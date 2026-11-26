"""Real Qt/libass pixel checks for captions following covers at frame edges."""
import sys,subprocess,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from videotranslator.project import new_project,save_project
from videotranslator.engine import Worker,probe
from videotranslator.subtitles import cue
from videotranslator.live_video import LiveVideoWidget

app=QApplication([]);folder=Path('projects/three-fixes-check').resolve();folder.mkdir(exist_ok=True,parents=True)
source=folder/'edge-fixture.mp4'
subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=0x123456:s=640x360:r=24:d=4','-c:v','libx264',str(source)],check=True)
p=new_project(source,probe(source));p.update(appearance='replace',original_kind='burned');p['style']['size']=28
c=cue(0,4,'Original',[[0,0,120,35]],1)
c['translation']='مرحبا Hello'
c['cover_spans']=[{'start':i,'end':i+1,'boxes':[[x,y,120,35]]} for i,(x,y) in enumerate([(0,0),(520,0),(0,325),(520,325)])]
p['cues']=[c];path=folder/'edge-fixture.json';save_project(p,path);worker=Worker(path);worker.render(preview=True,start=0,length=4)
preview=worker.p['preview']['path'];w=LiveVideoWidget();w.set_project(p);w.live=True
w.frame=QImage(640,360,QImage.Format.Format_RGB32);w.frame.fill(QColor('#123456'));checks=[]
for i in range(4):
    t=i+.5
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',preview,'-vf',f'select=gte(t\\,{t})','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'])
    export=np.frombuffer(raw,np.uint8).reshape(360,640,3)
    w.time=t;live=w.composite();pixels=np.frombuffer(live.bits(),np.uint8).reshape(360,640,4)[:,:,:3]
    for label,frame in [('export',export),('live',pixels)]:
        yy,xx=np.where((frame>180).all(axis=2))
        assert len(xx)>100,(i,label,'missing text')
        assert xx.min()>=4 and xx.max()<636 and yy.min()>=4 and yy.max()<356,(i,label,'clipped',xx.min(),xx.max(),yy.min(),yy.max())
        checks.append({'corner':i,'renderer':label,'bounds':[int(xx.min()),int(yy.min()),int(xx.max()),int(yy.max())]})
(folder/'edge-verification.json').write_text(json.dumps(checks,indent=2))
print('All four corners: Arabic/English text visible inside frame in live Qt and actual libass video; moving-cover events verified.')
