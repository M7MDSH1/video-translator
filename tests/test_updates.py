"""Update check and install, with GitHub replaced by canned answers."""
import io,os,tempfile,unittest,zipfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from videotranslator import updates

OLD='a'*40;NEW='b'*40
def answer(files,ahead=1,message='Fix the thing\n\nDetails'):
    return {'ahead_by':ahead,'files':[{'filename':f} for f in files],'commits':[{'sha':NEW,'commit':{'message':message}}]*ahead}

class CheckTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'VERSION').write_text(OLD+'\n')
    def check(self,reply):
        self.asked=[]
        def fetch(url):
            self.asked.append(url)
            if isinstance(reply,Exception):raise reply
            return reply
        return updates.check(self.root,fetch)
    def test_newer_desktop_files_offer_the_latest_commit(self):
        self.assertEqual(self.check(answer(['videotranslator/app.py','android/x.kt'])),{'sha':NEW,'message':'Fix the thing'})
        self.assertEqual(self.asked,[f'https://api.github.com/repos/{updates.REPO}/compare/{OLD}...main'])
    def test_nothing_to_offer(self):
        self.assertIsNone(self.check(answer([],ahead=0)))
        self.assertIsNone(self.check(answer(['android/app/x.kt','.github/workflows/android.yml'])))  # only the phone app changed
        self.assertIsNone(self.check(OSError('offline')));self.assertIsNone(self.check({'message':'rate limited'}))
    def test_copy_whose_version_github_no_longer_knows_is_offered_the_newest(self):
        self.assertEqual(self.check(LookupError()),{'sha':'main','message':''})
    def test_git_checkout_uses_its_own_commit_and_stays_quiet_when_unpushed(self):
        (self.root/'VERSION').write_text('$Format:%H$\n')
        with patch.object(updates,'git_head',return_value=OLD):
            self.assertEqual(self.check(answer(['README.md']))['sha'],NEW)
            self.assertIsNone(self.check(LookupError()))  # local work GitHub has not seen
        with patch.object(updates,'git_head',return_value=None):self.assertIsNone(self.check(answer(['README.md'])))

class ApplyTests(unittest.TestCase):
    def test_zip_install_gets_new_files_and_keeps_user_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'VERSION').write_text(OLD);(root/'projects').mkdir();(root/'projects'/'mine.json').write_text('keep')
            (root/'requirements.txt').write_text('same');(root/'old.py').write_text('old')
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w') as z:
                for name,text in (('VERSION',NEW),('requirements.txt','same'),('videotranslator/new.py','new'),('old.py','newer')):z.writestr(f'video-translator-{NEW}/{name}',text)
            ran=[]
            with patch.object(updates,'download',return_value=data.getvalue()) as download,patch.object(updates.subprocess,'run',side_effect=lambda *a,**k:ran.append(a[0])):
                updates.apply(NEW,root)
            self.assertEqual(download.call_args[0][0],f'https://github.com/{updates.REPO}/archive/{NEW}.zip')
            self.assertEqual(((root/'VERSION').read_text(),(root/'old.py').read_text(),(root/'videotranslator'/'new.py').read_text(),(root/'projects'/'mine.json').read_text()),(NEW,'newer','new','keep'))
            self.assertEqual(ran,[])  # same requirements: no package install
    def test_git_checkout_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'VERSION').write_text('$Format:%H$');(root/'.git').mkdir();ran=[]
            with patch.object(updates,'download') as download,patch.object(updates.subprocess,'run',side_effect=lambda *a,**k:ran.append(a[0])):
                updates.apply(NEW,root)
            download.assert_not_called();self.assertEqual(ran,[['git','pull','--ff-only','origin','main']])
    def test_git_update_that_changes_requirements_installs_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'.git').mkdir();(root/'requirements.txt').write_text('old');ran=[]
            def run(command,**k):
                ran.append(command[:3])
                if command[0]=='git':(root/'requirements.txt').write_text('new')
            with patch.object(updates.subprocess,'run',side_effect=run):updates.apply(NEW,root)
            self.assertEqual([c[1:3] for c in ran],[['pull','--ff-only'],['-m','pip']])

class WindowTests(unittest.TestCase):
    def test_found_update_shows_button_and_popup_and_later_keeps_the_button(self):
        from PySide6.QtWidgets import QApplication,QMessageBox
        from videotranslator.app import MainWindow
        app=QApplication.instance() or QApplication([]);w=MainWindow();self.addCleanup(w.close)
        self.assertEqual([b.isHidden() for b in w.update_buttons],[True,True])
        with patch.object(QMessageBox,'exec',return_value=0) as popup,patch('subprocess.Popen') as run:
            w.show_update({'sha':NEW,'message':'Fix the thing'})  # no button clicked counts as Later
        self.assertEqual(popup.call_count,1);run.assert_not_called()
        self.assertEqual([b.isHidden() for b in w.update_buttons],[False,False])
        with patch.object(QMessageBox,'exec',return_value=0),patch.object(QMessageBox,'clickedButton',lambda box:box.buttons()[0]),patch('subprocess.Popen') as run:
            w.update_buttons[0].click()
        self.assertEqual(run.call_args[0][0][1:],['-m','videotranslator.updates',NEW])

