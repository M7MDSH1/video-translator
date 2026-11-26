"""Fresh-sample benchmark: score local Ollama models on the same subtitles against a hand-made reference SRT.

  .venv\\Scripts\\python.exe tools\\compare_models.py projects\\my-video\\project.json reference.ar.srt --models gemma4:12b qwen3.8:27b

Each model runs the app's translation pass (same prompts and batch size) on a copy of only the sampled
cues. That is not identical to a full-video run: the model's own name list is seeded from the sample alone,
there is no dialogue before the sample as context, translation memory starts empty and replacement rules are off.
The project's glossary (Edit names / terminology) is kept and overrides the model's names, as in the app,
so with a full glossary the ranking measures dialogue translation, not name choice.
Every model gets the same conditions, so the ranking is fair, but absolute scores can differ from a full
run in either direction. The project itself is not changed.

Score: chrF, 0-100, character n-grams; it suits Arabic, where one word takes many prefixed forms.
Higher is better; a few points apart is noise on a 60-line sample, so read samples.txt too.
Each run is saved to its own dated folder with scores, model digests, engine version, settings and input fingerprints.
"""
import argparse,contextlib,hashlib,inspect,io,json,re,subprocess,sys,tempfile,time
from collections import Counter
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from videotranslator.engine import Worker
from videotranslator.project import load_project,save_project
from videotranslator.replacements import without_marks
from videotranslator.dialogue import speaker_label,bare,spoken,given_names
from videotranslator.translation import REVISION

STAMP=re.compile(r'^\s*(\d+):(\d\d):(\d\d)[,.](\d{1,3})\s*-->\s*(\d+):(\d\d):(\d\d)[,.](\d{1,3})')

def parse_srt(path):
    cues=[]
    for number,block in enumerate(re.split(r'\n\s*\n',Path(path).read_text(encoding='utf-8-sig').replace('\r','').strip()),1):
        lines=block.split('\n');i=next((i for i,l in enumerate(lines) if '-->' in l),None)
        if i is None:continue
        m=STAMP.match(lines[i])
        if not m:raise ValueError(f'Reference entry {number} has a malformed timestamp: {lines[i]!r}')
        g=[int(x) for x in m.groups()];start=g[0]*3600+g[1]*60+g[2]+int(m.group(4).ljust(3,'0'))/1000
        end=g[4]*3600+g[5]*60+g[6]+int(m.group(8).ljust(3,'0'))/1000
        if end<=start:raise ValueError(f'Reference entry {number} ends before it starts: {lines[i]!r}')
        cues.append({'start':start,'end':end,'text':'\n'.join(lines[i+1:]).strip()})
    if not cues:raise ValueError('The reference SRT has no subtitle entries.')
    return cues

def normal(text):return re.sub(r'\s+','',without_marks(text).replace('ـ',''))

def chrf(pairs,order=6,beta=2):
    """Corpus chrF over (hypothesis, reference) pairs, as sacrebleu computes it."""
    match=[0]*order;hyp=[0]*order;ref=[0]*order
    for h,r in pairs:
        h,r=normal(h),normal(r)
        for n in range(order):
            a=Counter(h[i:i+n+1] for i in range(len(h)-n));b=Counter(r[i:i+n+1] for i in range(len(r)-n))
            match[n]+=sum((a&b).values());hyp[n]+=max(0,len(h)-n);ref[n]+=max(0,len(r)-n)
    used=[n for n in range(order) if hyp[n] and ref[n]] or [0]  # text shorter than 6 letters has no 6-grams to miss
    p=sum(match[n]/hyp[n] for n in used if hyp[n])/len(used);r=sum(match[n]/ref[n] for n in used if ref[n])/len(used)
    return 100*(1+beta**2)*p*r/(beta**2*p+r) if p+r else 0.

def passages(cues,reference):
    """Join cues and reference lines that overlap in time, directly or through each other, into passages.

    One cue spanning two reference lines, or two cues under one, become one passage, so neither side is cut.
    Returns (passages as (cue indices, reference indices), cue indices with no reference line).
    """
    overlap=lambda a,b:min(a['end'],b['end'])>max(a['start'],b['start'])
    edges={}
    for i,c in enumerate(cues):
        for j,r in enumerate(reference):
            if overlap(c,r):edges.setdefault(('c',i),set()).add(('r',j));edges.setdefault(('r',j),set()).add(('c',i))
    found=[];seen=set()
    for node in sorted(edges):
        if node in seen:continue
        group=set();stack=[node]
        while stack:
            n=stack.pop()
            if n not in group:group.add(n);stack+=edges[n]
        seen|=group;found.append((sorted(i for k,i in group if k=='c'),sorted(j for k,j in group if k=='r')))
    return sorted(found),[i for i in range(len(cues)) if ('c',i) not in edges]

