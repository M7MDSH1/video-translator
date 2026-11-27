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
