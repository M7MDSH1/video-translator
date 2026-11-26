"""Interactions in the real native four-step workspace, with isolated project copies."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QProcess, QUrl
from videotranslator.app import MainWindow
from videotranslator.project import fingerprint, save_project, load_project, recognition_key
from videotranslator.export_paths import next_export, reserve_export


SAMPLE=Path(__file__).resolve().parent.parent/'projects'/'test-ocr'/'project.json'
needs_sample=unittest.skipUnless(SAMPLE.is_file(),'needs the local sample project projects/test-ocr, which is not in the repository')

@needs_sample
class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=MainWindow()
        self.w.load_path('projects/test-ocr/project.json');self.w.path=Path(self.temp.name)/'project.json'
        self.w.p['checkpoints'].update(recognized=True,recognition_key=recognition_key(self.w.p))
        self.errors=[];self.w.error=lambda e:self.errors.append(str(e))

    def tearDown(self):
        self.w.autosave.stop();self.w.player.stop();self.w.player.setSource(QUrl());self.w.p=None;self.w.close();self.w.deleteLater();self.app.processEvents();self.temp.cleanup()

    def test_four_pages_share_player_without_losing_project_or_sink(self):
        player=self.w.player;sink=player.videoSink();p=self.w.p
        for index in (0,2,3,1):
            self.w.tabs.setCurrentIndex(index)
            self.assertIs(self.w.player,player);self.assertIs(player.videoSink(),sink)
            self.assertIs(self.w.p,p)
            expected=self.w.review_player_slot if index==1 else self.w.player_hosts[index].parentWidget()
            self.assertIs(self.w.player_panel.parentWidget(),expected)

    def test_source_mode_only_shows_relevant_options(self):
        self.w.mode.setCurrentIndex(0)
        self.assertTrue(self.w.ocr_panel.isHidden());self.assertFalse(self.w.speech_panel.isHidden())
        self.w.mode.setCurrentIndex(1)
        self.assertFalse(self.w.ocr_panel.isHidden());self.assertTrue(self.w.speech_panel.isHidden())

    def test_model_change_blocks_preview_and_persists_across_reopen(self):
        self.w.model.setCurrentText('other-local-model');self.w.save()
        self.assertEqual(self.w.pending_work(),(False,True))
        self.assertFalse(self.w.generate_button.isEnabled());self.assertFalse(self.w.export_button.isEnabled())
        self.w.load_path(self.w.path)
        self.assertTrue(self.w.pending_work()[1]);self.w.run('preview')
        self.assertIn('Translate again',self.errors[-1])

    def test_recognition_change_cancel_keeps_cues_and_does_not_start(self):
        before=copy.deepcopy(self.w.p['cues']);self.w.interval.setValue(.5)
        self.assertEqual(self.w.process.text(),'Recognise again…')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):self.w.primary_process()
        self.assertEqual(before,self.w.p['cues']);self.assertIsNone(self.w.proc)
        self.assertTrue(self.w.pending_work()[0]);self.assertFalse(self.w.generate_button.isEnabled())

    def test_start_over_cancel_preserves_reviewed_cues(self):
        self.w.p['cues'][0]['reviewed']=True;self.w.collect();before=copy.deepcopy(self.w.p)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No) as ask:self.w.start_over()
        self.assertIn('reviewed',ask.call_args.args[2]);self.assertEqual(self.w.p,before)

    def test_start_over_saves_backup_before_reset(self):
        self.w.p['cues'][0]['reviewed']=True;before=copy.deepcopy(self.w.p['cues'])
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes),patch.object(self.w,'run') as run:
            self.w.start_over();run.assert_called_once_with('process')
        backups=list(Path(self.temp.name).glob('before-reprocess-*.json'))
        self.assertEqual(len(backups),1);self.assertEqual(load_project(backups[0])['cues'],before)
        self.assertEqual(self.w.p['cues'],[])

    def test_translate_again_preserves_reviewed_and_invalidates_unreviewed_cache(self):
        self.w.p['cues'][0].update(reviewed=True,translation_key='keep')
        self.w.p['cues'][1].update(reviewed=False,translation_key='rerun')
        with patch.object(QProcess,'start'):self.w.primary_process()
        saved=load_project(self.w.path)
        self.assertEqual(saved['cues'][0]['translation_key'],'keep')
        self.assertNotIn('translation_key',saved['cues'][1]);self.assertIsNone(saved['approval'])

    def test_resume_keeps_completed_translation_batch_keys(self):
        self.w.p['cues'][0].update(reviewed=False,translation_key='completed-batch')
        with patch.object(QProcess,'start'):self.w.resume.click()
        self.assertEqual(self.w.job_action,'process')
        self.assertEqual(load_project(self.w.path)['cues'][0]['translation_key'],'completed-batch')

    def test_approval_and_edit_gate_export(self):
        self.w.p['preview']['fingerprint']=fingerprint(self.w.p)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):self.w.approve()
        self.assertTrue(self.w.export_button.isEnabled())
        self.w.size.setValue(self.w.size.value()+1)
        self.assertFalse(self.w.export_button.isEnabled());self.assertFalse(self.w.continue_export.isEnabled())

    def test_filters_keep_correct_source_row_mapping(self):
        self.w.p['cues'][0]['reviewed']=True;self.w.p['cues'][1]['reviewed']=False;self.w.refresh()
        self.w.review_filter.setCurrentIndex(3)
        self.assertFalse(self.w.table.isRowHidden(0));self.assertTrue(self.w.table.isRowHidden(1))
        self.w.table.selectRow(0);self.assertEqual(self.w.selected(),0)

    def test_subtitle_only_lists_no_video(self):
        self.w.appearance.setCurrentIndex(2)
        self.assertNotIn('MKV',self.w.output_files.text());self.assertEqual(self.w.export_button.text(),'Export subtitle files')

    def test_refresh_offline_does_not_change_model_or_processing_state(self):
        before=copy.deepcopy(self.w.p)
        with patch('videotranslator.app.installed_models',side_effect=ConnectionError):self.w.refresh_models(quiet=True)
        self.assertIn('unavailable',self.w.model_status.text());self.assertEqual(self.w.p,before)

    def test_setup_translation_button_shows_only_when_ollama_or_the_model_is_missing(self):
        with patch('videotranslator.app.installed_models',side_effect=ConnectionError):self.w.refresh_models(quiet=True)
        self.assertFalse(self.w.ollama_setup.isHidden())
        with patch('videotranslator.app.installed_models',return_value=['other:1b']):self.w.refresh_models(quiet=True)
        self.w.model.setCurrentText('gemma4:12b');self.w.update_model_status();self.assertFalse(self.w.ollama_setup.isHidden())
        self.w.model.setCurrentText('other:1b');self.w.update_model_status();self.assertTrue(self.w.ollama_setup.isHidden())

    def test_setup_translation_runs_the_installer_for_the_chosen_model_and_refuses_odd_names(self):
        self.w.model.setCurrentText('gemma4:12b')
        with patch('subprocess.Popen') as run:self.w.setup_ollama()
        command=run.call_args[0][0];self.assertIn('-OllamaOnly',command);self.assertEqual(command[command.index('-Model')+1],'gemma4:12b')
        self.w.model.setCurrentText('x & calc')
        with patch('subprocess.Popen') as run:self.w.setup_ollama()
        run.assert_not_called();self.assertIn('not valid',self.w.status.text())

    def test_export_destination_display_creates_no_folder(self):
        root=Path(self.temp.name)/'exports';predicted=next_export(root,self.w.p)
        self.assertFalse(root.exists());self.assertEqual(reserve_export(root,self.w.p),predicted)
        self.assertNotEqual(next_export(root,self.w.p),predicted)

    def test_seconds_are_formatted_as_minutes_not_digits(self):
        from videotranslator.app import clock_time
        self.assertEqual(clock_time(1232.447937),'20:32')
        self.assertEqual(clock_time(3752),'1:02:32')

    def test_entire_video_selects_exact_duration_and_custom_remains_available(self):
        self.w.p['media']['duration']=1232.447937
        self.w.end.setValue(752);self.assertFalse(self.w.full_video.isChecked())
        self.w.full_video.setChecked(True);self.w.collect()
        self.assertEqual(self.w.p['range_start'],0)
        self.assertEqual(self.w.p['range_end'],1232.447937)
        self.assertIn('20:32',self.w.range_summary.text())
        self.assertFalse(self.w.end.isEnabled())
        self.w.full_video.setChecked(False);self.assertTrue(self.w.end.isEnabled())

    def test_audio_selection_is_saved_and_requires_recognition(self):
        before=recognition_key(self.w.p)
        self.w.audio_track.addItem('Second test track',1);self.w.audio_track.setCurrentIndex(1)
        self.assertEqual(self.w.p['audio_track'],1);self.assertNotEqual(recognition_key(self.w.p),before)
        self.assertTrue(self.w.pending_work()[0])
        self.w.audio_track.setCurrentIndex(0)
        self.assertEqual(recognition_key(self.w.p),before)

    def test_preview_range_manual_edit_requires_new_render(self):
        self.w.p['preview']['fingerprint']=fingerprint(self.w.p);self.w.p['approval']=fingerprint(self.w.p)
        self.w.preview_start.setValue(4);self.w.preview_start.editingFinished.emit()
        self.assertIsNone(self.w.p['preview']);self.assertFalse(self.w.export_button.isEnabled())

    def test_worker_start_failure_unlocks_workspace(self):
        self.w.tabs.setEnabled(False);self.w.cancel.setEnabled(True)
        self.w.worker_error(QProcess.ProcessError.FailedToStart)
        self.assertTrue(self.w.tabs.isEnabled());self.assertFalse(self.w.cancel.isEnabled())
        self.assertIn('could not start',self.w.status.text())

    def test_speech_decoder_maps_selected_audio_stream(self):
        import wave
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from videotranslator.engine import Worker
        p=copy.deepcopy(self.w.p);p['media']['streams']=[{'codec_type':'audio'},{'codec_type':'audio'}]
        p.update(audio_track=1,device='cpu',cues=[],checkpoints={},range_end=1)
        save_project(p,self.w.path);worker=Worker(self.w.path)
        def audio(args):
            self.assertEqual(args[args.index('-map')+1],'0:a:1')
            with wave.open(str(worker.work/'chunk.wav'),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*160)
        model=MagicMock();model.transcribe.return_value=(iter([]),SimpleNamespace(language='en',language_probability=1))
        with patch.dict('sys.modules',{'faster_whisper':SimpleNamespace(WhisperModel=lambda *a,**k:model)}),patch.object(worker,'command',side_effect=audio) as command:
            worker.speech();self.assertEqual(command.call_count,1)


if __name__=='__main__':unittest.main()
