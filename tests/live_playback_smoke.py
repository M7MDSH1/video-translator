"""Real video playback and edits; never modifies the user's project."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
Path('artifacts/verification').mkdir(parents=True,exist_ok=True)
from PySide6.QtCore import QTimer
from videotranslator.app import MainWindow,create_application
app=create_application([]);temp=tempfile.TemporaryDirectory();w=MainWindow();w.load_path('projects/test-ocr/project.json');w.path=Path(temp.name)/'project.json';w.show();w.audio.setVolume(0)
w.apply_arabic_style()
def verify():
    try:
        assert not w.video.frame.isNull();assert w.video.live
        before=w.video.composite();before.save('artifacts/verification/live-before.png');w.grab().save('artifacts/verification/live-editor.png')
        w.live_text.setPlainText('هذا تعديل مباشر!\nتتغير الترجمة دون تصدير الفيديو.')
        after=w.video.composite();after.save('artifacts/verification/live-after.png');assert before!=after
        assert w.showing_path(w.p['video']);assert w.proc is None
        w.live_boxes.setPlainText('[[700, 870, 450, 42], [450, 925, 1000, 45]]')
        covers=w.video.composite();covers.save('artifacts/verification/live-covers-after.png');assert covers!=after
        w.player.play();QTimer.singleShot(1500,finish)
    except Exception:
        import traceback;traceback.print_exc();w.autosave.stop();w.p=None;app.exit(1)
def finish():
    assert w.player.position()>2000
    print('Real playback, live Arabic typing, cover edits, and continuous playback passed; no render process.',flush=True)
    w.autosave.stop();w.p=None;app.exit(0)
QTimer.singleShot(2500,verify)
sys.exit(app.exec())