def sample_passages(cues,reference,start,count):
    """Passages are built over the whole project, then split at the sample edges.

    A passage reaching a cue outside the sample is excluded and reported: its reference text includes
    dialogue that was never translated. Reference lines in the sample's time span with no cue are reported too.
    Returns (complete passages, boundary passages, unmatched sampled cues, unmatched reference lines).
    """
    found,lost=passages(cues,reference);inside=range(start,start+count)
    complete=[g for g in found if all(i in inside for i in g[0])]
    boundary=[g for g in found if any(i in inside for i in g[0]) and g not in complete]
    sample=cues[start:start+count];span=(sample[0]['start'],sample[-1]['end'])
    matched={j for _,r in found for j in r}
    lost_refs=[j for j,r in enumerate(reference) if min(r['end'],span[1])>max(r['start'],span[0]) and j not in matched]
    return complete,boundary,[i for i in lost if i in inside],lost_refs

def run(p,model,folder):
    p=json.loads(json.dumps(p));p['model']=model;p.pop('translation_memory',None);p['replacements']={}
    for c in p['cues']:c.update(translation='',reviewed=False,flags=[]);c.pop('translation_key',None);c.pop('replacement_state',None)
    path=Path(folder)/(re.sub(r'[^\w.-]+','_',model)+'.json');save_project(p,path)
    worker=Worker(path);began=time.time()
    with contextlib.redirect_stdout(io.StringIO()):worker.translate()
    return worker.p['cues'],given_names(worker.p),time.time()-began

def engine():
    """What produced the translations: the code itself, so a later app change is visible in the results."""
    source=inspect.getsource(Worker.translate)
    try:
        commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()
        dirty=bool(subprocess.run(['git','status','--porcelain','videotranslator'],cwd=ROOT,capture_output=True,text=True).stdout.strip())
    except OSError:commit,dirty=None,None
    options=re.search(r"'options':(\{[^}]*\})",source)
    return {'translation_revision':REVISION,'translate_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'git_commit':commit,'app_code_uncommitted_changes':dirty,'generation_options':options and options.group(1),
            'batch':re.search(r'def batches\(([^)]*)\)',inspect.getsource(sys.modules['videotranslator.translation'])).group(1)}

def digests():
    try:
        import requests
        return {m['name']:m.get('digest') for m in requests.get('http://127.0.0.1:11434/api/tags',timeout=5).json()['models']}
    except Exception:return {}

