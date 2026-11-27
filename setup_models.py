"""Explicit setup-only downloads; normal processing never downloads weights."""
from pathlib import Path
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['HF_HUB_DISABLE_XET']='1'
os.environ.pop('HF_HUB_OFFLINE',None)
from faster_whisper import WhisperModel
import easyocr

import argparse
parser=argparse.ArgumentParser();parser.add_argument('--asr',default='turbo',choices=['small','turbo','large-v3']);parser.add_argument('--ocr',default=None)
args=parser.parse_args()
root=Path(__file__).resolve().parent/'models'
if not args.ocr:
    print(f'Downloading Whisper {args.asr} from Hugging Face',flush=True)
    WhisperModel(args.asr,device='cpu',compute_type='int8',download_root=str(root/'whisper'))
print('Downloading English/Arabic EasyOCR weights from official GitHub releases',flush=True)
# Chinese gets both readers: the engine picks Simplified or Traditional per video.
languages=([['en']] if args.ocr=='en' else [['ch_sim','en'],['ch_tra','en']] if args.ocr=='zh' else [[{'zh-cn':'ch_sim','zh-tw':'ch_tra'}.get(args.ocr,args.ocr),'en']]) if args.ocr and args.ocr!='auto' else (['en'],['ar','en'])
for langs in languages:
    easyocr.Reader(langs,gpu=False,model_storage_directory=str(root/'ocr'),verbose=False)
print('Offline models ready.',flush=True)
