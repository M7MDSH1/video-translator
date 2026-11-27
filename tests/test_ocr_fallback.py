import io,tempfile,unittest
import numpy  # before the tests swap sys.modules: it cannot be imported twice in one process
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import patch,MagicMock
from videotranslator.project import new_project,save_project
from videotranslator.engine import Worker

class OcrFallbackTests(unittest.TestCase):
    def run_case(self,preference='auto',fail_at=1,cpu_fails=False,empty=(),count=2):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        p=new_project('fixture.mp4',{'width':16,'height':16,'duration':count/4,'streams':[]})
        p.update(mode='ocr',device=preference,roi=[0,0,1,1],sample_interval=.25)
        path=Path(self.temp.name)/'p.json';save_project(p,path);w=Worker(path)
        attempts=[];frames=[];gpu_calls=0
        class Reader:
            def __init__(self,*args,gpu,**kwargs):self.gpu=gpu;attempts.append(gpu)
            def readtext(self,frame,**kwargs):
                nonlocal gpu_calls
                frames.append((self.gpu,int(frame[0,0,0])))
                if self.gpu:
                    gpu_calls+=1
                    if gpu_calls==fail_at:raise RuntimeError('CUDA first convolution failed')
                elif cpu_fails:raise RuntimeError('CPU recognition failed')
                return []
        proc=MagicMock();proc.stdout=io.BytesIO(bytes([17])*16*16*3+bytes([29])*16*16*3*(count-1))
        # Also prove an unusable CUDA context cannot block CPU cleanup/retry.
        torch=Obj(set_num_threads=lambda n:None,cuda=Obj(empty_cache=MagicMock(side_effect=RuntimeError('CUDA cleanup failed'))))
        with patch.dict('sys.modules',{'easyocr':Obj(Reader=Reader),'torch':torch}),patch('videotranslator.hardware.device_for',return_value='cuda'),patch('videotranslator.engine.subprocess.Popen',return_value=proc),patch('videotranslator.engine.no_text',side_effect=lambda reader,frame:int(frame[0,0,0]) in empty) as self.gate:
            try:w.scan_ocr();error=None
            except RuntimeError as exc:error=str(exc)
        self.assertTrue(proc.kill.called)
        return w,attempts,frames,error
    def test_auto_retries_first_frame_on_cpu_without_duplicate_samples(self):
        w,attempts,frames,error=self.run_case()
        self.assertIsNone(error);self.assertEqual(attempts,[True,False])
        self.assertEqual(frames,[(True,17),(False,17),(False,29)])
        self.assertEqual([s['time'] for s in w.p['ocr_samples']],[0,.25])
        self.assertEqual(w.p['checkpoints']['ocr_device'],'cpu')
    def test_later_failure_preserves_completed_frame(self):
        w,attempts,frames,error=self.run_case(fail_at=2)
        self.assertIsNone(error);self.assertEqual(frames,[(True,17),(True,29),(False,29)])
        self.assertEqual(len(w.p['ocr_samples']),2)
    def test_explicit_gpu_does_not_silently_fall_back(self):
        w,attempts,frames,error=self.run_case('cuda')
        self.assertEqual(attempts,[True]);self.assertIn('first convolution',error)
        self.assertEqual(w.p['ocr_samples'],[])
    def test_cpu_failure_remains_actionable_and_does_not_save_failed_frame(self):
        w,attempts,frames,error=self.run_case(cpu_fails=True)
        self.assertEqual(error,'CPU recognition failed');self.assertEqual(w.p['ocr_samples'],[])
    def test_frame_without_text_skips_the_full_read_but_keeps_its_sample(self):
        w,attempts,frames,error=self.run_case(fail_at=0,empty=(17,))
        self.assertIsNone(error);self.assertEqual(frames,[(True,29)])
        self.assertEqual([(s['time'],s['text'],s['boxes']) for s in w.p['ocr_samples']],[(0,'',[]),(.25,'',[])])
        self.assertEqual(w.p['checkpoints']['ocr_cursor'],.5)
    def test_quick_test_pauses_when_it_rarely_skips(self):
        w,attempts,frames,error=self.run_case(fail_at=0,count=260)
        self.assertIsNone(error);self.assertEqual(len(frames),260);self.assertEqual(self.gate.call_count,200)

