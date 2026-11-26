"""Offline video translation for Windows."""
import os
from pathlib import Path

_ffmpeg=Path(__file__).resolve().parent.parent/'runtime'/'ffmpeg'/'bin'
if _ffmpeg.is_dir():os.environ['PATH']=str(_ffmpeg)+os.pathsep+os.environ.get('PATH','')
