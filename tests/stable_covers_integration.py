"""Every sampled frame: text must be inside the tight covers, with no jitter."""
import sys,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from videotranslator.project import load_project,save_project
from videotranslator.engine import Worker,probe
from videotranslator.live_video import LiveVideoWidget
from videotranslator.subtitles import active_covers,cover_rect,stable_cover_spans

app=QApplication([]);root=Path('projects/stable-cover-check').resolve()
p=load_project(root/'project.json');source=root/'flat-fixture.mp4'
subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=0x123456:s=1920x1080:r=24:d=20','-c:v','libx264',str(source)],check=True)
p.update(video=str(source),media=probe(source),range_end=20,preview=None,approval=None)
path=root/'flat-fixture.json';save_project(p,path);worker=Worker(path);worker.render(preview=True,start=0,length=20)
w=LiveVideoWidget();w.set_project(p);w.live=True;w.frame=QImage(1920,1080,QImage.Format.Format_RGB32);w.frame.fill(QColor('#123456'))
decoder=subprocess.Popen(['ffmpeg','-v','error','-i',worker.p['preview']['path'],'-vf','fps=4:start_time=0','-pix_fmt','rgb24','-f','rawvideo','-'],stdout=subprocess.PIPE)
checked=0;previous={}
try:
    for n in range(80):
        t=n/4;raw=decoder.stdout.read(1920*1080*3)
        assert len(raw)==1920*1080*3
        exported=np.frombuffer(raw,np.uint8).reshape(1080,1920,3)
        w.time=t;live=w.composite();pixels=np.frombuffer(live.bits(),np.uint8).reshape(1080,1920,4)[:,:,:3]
        mask=np.zeros((1080,1920),bool);active=[]
        for i,c in enumerate(p['cues']):
            if c['start']<=t<c['end']:
                active.append(i)
                for box in active_covers(c,t):
                    x,y,bw,bh=cover_rect(box,p,1920,1080);mask[y:y+bh,x:x+bw]=True
        for name,frame in [('Qt',pixels),('libass',exported)]:
            white=(frame>180).all(axis=2)
            assert not (white&~mask).any(),(name,t,'text outside cover',int((white&~mask).sum()))
            if active:assert white.sum()>100,(name,t,'missing caption')
            key=(name,tuple(active))
            # These real excerpt cues contain stationary original subtitles.
            # Their white text mask must be identical throughout each cue.
            if active and key in previous:
                yy,xx=np.where(white);py,px=np.where(previous[key])
                bounds=np.array([xx.min(),yy.min(),xx.max(),yy.max()]);old=np.array([px.min(),py.min(),px.max(),py.max()])
                assert np.max(np.abs(bounds-old))<=1,(name,t,'text jitter',bounds.tolist(),old.tolist())
                if name=='Qt':assert np.array_equal(white,previous[key]),(name,t,'text jitter')
            previous[key]=white.copy()
        checked+=1
finally:
    decoder.kill();decoder.wait();decoder.stdout.close()
report={'frames_per_renderer':checked,'renderers':['Qt','libass'],'outside_cover_pixels':0,'jitter':False,
        'stable_runs_per_cue':[len(stable_cover_spans(c)) for c in p['cues']]}
(root/'pixel-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