def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    positive=lambda s:int(s) if int(s)>0 else (_ for _ in ()).throw(argparse.ArgumentTypeError('must be 1 or more'))
    natural=lambda s:int(s) if int(s)>=0 else (_ for _ in ()).throw(argparse.ArgumentTypeError('must be 0 or more'))
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project');ap.add_argument('reference',help='hand-checked SRT in the target language')
    ap.add_argument('--models',nargs='+',required=True);ap.add_argument('--start',type=natural,default=0,help='first cue (0-based)')
    ap.add_argument('--count',type=positive,default=60,help='cues to translate (consecutive, so batch context works)')
    ap.add_argument('--speakers',nargs='*',default=[],help='speaker names shown above dialogue, when the project has no dialogue layout')
    ap.add_argument('--out',default='projects/model-comparison',help='a dated run folder is created inside it')
    a=ap.parse_args();sys.stdout.reconfigure(encoding='utf-8')
    try:reference=parse_srt(a.reference)
    except (OSError,ValueError) as exc:sys.exit(f'Reference: {exc}')
    p=load_project(a.project);every=p['cues'];total=len(every)
    if a.start>=total:sys.exit(f'--start {a.start} is past the last cue; the project has {total} cues.')
    groups,boundary,lost_cues,lost_refs=sample_passages(every,reference,a.start,a.count)
    if not groups:sys.exit('No complete reference passage inside these cues; check the SRT belongs to this video, or widen --count.')
    labels={i:speaker_label(every[i],p,a.speakers) for g in groups for i in g[0]}
    p['cues']=every[a.start:a.start+a.count]
    out=Path(a.out)/datetime.now().strftime('%Y%m%d-%H%M%S');out.mkdir(parents=True)
    print(f'Cues {a.start}-{a.start+len(p["cues"])-1} of {total}: {len(groups)} passages scored; not scored: '
          f'{len(boundary)} passages cut by the sample edge, {len(lost_cues)} cues and {len(lost_refs)} reference lines with no timing match\n')
    print(f'{"model":60} {"chrF":>6} {"time":>7} {"names removed":>14}')
    refs=['\n'.join(reference[j]['text'] for j in r) for _,r in groups];results={};texts={}
    named=sum(1 for v in labels.values() if v)
    with tempfile.TemporaryDirectory() as folder:
        for model in a.models:
            try:cues,terms,seconds=run(p,model,folder)
            except Exception as exc:
                results[model]={'error':str(exc)};print(f'{model:60} failed: {str(exc)[:150]}',flush=True);continue
            kept=lambda i:spoken(cues[i-a.start]['translation'],labels[i],terms)
            texts[model]=['\n'.join(kept(i) for i in c) for c,_ in groups]
            removed=sum(1 for c,_ in groups for i in c if kept(i)!=cues[i-a.start]['translation'].strip())
            # Speaker verified in the source, but the first translated line is not the expected name: kept, listed for review.
            uncertain=[{'cue':i,'speaker':labels[i],'first_line':cues[i-a.start]['translation'].split('\n')[0],'expected':terms.get(labels[i])}
                       for c,_ in groups for i in c if labels[i] and kept(i)==cues[i-a.start]['translation'].strip()]
            results[model]={'chrf':round(chrf(zip(texts[model],refs)),2),'seconds':round(seconds,1),
                            'speaker_lines_removed':removed,'speaker_lines_verified_in_source':named,'speaker_lines_kept_for_review':uncertain}
            print(f'{model:60} {results[model]["chrf"]:6.1f} {seconds:6.0f}s {removed:>7}/{named}',flush=True)
    tags=digests()
    for model in results:results[model]['digest']=tags.get(model) or tags.get(model+':latest')
    (out/'results.json').write_text(json.dumps({
        'created':datetime.now().isoformat(timespec='seconds'),'results':results,'engine':engine(),
        'sample':{'start':a.start,'count':len(p['cues']),'project_cues':total,'passages_scored':len(groups),
                  'boundary_passages_excluded':[{'cues':c,'reference_entries':[j+1 for j in r]} for c,r in boundary],
                  'unmatched_cues':lost_cues,'unmatched_reference_entries':[j+1 for j in lost_refs]},
        'settings':{'conditions':'fresh sample: model name list and context from the sample only, project glossary kept, empty memory, no replacement rules',
                    'glossary':{'entries':len(p.get('glossary',{})),'sha256':hashlib.sha256(json.dumps(p.get('glossary',{}),sort_keys=True,ensure_ascii=False).encode()).hexdigest()},
                    'metric':'chrF order 6 beta 2, Arabic marks and tatweel removed',
                    'speaker_check':'source line at the dialogue layout speaker height or named with --speakers, and the translated line exactly equals the name the model was given (glossary, else its own name list); other speaker lines are kept and listed',
                    'speakers_named':a.speakers},
        'project':{'path':str(Path(a.project).resolve()),'sha256':sha256(a.project)},
        'reference':{'path':str(Path(a.reference).resolve()),'sha256':sha256(a.reference)}},ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'samples.txt').open('w',encoding='utf-8') as f:
        for k,(c,r) in enumerate(groups):
            source=' / '.join('\n'.join(every[i]['original'].split('\n')[1 if labels[i] else 0:]).strip() for i in c)
            f.write(f'#{",".join(str(j+1) for j in r)} {every[c[0]]["start"]:.1f}s  EN: {source}\n  REF: {refs[k]}\n')
            for model in texts:f.write(f'  {model}: {texts[model][k]}\n')
            f.write('\n')
    print(f'\nSaved scores and side-by-side lines in {out.resolve()}')
    if not texts:sys.exit('Every model failed.')

if __name__=='__main__':main()
