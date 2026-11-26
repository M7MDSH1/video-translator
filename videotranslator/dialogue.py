"""Opt-in dialogue layout locking for games with speaker-labelled subtitles."""
import copy
import re
from difflib import SequenceMatcher
from .subtitles import dialogue_samples
from .replacements import without_marks

def stable_lower_lines(items):
    """Repair partial OCR reads inside one otherwise stable dialogue cue.

    Only bridge at most two quarter-second missing samples. Different full lines
    start a new run; a matching short fragment inherits the complete line.
    """
    result=copy.deepcopy(items);run=[];best=None;last=-10
    def normalized(text):return re.sub(r'\W+',' ',text.casefold()).strip()
    def flush():
        if not run:return
        for i in range(run[0],run[-1]+1):result[i]=copy.deepcopy(best)
    for i,item in enumerate(items):
        if not item:continue
        a=normalized(item['text']);b=normalized(best['text']) if best else ''
        similar=bool(a and b) and (a in b or b in a or SequenceMatcher(None,a,b).ratio()>=.7)
        if run and (i-last>3 or not similar):flush();run=[];best=None
        if best is None or len(item['text'])*item['confidence']>len(best['text'])*best['confidence']:best=item
        run.append(i);last=i
    flush()
    return result

def profile_from_cue(c,w,h):
    boxes=c.get('boxes',[])
    if len(boxes)<2:raise ValueError('Select a dialogue cue with a speaker line and a dialogue line.')
    a,b=boxes[:2]
    return {'center':(a[0]+a[2]/2)/w,'speaker_y':(a[1]+a[3]/2)/h,
            'dialogue_y':(b[1]+b[3]/2)/h,'second_line_gap':(b[1]+b[3]/2-a[1]-a[3]/2)/h,
            'tolerance':.018,'vertical_drift':.035,'min_height':min(a[3],b[3])/h*.72}

def filter_project(p,profile):
    """Keep original detections and excluded cues for reversible review."""
    w,h=p['media']['width'],p['media']['height'];kept=[];excluded=[]
    for original in p['cues']:
        c=copy.deepcopy(original)
        sample=dialogue_samples([{'time':c['start'],'text':c['original'],'boxes':c['boxes'],'confidence':c['confidence']}],profile,w,h)[0]
        if not sample['text'] or sample['text'].split('\n')[0] in profile.get('excluded_speakers',[]):
            excluded.append(c);continue
        old_lines=c['original'].split('\n');new_lines=sample['text'].split('\n')
        translated=c['translation'].split('\n')
        if len(old_lines)==len(translated):
            indices=[i for i,(line,box) in enumerate(zip(old_lines,c['boxes'])) if any(line==txt and box==b for txt,b in zip(new_lines,sample['boxes']))]
            c['translation']='\n'.join(translated[i] for i in indices)
        c.update(original=sample['text'],boxes=sample['boxes'])
        for span in c.get('cover_spans',[]):
            source={'time':span['start'],'text':'\n'.join('line' for _ in span['boxes']),'boxes':span['boxes'],'confidence':1}
            span['boxes']=dialogue_samples([source],profile,w,h)[0]['boxes']
        c['flags']=[f for f in c.get('flags',[]) if not f.startswith(('Small fitted text','Possible game interface'))]
        kept.append(c)
    p.setdefault('excluded_cues',[]).extend(excluded)
    p['cues']=kept;p['dialogue_profile']=copy.deepcopy(profile);p['preview']=None;p['approval']=None
    return len(excluded)

def speaker_label(c,p,named=()):
    """The cue's first line when it is verified as a speaker label, else None.

    Verified means named by the caller, or placed at the speaker height of the project's dialogue
    layout (Detect dialogue layout). Wording alone never decides: a repeated "Run" looks like a name.
    """
    lines=[l.strip() for l in c['original'].split('\n') if l.strip()];boxes=c.get('boxes') or []
    if len(lines)<2:return None
    if lines[0] in named:return lines[0]
    profile=p.get('dialogue_profile')
    if profile and len(boxes)>=2:
        top,height=boxes[0][1],boxes[0][3]
        if abs((top+height/2)/p['media']['height']-profile['speaker_y'])<=profile.get('vertical_drift',profile['tolerance']):return lines[0]
    return None

def bare(text):return re.sub(r'[^\w]','',without_marks(text).replace('ـ',''))

def spoken(translation,label,terms):
    """Drop the translated first line only when it is exactly the name the
    app told the model to use (punctuation and marks aside), so a reply that skipped the name keeps its dialogue."""
    out=translation.split('\n')
    if label and len(out)>1 and terms.get(label) and bare(out[0])==bare(terms[label]):out=out[1:]
    return '\n'.join(out).strip()

def given_names(p):
    """The names the dialogue batches were given: the model's name list, overridden by the project glossary (engine.py translate, ask())."""
    terms=dict(p.get('translation_memory',{}).get('terms',{}));terms.update(p.get('glossary',{}))
    return terms
