"""Validate generated bitmap tracks through OCR, preview and export."""
import json,subprocess,sys,hashlib
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from videotranslator.project import load_project,save_project,fingerprint
from videotranslator.engine import Worker,probe

folder=Path('projects/functional-check').resolve();results=[]
for name in ('pgs','dvd','dvb'):
    path=folder/('bitmap-'+name+'.json')
    worker=Worker(path);worker.recognize();p=worker.p
    assert any('Original bitmap subtitle' in c['original'] for c in p['cues']),name
    assert all(c['end']<=2.6 for c in p['cues']),(name,'subtitle should clear')
    for c in p['cues']:c['translation']='اختبار ترجمة العربية'
    p['style'].update(size=24,y=.55)
    source_hash=hashlib.sha256(Path(p['video']).read_bytes()).hexdigest()
    def audiohash(path):return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-'])
    for mode in ('add','replace'):
        p['appearance']=mode;target=folder/(name+'-'+mode+'.json');save_project(p,target)
        w=Worker(target);w.render(preview=True,start=.5,length=3)
        preview=w.p['preview']['path']
        # Decode sequentially: verify actual pixels and subtitle disappearance,
        # not just successful encoding or stream metadata.
        def frame_at(video,t):
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(video),'-vf',f'select=gte(t\\,{t})','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
            return np.frombuffer(raw,dtype=np.uint8).reshape(360,640,3)
        frame=frame_at(preview,.5)
        from PIL import Image
        Image.fromarray(frame).save(folder/(name+'-'+mode+'.png'))
        assert (frame[140:220,:,0]>180).sum()>100,(name,mode,'missing Arabic')
        original_pixels=(frame[270:350,:,0]>180).sum()
        assert original_pixels>100 if mode=='add' else original_pixels==0,(name,mode,'incorrect originals')
        assert (frame_at(preview,2.5)[:,:,0]>180).sum()==0,(name,mode,'subtitle failed to clear')
        # Approval simulation is only for our generated test fixture.
        w.p['approval']=fingerprint(w.p);w.save();w.render()
        export=max((folder/'exports').glob('translated-*.mkv'),key=lambda f:f.stat().st_mtime_ns)
        assert not any(s['codec_type']=='subtitle' for s in probe(export)['streams'])
        assert audiohash(export)==audiohash(p['video'])
        subprocess.run(['ffmpeg','-v','error','-i',str(export),'-f','null','-'],check=True)
        results.append({'codec':name,'mode':mode,'preview':preview,'export':str(export),'audio_identical':True})
    assert source_hash==hashlib.sha256(Path(p['video']).read_bytes()).hexdigest()
(folder/'bitmap-verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('PGS, DVD, DVB: OCR, clearing, add/replace, decoding and exact audio-copy checks passed.')
