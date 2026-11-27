import copy
import json
import tempfile
from pathlib import Path
from unittest.mock import patch,MagicMock
import unittest
from videotranslator.replacements import replace_text,apply_replacements,validate_rules

def settings(*pairs,**options):
    return dict(enabled=True,match_case=False,whole_words=True,rules=[dict(find=a,replace=b) for a,b in pairs],**options)

class ReplacementTests(unittest.TestCase):
    def test_words_and_case(self):
        self.assertEqual(replace_text('Football, footballer, FOOTBALL!',settings(('football','soccer'))),('soccer, footballer, soccer!',2))
    def test_literal_and_longest_phrase_no_cascade(self):
        rules=settings(('football','soccer'),('football club','blorp'),('soccer','xyz'),('C++','code'))
        self.assertEqual(replace_text('football club, football, soccer, C++',rules),('blorp, soccer, xyz, code',4))
    def test_arabic_and_wrapped_phrase(self):
        self.assertEqual(replace_text('كرة\nالقدم، والقدم. كرة القدم!',settings(('كرة القدم','زومبا'))),('زومبا، والقدم. زومبا!',2))
    def test_short_arabic_word_does_not_match_inside_others(self):
        self.assertEqual(replace_text('كما قلت، لما وصل، ما هذا؟',settings(('ما','X'))),('كما قلت، لما وصل، X هذا؟',1))
        self.assertEqual(replace_text('وبالكرة',settings(('كرة','زومبا'))),('وبالزومبا',1))  # three letters keep prefixes
    def test_deletion_closes_the_gap(self):
        self.assertEqual(replace_text('وكرة القدم ممتعة',settings(('كرة',''))),('القدم ممتعة',1))
        self.assertEqual(replace_text('قال سول ابدأ .\nسول',settings(('سول',''))),('قال ابدأ.',2))
        self.assertEqual(replace_text('هل أنت بخير ؟  نعم',settings(('ليس',''))),('هل أنت بخير ؟  نعم',0))  # untouched without a deletion
    def test_case_and_substring_options(self):
        rule=settings(('ball','X'));rule.update(whole_words=False,match_case=True)
        self.assertEqual(replace_text('football BALL',rule),('footX BALL',1))
    def test_invalid_rules(self):
        for rule in (settings(('','x')),settings(('A','x'),('a','y'))):
            with self.assertRaises(ValueError):validate_rules(rule)
    def test_arabic_prefixes_and_marks(self):
        source='كرة وكرة فَكُرَةً الكرة بالكرة كالكرة للكرة وبالكرة فالكرة كرةً كرتان فكرة'
        result='زومبا وزومبا فَزومبا الزومبا بالزومبا كالزومبا للزومبا وبالزومبا فالزومبا زومبا كرتان فزومبا'
        self.assertEqual(replace_text(source,settings(('كرة','زومبا'))),(result,11))
    def test_arabic_phrase_prefix_and_explicit_longer_rule(self):
        rules=settings(('كرة القدم','زومبا'),('الكرة','لعبة'))
        self.assertEqual(replace_text('وبِكُرةِ\nالقدمِ الكرة كرتي',rules),('وبِزومبا لعبة كرتي',2))
    def test_deletion_consumes_attached_prefix_and_marks(self):
        self.assertEqual(replace_text('وكرةً، كرة!',settings(('كرة',''))),('،!',2))
        self.assertEqual(replace_text('football footballer',settings(('football',''))),('footballer',1))
    def test_duplicate_arabic_vowel_variants_rejected(self):
        with self.assertRaises(ValueError):validate_rules(settings(('كرة','a'),('كُرَة','b')))
    def test_restoring_removes_only_rule_warnings(self):
        p={'replacements':settings(('كرة','زومبا')),'cues':[{'translation':'كرة','reviewed':False,'flags':['Low OCR confidence']}]}
        apply_replacements(p);p['replacements']['rules']=[];apply_replacements(p)
        self.assertEqual(p['cues'][0]['translation'],'كرة')
        self.assertEqual(p['cues'][0]['flags'],['Low OCR confidence'])
    def test_full_cue_deletion_can_render_and_restore(self):
        from videotranslator.project import new_project,validate
        from videotranslator.subtitles import make_srt,make_ass,display_cues
        p=new_project('unused.mp4',{'width':640,'height':360,'duration':5,'streams':[]})
        p.update(appearance='replace',replacements=settings(('كرة','')))
        p['cues']=[{'start':1,'end':1.5,'translation':'وكرةً','original':'ball','reviewed':False,'flags':[],'boxes':[[10,250,100,40]]}]
        apply_replacements(p);validate(p,render=True)
        self.assertEqual(make_srt(p).strip(),'');self.assertIn('Dialogue: 0',make_ass(p));self.assertNotIn('Dialogue: 1',make_ass(p))
        self.assertEqual(display_cues(p)[0][1]['end'],1.5)
        p['replacements']['enabled']=False;apply_replacements(p)
        self.assertEqual(p['cues'][0]['translation'],'وكرةً')
        p['cues'][0]['translation']=''
        with self.assertRaises(ValueError):validate(p,render=True)
    def test_apply_resume_restore_and_reviewed(self):
        p={'replacements':settings(('football','soccer'),('soccer','blorp')),'cues':[{'original':'football','translation':'football','reviewed':False},{'original':'football','translation':'football','reviewed':True}]}
        self.assertEqual(apply_replacements(p),1);self.assertEqual(p['cues'][0]['translation'],'soccer')
        self.assertEqual(apply_replacements(p),0);self.assertEqual(p['cues'][0]['translation'],'soccer')
        self.assertEqual(p['cues'][1]['translation'],'football');self.assertEqual(p['cues'][0]['original'],'football')
        p['replacements']['enabled']=False
        self.assertEqual(apply_replacements(p),1);self.assertEqual(p['cues'][0]['translation'],'football')
    def test_manual_edits_become_baseline(self):
        p={'replacements':settings(('football','soccer')),'cues':[{'translation':'football','reviewed':False}]}
        apply_replacements(p);p['cues'][0]['translation']='my corrected soccer'
        p['replacements']['rules']=[];apply_replacements(p)
        self.assertEqual(p['cues'][0]['translation'],'my corrected soccer')
    def test_explicit_include_reviewed_invalidates_review(self):
        p={'replacements':settings(('football','nonsense')),'cues':[{'translation':'football','reviewed':True}]}
        self.assertEqual(apply_replacements(p,include_reviewed=True),1)
        self.assertFalse(p['cues'][0]['reviewed'])

    def test_worker_applies_after_model_and_resume_never_cascades(self):
        from videotranslator.project import new_project,save_project,load_project
        from videotranslator.engine import Worker
        p=new_project('unused.mp4',{'width':100,'height':100,'duration':5,'streams':[]})
        p.update(replacements=settings(('football','soccer'),('soccer','blorp')))
        p['cues']=[{'start':0,'end':3,'original':'football','translation':'','reviewed':False,'flags':[]}]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'project.json';save_project(p,path)
            response=MagicMock();response.__enter__.return_value=response
            response.json.return_value={'details':{'format':'gguf'}}
            response.iter_lines.return_value=[json.dumps({'message':{'content':json.dumps({'translations':[{'id':0,'translation':'football','source_language':'en','uncertain':False}],'terms':[]})}}).encode()]
            with patch('requests.Session') as session:
                session.return_value.post.return_value=response
                worker=Worker(path);worker.translate();worker.translate()
            saved=load_project(path)
            self.assertEqual(saved['cues'][0]['translation'],'soccer')
            self.assertEqual(saved['cues'][0]['original'],'football')

    def test_deleted_cached_cue_is_not_retranslated_on_resume(self):
        from videotranslator.project import new_project,save_project
        from videotranslator.translation import translation_key
        from videotranslator.engine import Worker
        p=new_project('unused.mp4',{'width':100,'height':100,'duration':5,'streams':[]});p['model']='gemma4:12b'
        p['cues']=[{'start':0,'end':3,'original':'ball','translation':'وكرةً','reviewed':False,'flags':[]}]
        p['cues'][0]['translation_key']=translation_key(p['cues'][0],p)
        p['replacements']=settings(('كرة',''));apply_replacements(p)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'project.json';save_project(p,path)
            with patch('requests.Session') as session:
                session.return_value.post.return_value.json.return_value={'details':{'format':'gguf'}}
                Worker(path).translate()
                urls=[call.args[0] for call in session.return_value.post.call_args_list]
                self.assertEqual(urls,['http://127.0.0.1:11434/api/show'])

class ReplacementDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_preview_cancel_is_nonmutating(self):
        from videotranslator.replacement_dialog import ReplacementDialog
        p={'cues':[{'start':0,'translation':'Football','reviewed':False}]};before=copy.deepcopy(p)
        d=ReplacementDialog(p);d.table.item(0,0).setText('football');d.table.item(0,1).setText('soccer')
        self.assertIn('1 subtitle would change',d.result.toPlainText());self.assertIn('soccer',d.result.toPlainText())
        d.reject();self.assertEqual(p,before)

    def test_arabic_preview_has_separate_directional_before_after_and_no_arrow(self):
        from videotranslator.replacement_dialog import ReplacementDialog,text_html
        p={'cues':[{'start':0,'translation':'وكرةً','reviewed':False}]}
        d=ReplacementDialog(p);d.table.item(0,0).setText('كرة');d.table.item(0,1).setText('زومبا')
        text=d.result.toPlainText()
        self.assertIn('Before',text);self.assertIn('After',text);self.assertIn('وزومبا',text);self.assertNotIn('→',text)
        self.assertIn('dir="rtl"',text_html('وكرةً'));self.assertIn('&lt;',text_html('<tag>'))
        d.table.item(0,1).setText('');self.assertIn('Removed',d.result.toPlainText());self.assertTrue(d.preview());d.reject()

    @unittest.skipUnless((Path(__file__).resolve().parent.parent/'projects'/'test-ocr'/'project.json').is_file(),'needs the local sample project projects/test-ocr, which is not in the repository')
    def test_app_apply_updates_live_invalidates_preview_and_reopens(self):
        from videotranslator.app import MainWindow
        from videotranslator.replacement_dialog import ReplacementDialog
        from videotranslator.project import fingerprint,load_project
        from PySide6.QtCore import QUrl
        w=MainWindow();w.load_path('projects/test-ocr/project.json')
        with tempfile.TemporaryDirectory() as tmp:
            w.path=Path(tmp)/'project.json';w.p['cues'][0].update(translation='football',reviewed=False)
            before=[c['original'] for c in w.p['cues']]
            w.p['preview']['fingerprint']=fingerprint(w.p);w.p['approval']=fingerprint(w.p)
            def edit(d):
                d.table.item(0,0).setText('football');d.table.item(0,1).setText('soccer');d.finish(True);return 1
            try:
                with patch.object(ReplacementDialog,'exec',edit):w.edit_replacements()
                self.assertEqual(w.video.project['cues'][0]['translation'],'soccer')
                self.assertEqual([c['original'] for c in w.p['cues']],before)
                self.assertFalse(w.export_button.isEnabled())
                saved=load_project(w.path);self.assertEqual(saved['replacements']['rules'][0]['replace'],'soccer')
                self.assertEqual(saved['cues'][0]['translation'],'soccer')
            finally:w.autosave.stop();w.player.stop();w.player.setSource(QUrl());w.p=None;w.close();w.deleteLater();self.app.processEvents()

if __name__=='__main__':unittest.main()
