"""Render every full-project caption state on a flat background, checking overflow.

No full user-video export: one synthetic frame per distinct caption/cover state.
"""
import sys,copy,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from videotranslator.project import load_project
from videotranslator.subtitles import caption_intervals,active_covers,rendered_covers,make_ass

root=Path(sys.argv[1] if len(sys.argv)>1 else 'projects/full-episode').resolve();p=load_project(root/'project.json');states=[]
for number,c in enumerate(p['cues']):
    for start,end in caption_intervals(c,p):
        boxes=active_covers(c,start)
        if not boxes:continue
        entry=copy.deepcopy(c);entry.update(start=len(states),end=len(states)+1,boxes=boxes)
        entry.pop('cover_spans',None);states.append((number,start,entry))
test=copy.deepcopy(p);test['cues']=[entry for number,t,entry in states]
review=root/'review';review.mkdir(exist_ok=True);(review/'all-layouts.ass').write_text(make_ass(test),encoding='utf-8-sig')
w,h=p['media']['width'],p['media']['height']
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from videotranslator.live_video import LiveVideoWidget
app=QApplication.instance() or QApplication([])
widget=LiveVideoWidget();widget.set_project(test);widget.live=True
widget.frame=QImage(w,h,QImage.Format.Format_RGB32);widget.frame.fill(QColor('#123456'))
with (review/'all-layouts-ffmpeg.log').open('w') as log:
    proc=subprocess.Popen(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c=0x123456:s={w}x{h}:r=1:d={len(states)}','-vf','ass=filename=all-layouts.ass:fontsdir=../project.cache/fonts','-pix_fmt','rgb24','-f','rawvideo','-'],stdout=subprocess.PIPE,stderr=log,cwd=review)
failures=[];faint=[]
try:
    for number,t,c in states:
        raw=proc.stdout.read(w*h*3);assert len(raw)==w*h*3,'Incomplete test frame'
        frame=np.frombuffer(raw,np.uint8).reshape(h,w,3);mask=np.zeros((h,w),bool)
        import math
        for x,y,bw,bh in rendered_covers(c,p,w,h,c['start']):
            mask[math.floor(y):math.ceil(y+bh),math.floor(x):math.ceil(x+bw)]=True
        white=(frame>180).all(axis=2);outside=int((white&~mask).sum())
        if outside:
            failures.append({'cue':number,'time':t,'outside_pixels':outside})
            from PIL import Image
            Image.fromarray(frame).save(review/f'overflow-{number}-{t:.2f}.png')
        if not white.any():faint.append({'cue':number,'time':t})
        widget.time=c['start']+.1
        qt_image=widget.composite().convertToFormat(QImage.Format.Format_RGB888)
        qt=np.frombuffer(qt_image.bits(),np.uint8).reshape(h,qt_image.bytesPerLine())[:,:w*3].reshape(h,w,3)
        qt_white=(qt>180).all(axis=2)
        qt_outside=int((qt_white&~mask).sum())
        if qt_outside:failures.append({'cue':number,'time':t,'renderer':'Qt','outside_pixels':qt_outside})
finally:
    proc.kill();proc.wait();proc.stdout.close()
result={'caption_states_checked':len(states),'renderers':['Qt','libass'],'overflow':failures,'no_bright_text':faint}
(review/'all-layouts-pixels.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
assert not failures,'Caption ink exceeded its cover; inspect saved frames'
