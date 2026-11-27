"""Which translation model to use when the user leaves the choice on 'auto'. Standard library only.

Scores come from tools/rank_models.py, which measures the models installed on this PC and writes
runtime/model_scores.json. Without that file, or for a language it did not measure, the usual model is used.
"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULT='gemma4:12b'
TIE=2.  # chrF points; on a 30-line sample smaller gaps are noise, so they go to the faster model

def local_digests():
    """{name: digest} of the translation models installed in Ollama on this PC; empty when Ollama is not running."""
    import urllib.request
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as reply:found=json.loads(reply.read()).get('models',[])
    except (OSError,ValueError):return {}
    return {m['name']:m.get('digest') for m in found if not m.get('remote_host') and not m.get('remote_model') and 'cloud' not in m['name'].lower()}

def local_models():return sorted(local_digests())

def scores(root=ROOT):
    """The saved measurements, or nothing when they were made with an older translation prompt."""
    from .translation import REVISION
    try:table=json.loads((Path(root)/'runtime'/'model_scores.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}
    return table if isinstance(table,dict) and table.get('revision')==REVISION else {}

def best_model(source,target,installed,table):
    """The installed model measured best for source -> target; close scores go to the faster one.
    [installed] is {name: digest} (or just names): a score counts only for the weights it was measured on,
    since a name can be re-downloaded as a different model.
    Returns (name, measured): measured is False when there was nothing to go on and the usual model is returned."""
    usual=DEFAULT if DEFAULT in installed or not installed else sorted(installed)[0]
    if table.get('target')!=target:return usual,False
    same=lambda name,m:not isinstance(installed,dict) or m.get('digest')==installed[name]
    rows=[(name,m['languages'][source]) for name,m in table.get('models',{}).items() if name in installed and same(name,m) and source in m.get('languages',{})]
    # A model that left lines empty or untranslated is not a candidate, whatever its score.
    rows=[(name,r) for name,r in rows if not r.get('bad_lines')]
    if not rows:return usual,False
    top=max(r['chrf'] for _,r in rows)
    return min(((name,r) for name,r in rows if r['chrf']>=top-TIE),key=lambda item:(item[1]['seconds_per_line'],item[0]))[0],True

def choose(p):
    """Resolves a project's 'auto' model once the language is known (speech mode learns it during recognition)."""
    cp=p.get('checkpoints',{});source=p['source']
    if source=='auto':source=cp.get('speech_language') or (p['ocr_script'] if p['mode']=='ocr' else '')
    return best_model(source.split('-')[0],p['target'],local_digests(),scores())  # scores are per language, not per script
