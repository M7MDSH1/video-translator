"""Render regression words/ranges through the real libass and Qt paths."""
import subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
Path('artifacts/verification').mkdir(parents=True,exist_ok=True)
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from videotranslator.project import new_project,save_project,load_project
from videotranslator.engine import Worker,probe
from videotranslator.live_video import LiveVideoWidget

app=QApplication([])
source=Path('projects/track-fixture/source.mkv').resolve()
p=new_project(str(source),probe(source));p['appearance']='replace';p['style'].update(size=24,y=.94)
p['cues']=[{'start':.1,'end':2.9,'original':'Arabic QA','translation':'حتى متى يبقى معنى هذا المبنى؟\nمدة العرض 35–45 ثانية والتاريخ 11-01\nالحلقة 12 والسعر 1,400 ريال\nيَحْيَى يجمع الخبرة والمعرفة','boxes':[]}]
path=Path('projects/arabic-qa/project.json');save_project(p,path);Worker(path).render(preview=True,start=0,length=3)
preview=load_project(path)['preview']['path']
subprocess.run(['ffmpeg','-v','error','-ss','1','-i',preview,'-frames:v','1','-update','1','-y','artifacts/verification/arabic-qa-export.png'],check=True)
w=LiveVideoWidget();w.set_project(p);w.live=True;w.time=1;w.frame=QImage(640,360,QImage.Format.Format_RGB32);w.frame.fill(QColor('#345678'));w.composite().save('artifacts/verification/arabic-qa-live.png')
print('Arabic QA frames rendered. Check full-word joining, final ya, numeric runs, marks and punctuation.')
