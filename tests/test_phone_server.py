"""Phone mode server: pairing, upload, job progress and resumable download, with the engine process mocked."""
import io,json,tempfile,time,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch,MagicMock
from videotranslator import phone_server
from videotranslator.project import load_project,save_project

class PhoneServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.server=phone_server.PhoneServer(root=self.root,port=0,host='127.0.0.1').start()
    def tearDown(self):self.server.stop();self.temp.cleanup()
    def call(self,method,path,data=None,token=None,headers=None):
        headers=dict(headers or {});token and headers.update(Authorization='Bearer '+token)
        request=urllib.request.Request(f'http://127.0.0.1:{self.server.port}{path}',data=data,method=method,headers=headers)
        try:
            with urllib.request.urlopen(request) as reply:return reply.status,reply.read()
        except urllib.error.HTTPError as error:return error.code,error.read()
    def pair(self):return json.loads(self.call('POST','/pair',json.dumps({'code':self.server.code}).encode())[1])['token']
    def test_requests_need_the_code_from_the_pc(self):
        self.assertEqual(self.call('GET','/status')[0],401)
        self.assertEqual(self.call('GET','/status',token='guess')[0],401)
        self.assertEqual(self.call('POST','/pair',b'{"code":"nope"}')[0],403)
        self.assertEqual(self.call('GET','/status',token=self.pair())[0],200)
        for _ in range(5):self.call('POST','/pair',b'{"code":"nope"}')
        self.assertEqual(self.call('POST','/pair',json.dumps({'code':self.server.code}).encode())[0],429)  # guessing is slowed down
    def test_upload_runs_the_job_and_serves_the_result(self):
        token=self.pair();result=self.root/'out.mp4';result.write_bytes(bytes(range(256))*40)
        def engine(args,**kw):
            project=Path(args[-1]);p=json.loads(project.read_text(encoding='utf-8'));p['last_export']=str(result)
            project.write_text(json.dumps(p),encoding='utf-8')
            proc=MagicMock();proc.stdout=io.StringIO('{"stage": "translate"}\n{"progress": 40, "message": "Translating"}\n');proc.wait.return_value=0;proc.poll.return_value=0
            return proc
        media={'width':1280,'height':720,'duration':5.0,'streams':[]}
        with patch.object(phone_server.subprocess,'Popen',side_effect=engine) as popen,patch('videotranslator.engine.probe',return_value=media),\
             patch.object(phone_server,'load_project',lambda path:json.loads(Path(path).read_text(encoding='utf-8'))):
            status,body=self.call('PUT','/upload?name=..%2F..%2Fbad%3Aname.mp4&mode=ocr',b'video-bytes',token)
            self.assertEqual(status,200,body)
            for _ in range(100):
                job=json.loads(self.call('GET','/status',token=token)[1])
                if job['state']=='done':break
                time.sleep(.05)
        self.assertEqual((job['state'],job['name'],job['result_size']),('done','bad_name.mp4',result.stat().st_size));self.assertNotIn('result',job)
        self.assertEqual(popen.call_args[0][0][1:4],['-m','videotranslator.engine','phone'])
        saved=list(self.root.glob('projects/phone-*/bad_name.mp4'));self.assertEqual(len(saved),1)  # the name cannot leave its folder
        self.assertEqual(saved[0].read_bytes(),b'video-bytes')
        self.assertEqual(json.loads((saved[0].parent/'project.json').read_text(encoding='utf-8'))['mode'],'ocr')
        whole=self.call('GET','/result',token=token);self.assertEqual((whole[0],whole[1]),(200,result.read_bytes()))
        part=self.call('GET','/result',token=token,headers={'Range':'bytes=5000-'});self.assertEqual((part[0],part[1]),(206,result.read_bytes()[5000:]))
    def test_cancel_stops_the_engine_and_what_it_started(self):
        import subprocess,sys
        token=self.pair();real=subprocess.Popen;pids=self.root/'pids.txt'
        # A stand-in engine that starts a child of its own (as the engine starts ffmpeg) and then keeps running.
        code=("import subprocess,sys,time,os;c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
              f"open(r'{pids}','w').write(str(os.getpid())+' '+str(c.pid));print('{{\"stage\": \"translate\"}}',flush=True);time.sleep(60)")
        def engine(args,**kw):return real([sys.executable,'-c',code],**kw) if 'videotranslator.engine' in args else real(args,**kw)
        def alive(pid):
            if phone_server.os.name!='nt':
                try:phone_server.os.kill(pid,0);return True
                except OSError:return False
            return str(pid) in subprocess.run(['tasklist','/FI',f'PID eq {pid}','/NH'],capture_output=True,text=True).stdout
        with patch.object(phone_server.subprocess,'Popen',side_effect=engine),patch('videotranslator.engine.probe',return_value={'width':1280,'height':720,'duration':5.0,'streams':[]}):
            self.assertEqual(self.call('PUT','/upload?name=a.mp4',b'video',token)[0],200)
            for _ in range(200):
                if pids.exists() and len(pids.read_text().split())==2 and json.loads(self.call('GET','/status',token=token)[1])['stage']=='translate':break
                time.sleep(.05)
            engine_pid,child_pid=map(int,pids.read_text().split());self.assertTrue(alive(engine_pid) and alive(child_pid))
            job=json.loads(self.call('POST','/cancel',token=token)[1])
            self.assertEqual((job['state'],job['message']),('error','Cancelled.'))
            for _ in range(100):
                if not alive(engine_pid) and not alive(child_pid):break
                time.sleep(.05)
            self.assertFalse(alive(engine_pid));self.assertFalse(alive(child_pid))
            time.sleep(.3);self.assertEqual(json.loads(self.call('GET','/status',token=token)[1])['message'],'Cancelled.')  # the job thread does not overwrite it
    def test_phone_chooses_languages_and_model(self):
        token=self.pair();media={'width':1280,'height':720,'duration':5.0,'streams':[]};calls=[]
        with patch.object(phone_server,'local_models',return_value=['gemma4:12b','other:4b']):
            options=json.loads(self.call('GET','/options',token=token)[1])
        self.assertEqual(options['models'],['gemma4:12b','other:4b']);self.assertIn({'name':'Chinese','code':'zh'},options['languages'])
        def run(args,**kw):
            calls.append(args[1:]);proc=MagicMock();proc.stdout=io.StringIO('');proc.wait.return_value=0;proc.poll.return_value=0;return proc
        with patch.object(phone_server.subprocess,'Popen',side_effect=run),patch('videotranslator.engine.probe',return_value=media):
            self.assertEqual(self.call('PUT','/upload?mode=ocr&source=zh&target=en&model=other:4b',b'video',token)[0],200)
            for _ in range(100):
                if json.loads(self.call('GET','/status',token=token)[1])['state']!='working':break
                time.sleep(.05)
            self.assertEqual(self.call('PUT','/upload?source=xx',b'video',token)[0],400)
            self.assertEqual(self.call('PUT','/upload?model=bad%20name%3B',b'video',token)[0],400)
        p=load_project(next(self.root.glob('projects/phone-*/project.json')))
        self.assertEqual((p['mode'],p['source'],p['ocr_script'],p['target'],p['model']),('ocr','zh','zh','en','other:4b'))
        # A reader the app does not ship is fetched before the engine starts.
        self.assertEqual(calls[0][1:],['--ocr','zh']);self.assertTrue(calls[0][0].endswith('setup_models.py'));self.assertEqual(calls[1][:3],['-m','videotranslator.engine','phone'])
    def test_rejects_bad_requests(self):
        token=self.pair()
        self.assertEqual(self.call('PUT','/upload?mode=nonsense',b'x',token)[0],400)
        self.assertEqual(self.call('GET','/result',token=token)[0],404)
        with patch.object(phone_server.shutil,'disk_usage',return_value=MagicMock(free=10)):
            self.assertEqual(self.call('PUT','/upload?name=a.mp4',b'x',token)[0],507)