class ModelChoiceTests(unittest.TestCase):
    def test_best_measured_model_wins_and_close_scores_go_to_the_faster_one(self):
        from videotranslator.models import best_model
        row=lambda chrf,seconds,bad=0:{'chrf':chrf,'seconds_per_line':seconds,'bad_lines':bad}
        table={'target':'ar','models':{'small':{'languages':{'zh':row(50,1),'ja':row(40,1),'ru':row(60,1,bad=3)}},
                                       'big':{'languages':{'zh':row(51.5,6),'ja':row(47,6),'ru':row(55,6)}},
                                       'gone':{'languages':{'zh':row(90,1)}}}}
        have=['big','gemma4:12b','small']
        self.assertEqual(best_model('zh','ar',have,table),('small',True))   # 1.5 points is a tie: faster wins
        self.assertEqual(best_model('ja','ar',have,table),('big',True))     # 7 points is not
        self.assertEqual(best_model('ru','ar',have,table),('big',True))     # the higher score left lines untranslated
        self.assertEqual(best_model('ko','ar',have,table),('gemma4:12b',False))  # not measured: the usual model
        self.assertEqual(best_model('zh','en',have,table),('gemma4:12b',False))  # measured for another target
        self.assertEqual(best_model('zh','ar',['other'],{}),('other',False));self.assertEqual(best_model('zh','ar',[],{}),('gemma4:12b',False))
    def test_scores_for_other_weights_or_an_older_prompt_are_not_trusted(self):
        import json
        from videotranslator import models
        from videotranslator.translation import REVISION
        row={'chrf':90,'seconds_per_line':1,'bad_lines':0}
        table={'target':'ar','models':{'big':{'digest':'d1','languages':{'zh':row}}}}
        self.assertEqual(models.best_model('zh','ar',{'big':'d1','gemma4:12b':'g'},table),('big',True))
        self.assertEqual(models.best_model('zh','ar',{'big':'d2','gemma4:12b':'g'},table),('gemma4:12b',False))  # same name, new weights
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'runtime').mkdir();path=Path(temp)/'runtime'/'model_scores.json'
            path.write_text(json.dumps(dict(table,revision='older')));self.assertEqual(models.scores(temp),{})
            path.write_text(json.dumps(dict(table,revision=REVISION)));self.assertEqual(models.scores(temp)['target'],'ar')

class AutoModelWindowTests(unittest.TestCase):
    def test_auto_model_stays_translated_after_the_job(self):
        import json
        from PySide6.QtWidgets import QApplication
        from videotranslator.app import MainWindow
        from videotranslator.project import new_project,save_project
        app=QApplication.instance() or QApplication([]);w=MainWindow();self.addCleanup(w.close)
        with tempfile.TemporaryDirectory() as temp:
            p=new_project('unused.mp4',{'width':100,'height':100,'duration':5,'streams':[]})
            p['cues']=[{'start':0,'end':3,'original':'ball','translation':'x','reviewed':False,'flags':[],'boxes':[],'confidence':1}]
            path=Path(temp)/'p.json';save_project(p,path);w.p=p;w.path=path;w.load_ui()
            self.assertEqual(w.model.currentText(),'auto')
            p['model']='gemma4:12b';save_project(p,path)  # what the worker does when it resolves auto
            w.job_action='translate'
            with patch.object(w,'refresh'),patch.object(w,'read_output'),patch.object(w,'end_steps',create=True):w.finished(0,None)
            self.assertEqual(w.model.currentText(),'gemma4:12b');self.assertEqual(w.pending_work(),(False,False))
            w.collect();self.assertEqual(w.p['model'],'gemma4:12b');self.assertEqual(w.pending_work(),(False,False))
    def test_undo_brings_back_placement_and_size_reset_for_all_subtitles(self):
        from PySide6.QtWidgets import QApplication
        from videotranslator.app import MainWindow
        from videotranslator.project import new_project
        app=QApplication.instance() or QApplication([]);w=MainWindow();self.addCleanup(w.close)
        p=new_project('unused.mp4',{'width':100,'height':100,'duration':5,'streams':[]})
        p['cues']=[{'start':0,'end':3,'original':'ball','translation':'x','reviewed':False,'flags':[],'boxes':[],'confidence':1}]
        p['style'].update(caption_offset=[.1,.2],caption_scale=1.5)
        with tempfile.TemporaryDirectory() as temp:
            w.p=p;w.path=Path(temp)/'p.json';w.load_ui();w.stack.setCurrentIndex(1);w.drag_scope.setCurrentIndex(0)
            with patch.object(w,'edit_changed'),patch.object(w,'refresh'):
                w.reset_caption_position();w.reset_caption_size()
                self.assertNotIn('caption_offset',w.p['style']);self.assertNotIn('caption_scale',w.p['style'])
                w.undo();self.assertEqual(w.p['style'].get('caption_scale'),1.5)
                w.undo();self.assertEqual(w.p['style'].get('caption_offset'),[.1,.2])
                w.undo(redo=True);self.assertNotIn('caption_offset',w.p['style'])
            w.autosave.stop()
