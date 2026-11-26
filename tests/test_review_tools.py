"""Undo/redo and keyboard helpers in Review, and the worker's Ollama error text."""
import os,tempfile,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl
from test_start_and_youtube import project

class OllamaErrorTests(unittest.TestCase):
    def test_memory_failure_names_the_cause_and_other_errors_are_quoted(self):
        from videotranslator.engine import ollama_error
        text=ollama_error('gemma4:12b','{"error":"llama runner process has terminated: failed to allocate CUDA_Host buffer"}')
        self.assertIn('Not enough free graphics or system memory',text);self.assertIn('Close other AI apps',text)
        self.assertIn('Not enough free',ollama_error('x','{"error":"llama-server reported out-of-memory during startup"}'))  # hyphenated wording
        self.assertNotIn('Not enough free',ollama_error('x','{"error":"bad room name"}'))  # 'oom' only as a whole word
        self.assertEqual(ollama_error('x','{"error":"token repeat limit reached"}'),'Ollama could not run x: token repeat limit reached')
        self.assertEqual(ollama_error('x','<html>bad gateway'),'Ollama could not run x: <html>bad gateway')

class UndoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from videotranslator.app import MainWindow
        self.temp=tempfile.TemporaryDirectory();self.w=MainWindow();self.w.error=lambda e:self.fail(str(e))
        self.w.load_path(str(project(self.temp.name)));self.w.tabs.setCurrentIndex(1)
    def tearDown(self):
        self.w.autosave.stop();self.w.player.stop();self.w.player.setSource(QUrl());self.w.p=None;self.w.close();self.w.deleteLater();self.app.processEvents();self.temp.cleanup()
    def texts(self):return [c['translation'] for c in self.w.p['cues']]
    def test_typing_in_one_line_is_one_undo_step_and_redo_restores_it(self):
        w=self.w;before=self.texts();w.table.selectRow(0)
        w.live_text.setPlainText('a');w.live_text.setPlainText('ab')   # two keystrokes, same line
        w.table.selectRow(1);w.live_text.setPlainText('second')
        w.undo();self.assertEqual(self.texts(),['ab',before[1]])
        w.undo();self.assertEqual(self.texts(),before);self.assertEqual(w.table.item(0,3).text(),before[0])
        w.undo();self.assertEqual(w.status.text(),'Nothing to undo.')
        w.undo(redo=True);w.undo(redo=True);self.assertEqual(self.texts(),['ab','second'])
    def test_delete_and_mark_reviewed_can_be_undone(self):
        w=self.w;w.table.selectRow(0);w.mark_reviewed();w.delete_cue();self.assertEqual(len(w.p['cues']),1)
        w.undo();self.assertEqual(len(w.p['cues']),2);self.assertTrue(w.p['cues'][0]['reviewed'])
        w.undo();self.assertFalse(w.p['cues'][0]['reviewed'])
    def test_ctrl_enter_marks_reviewed_and_moves_to_the_next_unreviewed_line(self):
        w=self.w;w.table.selectRow(0);w.review_and_next()
        self.assertTrue(w.p['cues'][0]['reviewed']);self.assertEqual(w.table.currentRow(),1)
        w.review_and_next();self.assertTrue(w.p['cues'][1]['reviewed']);self.assertEqual(w.table.currentRow(),1)  # last line: stays
    def test_shortcut_keys_reach_their_actions(self):
        from PySide6.QtGui import QShortcut
        keys={s.key().toString() for s in self.w.findChildren(QShortcut)}
        self.assertLessEqual({'Ctrl+Z','Ctrl+Y','Space','Return','Ctrl+Return'},keys)

class CompareDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_command_lists_only_ticked_models_and_needs_a_reference(self):
        from PySide6.QtCore import Qt
        from videotranslator.compare_dialog import CompareDialog
        d=CompareDialog('p.json',['a','b','c'],'b');self.assertEqual(d.chosen(),['b'])
        d.toggle();self.assertIsNone(d.proc);self.assertIn('Choose a reference',d.output.toPlainText())
        d.models.item(2).setCheckState(Qt.CheckState.Checked);d.reference.setText('ref.srt')
        self.assertEqual(d.command()[2:],['p.json','ref.srt','--models','b','c','--count','60'])

if __name__=='__main__':unittest.main()
