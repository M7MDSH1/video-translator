import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QProgressBar,QLabel,QWidget,QPlainTextEdit,QVBoxLayout
from videotranslator import job_steps,motion
from videotranslator.live_video import snap_center

class JobStepTests(unittest.TestCase):
    def test_process_moves_through_load_read_translate(self):
        self.assertEqual(job_steps.current('process',0,'Loading offline OCR; scanning only the selected rectangle'),0)
        self.assertEqual(job_steps.current('process',0,'OCR 0.25 / 60.00s; timing resolution 0.25s'),1)
        self.assertEqual(job_steps.current('process',23,'Transcribed through 40.0s (en, cuda)'),1)
        self.assertEqual(job_steps.current('process',50,'Translating 14 names and terms before dialogue'),2)
        # Recognition already cached: the worker starts straight at translation.
        self.assertEqual(job_steps.current('process',50,'Translating batch of 12 cues locally'),2)
    def test_steps_follow_the_source_mode(self):
        self.assertIn('Listen and transcribe',job_steps.steps('process','speech'))
        self.assertIn('Read on-screen subtitles',job_steps.steps('process','ocr'))

class MotionSnapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_hidden_widgets_get_the_final_state_at_once(self):
        bar=QProgressBar();motion.progress_to(bar,60);self.assertEqual(bar.value(),60)
        label=QLabel();motion.flash(label,'#B0BDCE');self.assertEqual(label.styleSheet(),'')
        self.parent=QWidget();body=QWidget(self.parent);motion.reveal(body,True);self.assertFalse(body.isHidden());self.assertEqual(body.maximumHeight(),16777215)
        motion.reveal(body,False);self.assertTrue(body.isHidden())
    def test_progress_going_back_snaps(self):
        bar=QProgressBar();bar.setValue(80);motion.progress_to(bar,0);self.assertEqual(bar.value(),0)
    def test_reveal_keeps_the_widgets_own_height_limit(self):
        # The processing log is capped at 80 px; opening and closing it must not lift that cap.
        holder=QWidget();log=QPlainTextEdit(holder);log.setMaximumHeight(80);log.hide()
        motion.reveal(log,True);self.assertEqual(log.maximumHeight(),80)
        motion.reveal(log,False);motion.reveal(log,True);self.assertEqual(log.maximumHeight(),80)
    def test_offscreen_windows_never_animate(self):
        w=QWidget();w.show();self.assertFalse(motion.enabled(w))
    def test_fade_in_leaves_no_effect_and_restores_margins(self):
        w=QWidget();lay=QVBoxLayout(w);lay.setContentsMargins(8,0,0,0)
        motion.fade_in(w,rise_layout=lay);self.assertIsNone(w.graphicsEffect());self.assertEqual(lay.contentsMargins().top(),0)
    def test_step_strip_breathes_only_while_running(self):
        strip=motion.StepStrip()
        strip.set(['Load','Read','Ready'],1,detail='Step 2 of 2 · Read',running=True)
        self.assertEqual((strip.index,strip.detail),(1,'Step 2 of 2 · Read'))
        strip.set(['Load','Read','Ready'],3,detail='Done',running=False)
        self.assertNotIn('breath',strip.__dict__.get('_tweens',{}))

class CaptionSnapTests(unittest.TestCase):
    def test_caption_snaps_to_the_centre_only_when_close(self):
        # Caption 800-1100 in a 1920 frame: centre 950. A move of +5 puts it at 955, within 10 of 960.
        self.assertEqual(snap_center(800,1100,5,1920,10),(10,True))
        self.assertEqual(snap_center(800,1100,-40,1920,10),(-40,False))

class WindowDropTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from videotranslator.app import MainWindow
        cls.w=MainWindow()
    @classmethod
    def tearDownClass(cls):cls.w.close();cls.w.deleteLater()
    def test_text_fields_refuse_dropped_files(self):
        # Otherwise a video dropped on the translation editor would paste its path into the subtitle.
        from PySide6.QtWidgets import QLineEdit
        fields=self.w.findChildren(QLineEdit)+self.w.findChildren(QPlainTextEdit)
        self.assertTrue(fields);self.assertFalse(any(f.acceptDrops() for f in fields))
        self.assertTrue(self.w.acceptDrops())
    def test_only_an_existing_video_file_counts_as_a_drop(self):
        import tempfile
        from pathlib import Path
        from PySide6.QtCore import QMimeData,QUrl,QPointF,Qt
        from PySide6.QtGui import QDropEvent
        keep=[]
        def drop(path):
            data=QMimeData();data.setUrls([QUrl.fromLocalFile(str(path))]);keep.append(data)  # the event does not own it
            return QDropEvent(QPointF(5,5),Qt.DropAction.CopyAction,data,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
        with tempfile.TemporaryDirectory() as d:
            video=Path(d)/'clip.MP4';video.write_bytes(b'x');text=Path(d)/'notes.txt';text.write_text('x')
            self.assertEqual(self.w.dropped_video(drop(video)),str(video).replace('\\','/'))
            self.assertEqual(self.w.dropped_video(drop(text)),'')
            self.assertEqual(self.w.dropped_video(drop(Path(d)/'missing.mkv')),'')

if __name__=='__main__':unittest.main()
