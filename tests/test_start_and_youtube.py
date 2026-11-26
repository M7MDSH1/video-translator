"""Start screen (new or open project) and the YouTube captions output."""
import json,os,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QProcess,QUrl
from videotranslator.project import new_project,save_project,load_project
from videotranslator.start_screen import recent_projects

def project(folder,**changes):
    p=new_project(str(Path(__file__).resolve().parent/'fixtures'/'test_excerpt.mp4'),{'width':1920,'height':1080,'duration':20,'streams':[]})
    p['target']='ar';p['cues']=[{'start':1,'end':3,'original':'Hello','translation':'...مرحبا\nكيف حالك','boxes':[],'flags':[],'reviewed':False},
                                {'start':4,'end':6,'original':'Bye','translation':'إلى اللقاء','boxes':[],'flags':[],'reviewed':False}]
    p.update(changes);path=Path(folder)/'project.json';save_project(p,path);return path

class RecentProjectTests(unittest.TestCase):
    def test_only_project_files_newest_first(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('old','new'):
                (Path(d)/name).mkdir();project(Path(d)/name,video=f'C:/Videos/{name} clip.mp4');os.utime(Path(d)/name/'project.json',(1,1) if name=='old' else None)
            # Snapshots and backups beside a project are not projects to open.
            shutil.copy(Path(d)/'new'/'project.json',Path(d)/'new'/'approved-export.json')
            shutil.copy(Path(d)/'new'/'project.json',Path(d)/'new'/'before-reprocess-1.json')
            found=recent_projects(d)
            self.assertEqual([r['video'] for r in found],['new clip.mp4','old clip.mp4'])

class YoutubeCaptionTests(unittest.TestCase):
    def test_captions_file_needs_no_approved_preview(self):
        from videotranslator import engine
        with tempfile.TemporaryDirectory() as d:
            path=project(d,appearance='youtube')
            with patch.object(engine,'ROOT',Path(d)),patch('sys.stdout'):engine.Worker(path).render()
            p=load_project(path);srt=Path(p['last_export'])
            self.assertTrue(srt.name.endswith(' - Arabic.ar.srt'),srt.name);self.assertEqual(srt.parent.parent.resolve(),(Path(d)/'exports').resolve())
            text=srt.read_text(encoding='utf-8')
            self.assertIn('00:00:01,000 -->',text)
            # Every Arabic line starts with a right-to-left mark, so "...مرحبا" stays right-aligned.
            lines=[l for l in text.split('\n') if l and not l[0].isdigit()]
            self.assertTrue(lines and all(l.startswith('\u200f') for l in lines),lines)
            self.assertFalse(list(Path(d,'exports').rglob('*.mkv')))  # no video is rendered
    def test_captions_drop_only_verified_speaker_names(self):
        from videotranslator.subtitles import make_srt
        with tempfile.TemporaryDirectory() as d:
            p=load_project(project(d,appearance='youtube',glossary={'Soul':'سول'},
                                   dialogue_profile={'speaker_y':.82,'dialogue_y':.88,'tolerance':.018,'vertical_drift':.035}))
            speaker,line=[800,870,100,30],[600,935,700,30]  # 1080-high frame: the name sits at 0.82 of the height
            p['cues'][0].update(original='Soul\nDo not panic',translation='سول\nلا تفزع',boxes=[speaker,line])
            p['cues'][1].update(original='Run\nthey are coming',translation='اهرب\nإنهم قادمون',boxes=[speaker,line])  # not a known name
            text=make_srt(p,speaker_names=False)
            self.assertNotIn('سول',text);self.assertIn('لا تفزع',text);self.assertIn('اهرب',text)
            self.assertIn('سول',make_srt(p))  # the SRT beside a rendered video keeps names
    def test_empty_translation_is_still_refused(self):
        from videotranslator import engine
        with tempfile.TemporaryDirectory() as d:
            path=project(d,appearance='youtube');p=load_project(path);p['cues'][1]['translation']='';save_project(p,path)
            with patch.object(engine,'ROOT',Path(d)),self.assertRaisesRegex(ValueError,'empty'):engine.Worker(path).render()

class EncoderFallbackTests(unittest.TestCase):
    def test_preview_uses_the_nvidia_encoder_and_falls_back_to_cpu(self):
        from videotranslator import engine
        with tempfile.TemporaryDirectory() as d:
            path=project(d);worker=engine.Worker(path);calls=[];reason='[h264_nvenc @ 0] No capable devices found'
            def command(args,duration=0,label=''):
                calls.append(args)
                if 'h264_nvenc' in args:raise RuntimeError(reason)
                Path(args[-1]).write_bytes(b'x')
            worker.command=command
            with patch('sys.stdout'):worker.render(preview=True,start=0,length=2)
            self.assertEqual(['h264_nvenc' in calls[0],'libx264' in calls[1],len(calls)],[True,True,2])
            self.assertTrue(Path(load_project(path)['preview']['path']).exists())
            # A failure that is not about the encoder is reported, not retried on the CPU.
            calls.clear();reason='No space left on device'
            with patch('sys.stdout'),self.assertRaisesRegex(RuntimeError,'space'):worker.render(preview=True,start=0,length=2)
            self.assertEqual(len(calls),1)

class StartScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from videotranslator.app import MainWindow
        self.temp=tempfile.TemporaryDirectory();self.w=MainWindow();self.errors=[];self.w.error=lambda e:self.errors.append(str(e))
    def tearDown(self):
        self.w.autosave.stop();self.w.player.stop();self.w.player.setSource(QUrl());self.w.p=None;self.w.close();self.w.deleteLater();self.app.processEvents();self.temp.cleanup()
    def test_app_opens_on_the_start_screen_without_select_or_open_in_the_workspace(self):
        self.assertIs(self.w.stack.currentWidget(),self.w.start)
        from PySide6.QtWidgets import QPushButton
        workspace=self.w.stack.widget(1)
        labels={b.text() for b in workspace.findChildren(QPushButton)}
        self.assertIn('Home',labels);self.assertFalse({'Select video','Open project'}&labels)
    def test_opening_a_project_shows_the_workspace_and_home_returns(self):
        path=project(self.temp.name,appearance='youtube')
        self.w.load_path(str(path));self.assertEqual(self.w.stack.currentIndex(),1)
        self.assertEqual(self.w.appearance.currentText(),'YouTube captions (file you upload)')
        self.w.collect();self.assertEqual(self.w.p['appearance'],'youtube')  # survives load_ui → collect
        self.w.go_home()
        self.assertIsNone(self.w.p);self.assertIsNone(self.w.path);self.assertEqual(self.w.stack.currentIndex(),0)
        self.assertEqual(load_project(path)['appearance'],'youtube')
    def test_home_waits_for_a_running_job(self):
        path=project(self.temp.name);self.w.load_path(str(path))
        self.w.proc=MagicMock();self.w.proc.state.return_value=QProcess.ProcessState.Running
        self.w.go_home()
        self.assertIsNotNone(self.w.p);self.assertEqual(self.w.stack.currentIndex(),1);self.assertTrue(self.errors)
        self.w.proc=None
    def test_youtube_export_needs_no_preview_and_explains_the_upload(self):
        path=project(self.temp.name,appearance='youtube');self.w.load_path(str(path))
        self.w.p['checkpoints']['recognized']=True
        from videotranslator.project import recognition_key
        self.w.p['checkpoints']['recognition_key']=recognition_key(self.w.p)
        self.w.p['ui_baseline']={'recognition':recognition_key(self.w.p),'translation':[self.w.p['model'],self.w.p['target']]}
        self.w.refresh_approval()
        self.assertTrue(self.w.export_button.isEnabled());self.assertEqual(self.w.export_button.text(),'Save YouTube captions')
        self.assertIn('YouTube Studio',self.w.youtube_help.text())
    def test_clicking_save_youtube_captions_starts_the_export(self):
        # Regression: the button was enabled but the click still demanded an approved preview.
        path=project(self.temp.name,appearance='youtube');self.w.load_path(str(path))
        from videotranslator.project import recognition_key
        self.w.p['checkpoints'].update(recognized=True,recognition_key=recognition_key(self.w.p))
        self.w.p['ui_baseline']={'recognition':recognition_key(self.w.p),'translation':[self.w.p['model'],self.w.p['target']]}
        self.w.refresh_approval();self.assertTrue(self.w.export_button.isEnabled())
        with patch('videotranslator.app.QProcess') as process:
            process.ProcessState=QProcess.ProcessState;process.ProcessChannelMode=QProcess.ProcessChannelMode
            self.w.export_button.click()
            self.assertEqual(self.errors,[])
            args=process.return_value.start.call_args[0][1]
            self.assertEqual(args[:3],['-m','videotranslator.engine','export'])
        self.w.proc=None
    def test_drops_open_videos_only_from_the_start_screen(self):
        from PySide6.QtCore import QMimeData,QPointF,Qt
        from PySide6.QtGui import QDragEnterEvent
        video=Path(self.temp.name)/'clip.mp4';video.write_bytes(b'x');data=QMimeData();data.setUrls([QUrl.fromLocalFile(str(video))])
        enter=lambda:QDragEnterEvent(QPointF(5,5).toPoint(),Qt.DropAction.CopyAction,data,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
        e=enter();self.w.dragEnterEvent(e);self.assertTrue(e.isAccepted())
        self.w.load_path(str(project(self.temp.name)))
        e=enter();e.ignore();self.w.dragEnterEvent(e);self.assertFalse(e.isAccepted())

class AnimatedWindowSmokeTest(unittest.TestCase):
    """The other motion tests run with animation off (offscreen). This one runs the real animations."""
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from videotranslator import motion
        self.motion=motion;motion.FORCE=True;self.temp=tempfile.TemporaryDirectory()
    def tearDown(self):self.motion.FORCE=None;self.temp.cleanup()
    def run_events(self,ms):
        from PySide6.QtCore import QEventLoop,QTimer
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def test_open_change_tabs_go_home_and_close_a_dialog(self):
        from PySide6.QtWidgets import QDialog
        from PySide6.QtCore import QVariantAnimation,QTimer
        from videotranslator.app import MainWindow
        w=MainWindow();w.error=lambda e:self.fail(str(e));w.resize(1200,800);w.show();self.run_events(600)  # launch fade
        self.assertTrue(all(part.graphicsEffect() is None for part in w.start.launch_parts))
        w.load_path(str(project(self.temp.name)));self.run_events(50)
        for index in (1,2,3,0):w.tabs.setCurrentIndex(index);self.run_events(60)  # switch faster than the 220 ms fade
        self.run_events(500)
        self.assertTrue(all(panel.graphicsEffect() is None for panel in w.side_panels))
        self.assertEqual([lay.contentsMargins().top() for lay in w.side_layouts],[0]*4)  # no lift left half-way
        dialog=QDialog(w);self.motion.fade_window(dialog);dialog.show();QTimer.singleShot(30,dialog.reject);self.run_events(700)
        self.assertEqual(dialog.windowOpacity(),1)  # closed mid-fade, never left invisible
        w.go_home();self.run_events(500)
        self.assertEqual(w.stack.currentIndex(),0);self.assertIsNone(w.p);self.assertIsNone(w.start.graphicsEffect())
        running=[a for a in w.findChildren(QVariantAnimation) if a.state()==QVariantAnimation.State.Running]
        self.assertEqual(running,[])  # nothing keeps animating when idle
        w.close();w.deleteLater();self.app.processEvents()

if __name__=='__main__':unittest.main()
