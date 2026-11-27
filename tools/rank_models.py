"""Measure which installed Ollama model translates each language best, so the app can pick one by itself.

  .venv\\Scripts\\python.exe tools\\rank_models.py path\\to\\flores200_dataset\\devtest

The test text is FLORES-200 (https://github.com/facebookresearch/flores, "devtest"): the same sentences written by
professional translators in 200 languages. Each model translates the first lines of every source language into
the target with the app's own translation pass, and the result is scored against the human translation.

Results go to runtime\\model_scores.json, which the app reads (videotranslator/models.py). The run can be stopped
and started again: finished model/language pairs are kept. Models that are the same weights under two names are
measured once.

Limits worth knowing: FLORES is written news and encyclopedia text, not spoken dialogue; a few chrF points apart
on this many lines is noise, which is why the app treats close scores as a tie and takes the faster model.
"""
import argparse,contextlib,io,json,re,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from compare_models import chrf
from videotranslator.engine import Worker
from videotranslator.project import new_project,save_project
from videotranslator.subtitles import cue
from videotranslator.translation import REVISION

FLORES={'en':'eng_Latn','ar':'arb_Arab','zh':'zho_Hans','ja':'jpn_Jpan','ko':'kor_Hang','fr':'fra_Latn','es':'spa_Latn','de':'deu_Latn','it':'ita_Latn',
        'pt':'por_Latn','ru':'rus_Cyrl','tr':'tur_Latn','hi':'hin_Deva','fa':'pes_Arab','ur':'urd_Arab','id':'ind_Latn'}

def installed():
    import requests
    found=requests.get('http://127.0.0.1:11434/api/tags',timeout=5).json()['models']
    return {m['name']:m.get('digest') for m in found if not m.get('remote_host') and not m.get('remote_model') and 'cloud' not in m['name'].lower()}

def translate(model,source,target,lines,folder):
    p=new_project('benchmark.mp4',{'width':1280,'height':720,'duration':len(lines)*4.,'streams':[]})
    p.update(source=source,target=target,model=model,cues=[cue(i*4.,i*4.+3.5,text,[],1.) for i,text in enumerate(lines)])
    path=Path(folder)/'p.json';save_project(p,path);worker=Worker(path);began=time.time()
    with contextlib.redirect_stdout(io.StringIO()):worker.translate()
    return [c['translation'] for c in worker.p['cues']],time.time()-began

def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('data',help='the FLORES-200 devtest folder');ap.add_argument('--target',default='ar',choices=sorted(FLORES))
    ap.add_argument('--languages',nargs='+',default=[k for k in FLORES]);ap.add_argument('--models',nargs='+')
    ap.add_argument('--lines',type=int,default=30);ap.add_argument('--out',default=str(ROOT/'runtime'/'model_scores.json'))
    a=ap.parse_args();data=Path(a.data);out=Path(a.out)
    read=lambda code:(data/f'{FLORES[code]}.devtest').read_text(encoding='utf-8').splitlines()[:a.lines]
    try:saved=json.loads(out.read_text(encoding='utf-8'))
    except (OSError,ValueError):saved={}
    # Scores from another target, line count or prompt version cannot be mixed with new ones.
    if (saved.get('target'),saved.get('lines'),saved.get('revision'))!=(a.target,a.lines,REVISION):saved={'target':a.target,'lines':a.lines,'revision':REVISION,'models':{}}
    names=installed();reference=read(a.target);by_digest={}
    for name in a.models or names:
        if name not in names:print(f'{name}: not installed, skipped');continue
        by_digest.setdefault(names[name],[]).append(name)
    for digest,same in by_digest.items():
        entry=next((m for m in saved['models'].values() if m['digest']==digest),None) or {'digest':digest,'languages':{}}
        for source in a.languages:
            if source==a.target or source in entry['languages']:continue
            lines=read(source)
            try:
                with tempfile.TemporaryDirectory() as folder:got,seconds=translate(same[0],source,a.target,lines,folder)
            except Exception as error:print(f'{same[0]} {source}: failed ({str(error)[:120]})',flush=True);continue
            # Empty or copied lines are failures the score alone can hide.
            bad=sum(1 for g,s in zip(got,lines) if not g.strip() or g.strip()==s.strip())
            entry['languages'][source]={'chrf':round(chrf(list(zip(got,reference))),1),'seconds_per_line':round(seconds/len(lines),2),'bad_lines':bad}
            for name in same:saved['models'][name]=entry
            out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(saved,indent=1),encoding='utf-8')
            print(f'{same[0][:60]:60} {source}  chrF {entry["languages"][source]["chrf"]:5}  {seconds/len(lines):5.2f} s/line  bad {bad}',flush=True)
        for name in same:saved['models'][name]=entry
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(saved,indent=1),encoding='utf-8')

if __name__=='__main__':main()
