"""Check that this PC has everything the app needs. Changes nothing.

  .venv/Scripts/python.exe tools/self_check.py
"""
import importlib,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import videotranslator  # puts the bundled FFmpeg on PATH

def nvenc():
    r=subprocess.run(['ffmpeg','-hide_banner','-v','error','-f','lavfi','-i','color=s=256x256:d=0.1','-c:v','h264_nvenc','-f','null','-'],capture_output=True)
    return r.returncode==0,'fast export on the graphics card' if r.returncode==0 else 'not available; export uses the processor (slower)'
def gpu():
    from videotranslator.hardware import device_for
    return device_for('speech')=='cuda','speech recognition on the graphics card'
def memory():
    r=subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True)
    used,total=map(int,r.stdout.split('\n')[0].split(','));free=total-used
    return free>=8000,f'{free/1024:.1f} of {total/1024:.1f} GB graphics memory free'+('' if free>=8000 else '; close other AI apps before translating')
def ollama():
    import requests
    s=requests.Session();s.trust_env=False
    names=[m['name'] for m in s.get('http://127.0.0.1:11434/api/tags',timeout=5).json()['models']]
    return bool(names),f'{len(names)} models installed' if names else 'running, but no model installed (ollama pull gemma4:12b)'
def folder(path,what):
    return lambda:(any((ROOT/path).glob('*')) if (ROOT/path).is_dir() else False,what)
CHECKS=[('FFmpeg',lambda:(bool(shutil.which('ffmpeg') and shutil.which('ffprobe')),shutil.which('ffmpeg') or 'not found; run install.ps1')),
        ('Python packages',lambda:([importlib.import_module(m) for m in ('PySide6','faster_whisper','easyocr','requests')] and True,'PySide6, faster-whisper, EasyOCR, requests')),
        ('Speech models',folder('models/whisper','models/whisper (setup_models.py --asr turbo)')),
        ('OCR models',folder('models/ocr','models/ocr (setup_models.py --ocr en)')),
        ('NVIDIA speech',gpu),('NVIDIA video encoder',nvenc),('Graphics memory',memory),('Ollama',ollama)]
REQUIRED={'FFmpeg','Python packages','Ollama'}

def main():
    sys.stdout.reconfigure(encoding='utf-8');failed=False
    for name,check in CHECKS:
        try:ok,detail=check()
        except Exception as exc:ok,detail=False,f'{type(exc).__name__}: {str(exc)[:120]}'
        failed|=not ok and name in REQUIRED
        print(f'{"OK     " if ok else "MISSING" if name in REQUIRED else "note   "} {name:22} {detail}')
    print('\nSomething the app needs is missing; see the MISSING lines.' if failed else '\nReady.');sys.exit(failed)

if __name__=='__main__':main()
