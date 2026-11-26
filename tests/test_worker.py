import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import numpy  # noqa: F401 -- loaded before patch.dict(sys.modules), which would unload it
from videotranslator.project import new_project,save_project,fingerprint,approved
from videotranslator.engine import Worker,Cancelled
from videotranslator.subtitles import cue

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'project.json'
        self.p=new_project('source.mp4',{'width':640,'height':360,'duration':5,'streams':[]})
        self.p['cues']=[cue(0,2,'Hello',[[100,300,90,20]],.9)]
        self.p['cues'][0]['translation']='مرحبا';save_project(self.p,self.path)
    def tearDown(self):self.temp.cleanup()
    def test_export_requires_real_current_preview_approval(self):
        w=Worker(self.path)
        with self.assertRaisesRegex(ValueError,'approve'):w.render()
        preview=Path(self.temp.name)/'preview.mp4';preview.write_bytes(b'fixture')
        w.p['preview']={'path':str(preview),'fingerprint':fingerprint(w.p)};w.p['approval']=fingerprint(w.p)
        self.assertTrue(approved(w.p))
        w.p['style']['padding']=9;self.assertFalse(approved(w.p))
    def test_cancel_preserves_project(self):
        w=Worker(self.path);w.cancel_path.touch()
        with self.assertRaises(Cancelled):w.check()
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['cues'],self.p['cues'])
    def test_ocr_setting_change_invalidates_only_ocr(self):
        w=Worker(self.path);w.prepare_ocr();w.p['ocr_samples']=[{'time':1}];w.p['checkpoints']['ocr_complete']=True
        w.p['sample_interval']=.5;w.prepare_ocr()
        self.assertEqual(w.p['ocr_samples'],[]);self.assertNotIn('ocr_complete',w.p['checkpoints'])
        self.assertEqual(w.p['cues'],self.p['cues'])
    def test_blank_preview_rejected(self):
        w=Worker(self.path)
        with self.assertRaisesRegex(ValueError,'include translated'):w.render(preview=True,start=3,length=1)
    def test_cover_detection_never_changes_speech_source(self):
        w=Worker(self.path);w.p['ocr_samples']=[{'time':0,'text':'different visible source','boxes':[[2,3,40,12]],'confidence':.8}]
        with patch.object(w,'scan_ocr'):w.covers()
        self.assertEqual(w.p['cues'][0]['original'],'Hello')
        self.assertEqual(w.p['cues'][0]['cover_spans'][0]['boxes'],[[2,3,40,12]])
    def test_recognition_resume_keeps_completed_cues(self):
        w=Worker(self.path);w.prepare_recognition();w.p['cues']=self.p['cues'];w.p['checkpoints']['recognized']=True;w.save()
        with patch.object(w,'speech') as speech:
            w.recognize()
        self.assertEqual(w.p['cues'],self.p['cues'])
    def test_translation_request_is_loopback_only_and_resumes(self):
        w=Worker(self.path)
        result={'message':{'content':json.dumps({'translations':[{'id':0,'translation':'مرحبا','source_language':'en','uncertain':False}],'terms':[]})}}
        response=MagicMock();response.__enter__.return_value=response;response.iter_lines.return_value=[json.dumps(result).encode()]
        with patch('requests.Session') as session:
            session.return_value.post.return_value=response
            response.json.return_value={'details':{'format':'gguf'}}
            w.translate();w.translate()
            chat_calls=[c for c in session.return_value.post.call_args_list if c.args[0].endswith('/chat')]
            self.assertEqual(len(chat_calls),1)
            self.assertEqual(chat_calls[0].args[0],'http://127.0.0.1:11434/api/chat')
            self.assertFalse(session.return_value.trust_env)
            self.assertFalse(session.return_value.post.call_args.kwargs['allow_redirects'])

    def test_no_audio_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError,'no audio track'):Worker(self.path).speech()

    def test_invalid_batch_is_split_and_bad_cue_never_saved(self):
        w=Worker(self.path);w.p['cues'][0]['translation']='';w.p['cues'].append(cue(2,4,'Goodbye',[],.9));w.save()
        response=MagicMock();response.__enter__.return_value=response
        response.json.return_value={'details':{'format':'gguf'}}
        # The model always answers for cue 0 only: cue 1 can never be translated.
        response.iter_lines.return_value=[json.dumps({'message':{'content':json.dumps({'translations':[{'id':0,'translation':'Hi','source_language':'en','uncertain':False}],'terms':[]})}}).encode()]
        with patch('requests.Session') as session:
            session.return_value.post.return_value=response
            with self.assertRaisesRegex(ValueError,'Cue 2 could not be translated'):w.translate()
        saved=json.loads(self.path.read_text(encoding='utf-8'))['cues']
        self.assertEqual([c['translation'] for c in saved],['Hi',''])

    def test_rejected_batch_retries_in_halves(self):
        w=Worker(self.path);w.p['cues'][0]['translation']='';w.p['cues'].append(cue(2,4,'Goodbye',[],.9))
        def reply(ids):
            content={'translations':[{'id':i,'translation':f'T{i}','source_language':'en','uncertain':False} for i in ids],'terms':[]}
            r=MagicMock();r.__enter__.return_value=r;r.iter_lines.return_value=[json.dumps({'message':{'content':json.dumps(content)}}).encode()];return r
        show=MagicMock();show.json.return_value={'details':{'format':'gguf'}}
        with patch('requests.Session') as session:
            # Full batch drops cue 1; the two single-cue retries succeed.
            session.return_value.post.side_effect=[show,reply([0]),reply([0]),reply([1]),MagicMock()]  # last: model unload
            w.translate()
        self.assertEqual([c['translation'] for c in w.p['cues']],['T0','T1'])

    def test_auto_language_locks_after_first_confident_speech_chunk(self):
        import wave
        from types import SimpleNamespace as Obj
        w=Worker(self.path);w.p['range_end']=90;w.p['media']['duration']=90;w.p['media']['streams']=[{'codec_type':'audio'}];w.p['device']='cpu';w.p['cues']=[]
        def audio(*args,**kwargs):
            with wave.open(str(w.work/'chunk.wav'),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*160)
        speech=Obj(text='hi',words=[Obj(word='hi',start=5,end=5.5,probability=1)])
        model=MagicMock();model.transcribe.side_effect=[
            (iter([]),Obj(language='ja',language_probability=.95)),        # music only: confident but no words
            (iter([speech]),Obj(language='en',language_probability=.9)),   # first real speech: lock
            (iter([speech]),Obj(language='en',language_probability=1))]
        with patch.dict('sys.modules',{'faster_whisper':Obj(WhisperModel=lambda *a,**k:model)}),patch.object(w,'command',side_effect=audio):
            w.speech()
        self.assertEqual([c.kwargs['language'] for c in model.transcribe.call_args_list],[None,None,'en'])
        self.assertEqual(w.p['checkpoints']['speech_language'],'en')

    def test_auto_device_falls_back_to_cpu_when_cuda_fails(self):
        from types import SimpleNamespace as Obj
        w=Worker(self.path);w.p['media']['streams']=[{'codec_type':'audio'}];w.p['range_end']=0;w.p['cues']=[]
        devices=[]
        def model(*a,device,**k):
            devices.append(device)
            if device=='cuda':raise RuntimeError('cublas64_12.dll not found')
            return MagicMock()
        with patch.dict('sys.modules',{'faster_whisper':Obj(WhisperModel=model)}),patch('videotranslator.hardware.device_for',return_value='cuda'):
            w.speech()
        self.assertEqual(devices,['cuda','cpu'])
        w.p['device']='cuda';w.p['checkpoints']={}
        with patch.dict('sys.modules',{'faster_whisper':Obj(WhisperModel=model)}),patch('videotranslator.hardware.device_for',return_value='cuda'):
            with self.assertRaisesRegex(RuntimeError,'Select CPU'):w.speech()

    def test_speech_cancel_resume_keeps_boundary_word_once(self):
        import wave
        from types import SimpleNamespace as Obj
        w=Worker(self.path);w.p['range_end']=60;w.p['media']['duration']=60;w.p['media']['streams']=[{'codec_type':'audio'}];w.p['device']='cpu';w.p['cues']=[]
        info=Obj(language='en',language_probability=1)
        def segment(words):return Obj(text='text',words=words)
        first=segment([Obj(word='hello',start=29.5,end=30.2,probability=1)])
        second=segment([Obj(word='hello',start=2.6,end=3.1,probability=1),Obj(word=' world',start=3.2,end=3.6,probability=1)])
        def audio(*args,**kwargs):
            with wave.open(str(w.work/'chunk.wav'),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(b'\0\0'*160)
        model=MagicMock();model.transcribe.side_effect=[(iter([first]),info),(iter([second]),info)]
        def cancel_after_chunk():
            if w.p['checkpoints'].get('speech_cursor',0)>=30:raise Cancelled()
        with patch.dict('sys.modules',{'faster_whisper':Obj(WhisperModel=lambda *a,**k:model)}),patch.object(w,'command',side_effect=audio):
            with patch.object(w,'check',side_effect=cancel_after_chunk):
                with self.assertRaises(Cancelled):w.speech()
            from videotranslator.project import load_project
            w.p=load_project(self.path);w.speech()
        self.assertEqual(' '.join(c['original'] for c in w.p['cues']),'hello world')
        self.assertTrue(w.p['checkpoints']['recognized'])

    def test_cloud_model_rejected_before_text_sent(self):
        w=Worker(self.path)
        with patch('requests.Session') as session:
            session.return_value.post.return_value.json.return_value={'remote_host':'https://ollama.com','details':{'format':'gguf'}}
            with self.assertRaisesRegex(ValueError,'local'):w.translate()
            self.assertEqual(len([c for c in session.return_value.post.call_args_list if c.args[0].endswith('/chat')]),0)

if __name__=='__main__':unittest.main()
