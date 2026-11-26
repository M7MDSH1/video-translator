"""Real native corner resizing and rendered-preview check on an isolated gaming excerpt."""
import copy,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt,QPoint,QProcess,QUrl
from PySide6.QtTest import QTest
from videotranslator.app import create_application,MainWindow
from videotranslator.project import load_project,save_project
from videotranslator.subtitles import caption_blocks,caption_bounds

out=ROOT/'artifacts'/'caption-resize';out.mkdir(exist_ok=True)
app=create_application([]);w=MainWindow();w.resize(1440,1040);w.show();w.audio.setVolume(0)
p=load_project(ROOT/'artifacts'/'ui-redesign'/'ocr'/'project.json');save_project(p,out/'project.json');w.load_path(out/'project.json')
errors=[];w.error=lambda e:errors.append(str(e))
def wait(test,timeout=60):
    deadline=time.monotonic()+timeout
    while not test():
        app.processEvents();time.sleep(.03)
        assert not errors,errors
        assert time.monotonic()<deadline,'Timed out'
    app.processEvents()
try:
    w.tabs.setCurrentIndex(1);w.live_view(start=3)
    wait(lambda:not w.video.frame.isNull() and w.preview_freeze_position is None)
    before=copy.deepcopy(w.p['cues']);w.video.composite().save(str(out/'before.png'))
    width,height=w.video.source_size();l,t,r,b=caption_bounds(caption_blocks(w.p['cues'][0],w.p,width,height,w.video.time))
    rect=w.video.frame_rect()
    def point(x,y):return QPoint(round(rect.x()+x*rect.width()/width),round(rect.y()+y*rect.height()/height))
    a=point(l,t);z=point((l+r)/2+(l-r)/2*1.25,(t+b)/2+(t-b)/2*1.25)
    QTest.mousePress(w.video,Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(w.video,z);QTest.mouseRelease(w.video,Qt.MouseButton.LeftButton,pos=z)
    assert 1.20 < w.p['style']['caption_scale'] < 1.30
    assert before==w.p['cues'],'Global text resize must preserve source cues and original covers'
    assert not w.export_button.isEnabled();w.save_live_edits()
    w.video.composite().save(str(out/'live-after.png'));w.grab().save(str(out/'resize-in-app.png'))
    saved=load_project(w.path);assert saved['style']['caption_scale']==w.p['style']['caption_scale']
    w.tabs.setCurrentIndex(2);w.preview_start.setValue(1);w.preview_length.setValue(5);w.run('preview')
    wait(lambda:w.proc.state()==QProcess.ProcessState.NotRunning,120)
    assert w.proc.exitCode()==0,w.log.toPlainText()
    assert w.preview_current() and w.p['approval'] is None
    (out/'result.json').write_text(json.dumps({'preview':w.p['preview']['path'],'scale':w.p['style']['caption_scale'],'cues_and_original_covers_unchanged':True,'saved_and_reopened':True,'approval':None},indent=2),encoding='utf-8')
    print('Real subtitle resizing, saved size, unchanged covers and rendered preview passed.')
finally:
    w.autosave.stop();w.player.stop();w.player.setSource(QUrl());w.p=None;w.close();app.processEvents()
