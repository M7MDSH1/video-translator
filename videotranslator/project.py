import hashlib
import json
import math
import os
import time
from pathlib import Path
from .typography import khaam_style

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = {'Auto':'auto','English':'en','Arabic':'ar','Chinese':'zh','Japanese':'ja','Korean':'ko','French':'fr','Spanish':'es','German':'de','Italian':'it','Portuguese':'pt','Russian':'ru','Turkish':'tr','Hindi':'hi','Persian':'fa','Urdu':'ur','Indonesian':'id'}

def new_project(video, media):
    return {'version':1,'video':str(Path(video).resolve()),'media':media,
            'mode':'speech','source':'auto','target':'ar','ocr_script':'en','asr_model':'turbo','device':'auto',
            'appearance':'add','original_kind':'track' if any(s.get('codec_type')=='subtitle' for s in media.get('streams',[])) else 'burned','subtitle_track':0,'model':'gemma4:12b',
            'roi':[.1,.70,.8,.28],'sample_interval':.25,'range_start':0.,'range_end':media['duration'],'process_full_video':True,
            'style':khaam_style({'x':.5,'y':.76,'padding':5}),
            'cues':[],'ocr_samples':[],'checkpoints':{},'preview':None,'approval':None}

def save_project(p,path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    with temp.open('w',encoding='utf-8') as f:
        json.dump(p,f,ensure_ascii=False,indent=2); f.flush(); os.fsync(f.fileno())
    # Windows readers/antivirus can briefly hold the destination without delete
    # sharing. Keep atomic writes, but tolerate those short-lived locks.
    for attempt in range(11):
        try:os.replace(temp,path);break
        except PermissionError:
            if attempt==10:raise
            time.sleep(min(.05*(attempt+1),.3))

def load_project(path):
    p=json.loads(Path(path).read_text(encoding='utf-8'))
    if p.get('version')!=1: raise ValueError('Unsupported project version')
    # Compatibility for earlier example projects and immutable export snapshots.
    # Only relocate the known bundled test excerpt, never an arbitrary user video.
    legacy=ROOT/'test_excerpt.mp4';fixture=ROOT/'tests'/'fixtures'/'test_excerpt.mp4'
    if Path(p['video'])==legacy and not legacy.exists() and fixture.exists():p['video']=str(fixture)
    validate(p)
    return p

def fingerprint(p):
    keys=['video','media','appearance','original_kind','style','cues']
    data={k:p[k] for k in keys};data['subtitle_track']=p.get('subtitle_track',0)
    data['style']=dict(p['style']);data['style'].setdefault('x',.5)
    data['style'].setdefault('minimum_size',1)
    data['renderer_revision']=10  # 10: covers start one OCR sample early; 9: covers reach past trailing ellipses; 8: bursts share reading time, one text size per caption; 7: captions held for reading time; 6: readable individual line backgrounds.
    source=Path(p['video'])
    if source.is_file():data['source_stat']=[source.stat().st_size,source.stat().st_mtime_ns]
    def normalize(value):
        if isinstance(value,bool):return value
        if isinstance(value,(int,float)):return float(value)
        if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
        if isinstance(value,list):return [normalize(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(normalize(data),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def recognition_key(p):
    settings={k:p[k] for k in ['video','mode','source','ocr_script','roi','sample_interval','range_start','range_end']}
    settings['asr_model']=p.get('asr_model','turbo')
    if p.get('audio_track',0):settings['audio_track']=p['audio_track']
    settings['recognizer_revision']=2
    settings['dialogue_profile']=p.get('dialogue_profile')
    settings['original_kind']=p['original_kind'];settings['subtitle_track']=p.get('subtitle_track',0)
    source=Path(p['video'])
    if source.is_file():settings['source_stat']=[source.stat().st_size,source.stat().st_mtime_ns]
    return hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()

def ocr_key(p):
    settings={k:p[k] for k in ['video','ocr_script','roi','sample_interval','range_start','range_end','original_kind']}
    settings['decoder_revision']=2
    settings['track']=p.get('subtitle_track',0)
    source=Path(p['video'])
    if source.is_file():settings['source_stat']=[source.stat().st_size,source.stat().st_mtime_ns]
    return hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()

def validate(p,render=False):
    from .replacements import validate_rules,deleted_by_rule
    validate_rules(p.get('replacements',{}))
    w,h=p['media']['width'],p['media']['height']
    for owner in [p['style']]+p['cues']:
        scale=owner.get('caption_scale',1)
        if not isinstance(scale,(int,float)) or not math.isfinite(scale) or not .1<=scale<=8:raise ValueError('Subtitle resize scale must be between 0.1 and 8.')
        offset=owner.get('caption_offset',[0,0])
        if not isinstance(offset,(list,tuple)) or len(offset)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) and -2<=v<=2 for v in offset):
            raise ValueError('Subtitle drag position must contain two valid relative coordinates.')
    for c in p['cues']:
        if not all(math.isfinite(float(c[k])) for k in ('start','end')) or not 0<=c['start']<c['end']<=p['media']['duration']+.1:
            raise ValueError('Every cue needs valid start/end times inside the video.')
        for b in c.get('boxes',[]):
            if len(b)!=4 or not all(math.isfinite(float(v)) for v in b) or min(b)<0 or b[2]<=0 or b[3]<=0 or b[0]+b[2]>w+1 or b[1]+b[3]>h+1:
                raise ValueError('Cover rectangles must be inside the frame with positive size.')
        if render and not c.get('translation','').strip() and not deleted_by_rule(c): raise ValueError('A translation is empty. Edit it before rendering.')
        if render and p['appearance']=='replace' and p['original_kind']=='burned' and not c.get('boxes') and not c.get('cover_spans'):
            raise ValueError('Burned-in replacement needs detected or manually drawn line covers for every cue. Run Detect covers or draw them.')
        if render and p['appearance']=='replace' and p['original_kind']=='burned' and c.get('cover_spans') and not any(span.get('boxes') and max(c['start'],span['start'])<min(c['end'],span['end']) for span in c['cover_spans']):
            raise ValueError('Detected covers do not overlap the edited cue timing. Redetect or manually draw covers.')
    if render and not p['cues']: raise ValueError('Process a video or add subtitles first.')

def approved(p):
    preview=p.get('preview') or {}
    return (p.get('approval')==fingerprint(p)==preview.get('fingerprint') and Path(preview.get('path','')).is_file())
