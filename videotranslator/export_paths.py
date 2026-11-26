"""Readable, collision-safe Windows export bundles."""
import re
from pathlib import Path
from .project import LANGUAGES

def export_name(p):
    title=Path(p['video']).stem
    # Dots are replaced too: callers append sidecar suffixes with with_suffix.
    title=re.sub(r'[<>:"/\\|?*.\x00-\x1f]',' ',title)
    title=re.sub(r'\s+',' ',title).strip()[:65].rstrip() or 'Video'
    language=next((name for name,code in LANGUAGES.items() if code==p['target']),'Translated')
    return f'{title} - {language}'

def next_export(root,p):
    """Display a destination without reserving or creating any folders."""
    name=export_name(p);root=Path(root).resolve();number=1
    while True:
        folder=root/(name if number==1 else f'{name} ({number})')
        if not folder.exists():return folder/name
        number+=1

def reserve_export(root,p):
    name=export_name(p)
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    number=1
    while True:
        folder=root/(name if number==1 else f'{name} ({number})')
        try:
            folder.mkdir()
            return folder/name
        except FileExistsError:number+=1