class PhoneExportTests(unittest.TestCase):
    def test_phone_export_is_a_small_mp4_and_needs_no_approval(self):
        from videotranslator import engine
        from test_start_and_youtube import project
        with tempfile.TemporaryDirectory() as d:
            worker=engine.Worker(project(d));calls=[]
            def command(args,duration=0,label=''):calls.append(args);Path(args[-1]).write_bytes(b'x')
            worker.command=command
            with patch.object(engine,'ROOT',Path(d)),patch('sys.stdout'):worker.render(phone=True)
            args=calls[0];self.assertTrue(load_project(worker.path)['last_export'].endswith('.mp4'))
            self.assertIn("scale='if(gt(iw,ih),-2,720)'",args[args.index('-vf')+1]);self.assertEqual(args[args.index('-maxrate')+1],'3M');self.assertEqual(args[args.index('-c:a')+1],'aac');self.assertIn('+faststart',args)
            with patch.object(engine,'ROOT',Path(d)),self.assertRaisesRegex(ValueError,'approve'):worker.render()  # the desktop export still needs approval

class PhoneDialogTests(unittest.TestCase):
    def test_window_shows_address_code_and_every_job_state(self):
        import os;os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication,QLabel
        from videotranslator.phone_dialog import PhoneDialog
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as d:
            server=phone_server.PhoneServer(root=Path(d),port=0,host='127.0.0.1').start()
            try:
                dialog=PhoneDialog(server);texts=' '.join(label.text() for label in dialog.findChildren(QLabel))
                self.assertIn(' '.join(server.code),texts);self.assertIn(str(server.port),texts)
                self.assertIn('Waiting',dialog.state.text());self.assertTrue(dialog.bar.isHidden())
                server.set(state='working',stage='translate',progress=40,name='clip.mp4');dialog.refresh()
                self.assertIn('Translating',dialog.state.text());self.assertEqual(dialog.bar.value(),40);self.assertFalse(dialog.bar.isHidden())
                server.set(state='done',stage='done');dialog.refresh();self.assertIn('download',dialog.state.text())
                server.set(state='error',message='No dialogue found');dialog.refresh();self.assertIn('No dialogue found',dialog.state.text())
                dialog.timer.stop();dialog.deleteLater()
            finally:server.stop()

if __name__=='__main__':unittest.main()
