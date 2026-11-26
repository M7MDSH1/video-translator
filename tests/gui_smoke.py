import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
Path('artifacts/verification').mkdir(parents=True,exist_ok=True)
from PySide6.QtCore import QTimer
from videotranslator.app import create_application,MainWindow,RectangleDialog,CueDialog
from videotranslator.project import fingerprint
app=create_application([]);window=MainWindow();window.load_path('projects/test-ocr/project.json');window.show()
before=fingerprint(window.p);window.collect();assert fingerprint(window.p)==before, 'Loading/saving must not invalidate an unchanged preview'
assert window.table.rowCount()==4
window.player.setPosition(3000);window.audio.setVolume(0);window.player.play()
def check():
    try:
        window.player.pause()
        assert not window.player.errorString(),window.player.errorString()
        window.grab().save('artifacts/verification/application.png')
        dialog=RectangleDialog(window.p['video'],3,window.p['cues'][0]['boxes'],parent=window)
        dialog.values.setPlainText('[[780, 870, 364, 40], [520, 923, 885, 46]]')
        assert dialog.apply_numbers();assert len(dialog.canvas.boxes)==2
        dialog.show();app.processEvents();dialog.grab().save('artifacts/verification/cover-editor.png');dialog.reject()
        edit=CueDialog(window.p['cues'][0],window.p['media']['duration']);edit.start.setValue(1.3);edit.translation.setPlainText('اختبار العربية\nسطر ثان.');edit.finish()
        assert edit.c['start']==1.3 and '\n' in edit.c['translation']
        assert edit.c['cover_spans'] and edit.c['cover_spans'][0]['start']==1.3
        print('GUI playback, unchanged-preview fingerprint, cover editor, timing/line-break editor passed.',flush=True)
        app.exit(0)
    except Exception:
        import traceback;traceback.print_exc();app.exit(1)
QTimer.singleShot(2500,check)
sys.exit(app.exec())