class ChineseScriptTests(unittest.TestCase):
    def test_the_surer_chinese_reader_is_kept(self):
        from videotranslator import engine
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'models'/'ocr').mkdir(parents=True);(root/'models'/'ocr'/'chinese.pth').write_bytes(b'')
            p=new_project('fixture.mp4',{'width':16,'height':16,'duration':40,'streams':[]});p.update(mode='ocr',roi=[0,0,1,1],ocr_script='zh')
            path=root/'p.json';save_project(p,path);w=Worker(path)
            class Reader:
                def __init__(self,langs,**kwargs):self.sure=.9 if langs[0]=='ch_tra' else .1
                def readtext(self,frame,**kwargs):return [(None,'x',self.sure)]
            frame=Obj(stdout=bytes(16*16*3))
            with patch.dict('sys.modules',{'easyocr':Obj(Reader=Reader)}),patch.object(engine,'ROOT',root),patch.object(engine.subprocess,'run',return_value=frame) as grab:
                self.assertEqual(w.chinese_script('cpu'),'ch_tra');self.assertEqual(grab.call_count,40)
                self.assertEqual(w.chinese_script('cpu'),'ch_tra');self.assertEqual(grab.call_count,40)  # decided once per project
    def test_named_chinese_script_is_used_without_checking(self):
        from videotranslator import engine
        with tempfile.TemporaryDirectory() as temp:
            p=new_project('fixture.mp4',{'width':16,'height':16,'duration':.25,'streams':[]});p.update(mode='ocr',roi=[0,0,1,1],ocr_script='zh-tw',device='cpu')
            path=Path(temp)/'p.json';save_project(p,path);w=Worker(path);loaded=[]
            class Reader:
                def __init__(self,langs,**kwargs):loaded.append(langs)
                def readtext(self,frame,**kwargs):return []
            proc=MagicMock();proc.stdout=io.BytesIO(bytes(16*16*3))
            torch=Obj(set_num_threads=lambda n:None,cuda=Obj(empty_cache=lambda:None))
            with patch.dict('sys.modules',{'easyocr':Obj(Reader=Reader),'torch':torch}),patch('videotranslator.hardware.device_for',return_value='cpu'),\
                 patch('videotranslator.engine.subprocess.Popen',return_value=proc),patch.object(w,'chinese_script') as check:
                w.scan_ocr()
            self.assertEqual(loaded,[['ch_tra','en']]);check.assert_not_called()

class RotatedVideoTests(unittest.TestCase):
    def test_sizes_describe_the_upright_picture_ffmpeg_decodes(self):
        import subprocess
        from videotranslator.engine import probe
        with tempfile.TemporaryDirectory() as temp:
            plain=str(Path(temp)/'plain.mp4');turned=str(Path(temp)/'turned.mp4')
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=320x240:d=1','-pix_fmt','yuv420p',plain],check=True)
            subprocess.run(['ffmpeg','-v','error','-y','-display_rotation','90','-i',plain,'-c','copy',turned],check=True)  # how phones store portrait video
            media=probe(turned);self.assertEqual((media['width'],media['height']),(240,320))
            self.assertEqual((probe(plain)['width'],probe(plain)['height']),(320,240))
            # The default subtitle area, cut the way the scan cuts it, must fit the decoded frame.
            p=new_project(turned,media);w,h=media['width'],media['height'];rx,ry,rw,rh=p['roi'];x,y=int(rx*w),int(ry*h);cw,ch=int((rx+rw)*w)-x,int((ry+rh)*h)-y
            frame=subprocess.run(['ffmpeg','-v','error','-i',turned,'-frames:v','1','-vf',f'crop={cw}:{ch}:{x}:{y}:exact=1','-pix_fmt','bgr24','-f','rawvideo','pipe:1'],capture_output=True)
            self.assertEqual(len(frame.stdout),cw*ch*3,frame.stderr[-200:])
