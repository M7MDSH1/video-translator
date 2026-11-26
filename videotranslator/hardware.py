"""Local inference device selection; no downloads or external service changes."""
import os
from pathlib import Path

_dll_handles=[]

def cuda_libraries():
    # Torch's CUDA wheel provides compatible runtime DLLs for CTranslate2 too.
    # Keep directory handles alive for the worker lifetime on Windows.
    if os.name=='nt' and not _dll_handles:
        import importlib.util
        spec=importlib.util.find_spec('torch')
        if spec:
            folder=Path(spec.origin).parent/'lib'
            if folder.exists():
                _dll_handles.append(os.add_dll_directory(str(folder)))
                os.environ['PATH']=str(folder)+os.pathsep+os.environ.get('PATH','')

def device_for(kind,preference='auto'):
    if preference=='cpu':return 'cpu'
    cuda_libraries()
    try:
        if kind=='speech':
            import ctranslate2
            available=ctranslate2.get_cuda_device_count()>0
        else:
            import torch
            available=torch.cuda.is_available()
        if available:return 'cuda'
    except (RuntimeError,OSError):pass
    if preference=='cuda':raise RuntimeError('GPU mode is selected but the CUDA backend is unavailable. Install the app GPU dependencies or select CPU.')
    return 'cpu'
