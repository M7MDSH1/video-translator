import io,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import patch,MagicMock
from videotranslator.project import new_project,save_project
from videotranslator.engine import Worker

class OcrFallbackTests(unittest.TestCase):
    def run_case(self,preference='auto',fail_at=1,cpu_fails=False):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        p=new_project('fixture.mp4',{'width':16,'height':16,'duration':.5,'streams':[]})
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
        proc=MagicMock();proc.stdout=io.BytesIO(bytes([17])*16*16*3+bytes([29])*16*16*3)
        # Also prove an unusable CUDA context cannot block CPU cleanup/retry.
        torch=Obj(set_num_threads=lambda n:None,cuda=Obj(empty_cache=MagicMock(side_effect=RuntimeError('CUDA cleanup failed'))))
        with patch.dict('sys.modules',{'easyocr':Obj(Reader=Reader),'torch':torch}),patch('videotranslator.hardware.device_for',return_value='cuda'),patch('videotranslator.engine.subprocess.Popen',return_value=proc):
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
