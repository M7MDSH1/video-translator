import unittest
import tempfile
import json
from unittest.mock import patch
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QProcess,QUrl,QCoreApplication,QEvent
from videotranslator.app import MainWindow
from videotranslator.project import load_project,fingerprint

SAMPLE=Path(__file__).resolve().parent.parent/'projects'/'test-ocr'/'project.json'
needs_sample=unittest.skipUnless(SAMPLE.is_file(),'needs the local sample project projects/test-ocr, which is not in the repository')

@needs_sample
class PlayerViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=MainWindow()
        self.w.error=lambda exc: (_ for _ in ()).throw(AssertionError(str(exc)))
        self.w.load_path('projects/test-ocr/project.json')
        self.temp=tempfile.TemporaryDirectory();self.w.path=Path(self.temp.name)/'project.json'
    def tearDown(self):
        self.w.autosave.stop();self.w.player.stop();self.w.player.setSource(QUrl());self.w.p=None;self.w.close();self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents();self.temp.cleanup()
    def test_model_dropdown_lists_local_models_and_saves_choice(self):
        from unittest.mock import MagicMock
        reply=MagicMock();reply.json.return_value={'models':[{'name':'qwen3:8b'},{'name':'gemma4:12b'},{'name':'gpt-oss:120b-cloud'},{'name':'x:latest','remote_host':'https://ollama.com'}]}
        with patch('requests.get',return_value=reply):self.w.refresh_models()
        names=[self.w.model.itemText(i) for i in range(self.w.model.count())]
        self.assertEqual(names,['auto','gemma4:12b','qwen3:8b'])
        self.w.model.setCurrentText('qwen3:8b');self.w.save()
        self.assertEqual(self.w.p['model'],'qwen3:8b')
    def test_project_opens_live_view(self):
        self.assertTrue(self.w.showing_path(self.w.p['video']))
        self.assertTrue(self.w.video.live)
        self.assertIn('Live edits',self.w.view_label.text())
    def test_selecting_cue_keeps_preview(self):
        # Fixture-only validity: user edits must not make the UI unit test depend
        # on their current approval state. Never write this back to their project.
        self.w.p['preview']['fingerprint']=fingerprint(self.w.p)
        self.w.play_preview();self.w.player.pause();self.w.table.selectRow(1)
        self.assertTrue(self.w.showing_path(self.w.p['preview']['path']))
    def test_original_choice_is_explicit(self):
        self.w.original_video();self.w.table.selectRow(1)
        self.assertTrue(self.w.showing_path(self.w.p['video']))
        self.assertIn('Original',self.w.view_label.text())
        self.assertFalse(self.w.video.live)
    def test_khaam_preset_survives_collect_and_updates_live(self):
        original=self.w.p['cues'][0]['translation']
        self.w.apply_arabic_style();self.w.collect()
        self.assertEqual(self.w.p['style']['font'],'Almarai')
        self.assertTrue(self.w.p['style']['arabic_typography'])
        self.assertEqual(self.w.p['style']['line_height'],1.45)
        self.assertEqual(self.w.p['cues'][0]['translation'],original)
        self.assertTrue(self.w.video.live)
    def test_inline_text_updates_overlay_and_invalidates_preview(self):
        self.w.table.selectRow(0);self.w.live_text.setPlainText('تحديث مباشر الآن')
        self.assertEqual(self.w.video.project['cues'][0]['translation'],'تحديث مباشر الآن')
        self.assertTrue(self.w.video.live);self.assertIsNone(self.w.proc)
        self.assertFalse(self.w.preview_current())
    def test_cover_numbers_and_style_update_live(self):
        self.w.table.selectRow(0);self.w.live_boxes.setPlainText('[[20, 30, 100, 40]]');self.w.size.setValue(55)
        self.assertEqual(self.w.video.project['cues'][0]['boxes'],[[20,30,100,40]])
        self.assertNotIn('cover_spans',self.w.p['cues'][0]);self.assertEqual(self.w.video.project['style']['size'],55)
    def test_invalid_cover_draft_does_not_replace_valid_covers(self):
        self.w.table.selectRow(0);before=self.w.p['cues'][0]['boxes']
        self.w.live_boxes.setPlainText('[[20,')
        self.assertEqual(self.w.p['cues'][0]['boxes'],before)
    def test_readable_minimum_survives_live_edits_and_collect(self):
        self.w.minimum_size.setValue(26);self.w.collect()
        self.assertEqual(self.w.p['style']['minimum_size'],26)
        self.assertTrue(self.w.video.live)
    def test_dialogue_layout_action_preserves_selected_dialogue(self):
        self.w.table.selectRow(0)
        original=self.w.p['cues'][0]['translation']
        self.w.lock_dialogue_layout()
        self.assertEqual(self.w.p['cues'][0]['translation'],original)
        self.assertIn('dialogue_profile',self.w.p)
    def test_timing_outside_detected_covers_requires_new_boxes(self):
        self.w.table.selectRow(0);self.w.live_end.setValue(9);self.w.live_start.setValue(8)
        self.assertEqual(self.w.p['cues'][0]['cover_spans'],[])
        self.assertEqual(self.w.p['cues'][0]['boxes'],[])
    def test_model_setup_flushes_edits_and_locks_editor(self):
        self.w.live_text.setPlainText('تعديل محفوظ قبل تنزيل النموذج')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(QProcess,'start'):
            self.w.setup_ocr()
        saved=json.loads(self.w.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['cues'][0]['translation'],'تعديل محفوظ قبل تنزيل النموذج')
        self.assertFalse(self.w.live_panel.isEnabled());self.assertFalse(self.w.video.isEnabled())

if __name__=='__main__':unittest.main()
