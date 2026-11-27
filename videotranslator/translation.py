"""Batch contracts keep model output attached to the correct timed cue."""
import hashlib
import json
import re
from collections import Counter

# 2: names translated before dialogue and OCR underscores cleaned; retranslates unreviewed cues.
REVISION='2'
# Already-translated lines shown to the model before each batch.
CONTEXT=8

def translation_key(c,p):
    glossary=json.dumps(p.get('glossary',{}),sort_keys=True,ensure_ascii=False) if p.get('glossary') else ''
    return hashlib.sha256((c['original']+p['target']+p['source']+p['model']+glossary+REVISION).encode()).hexdigest()

def clean_ocr(text):
    # OCR reads the subtitle ellipsis as '_', '__' or '_.'; no subtitle needs an underscore.
    return re.sub(r'\s*_+\.?','...',text)

def clean_source(text):
    # OCR also reads a lone "I" as "|" or "/" ("But / accidentally"). Source only: translations may use "/".
    return clean_ocr(re.sub(r'(?<!\S)[|/](?!\S)','I',text))

def candidate_terms(cues,limit=150):
    """Speaker labels and mid-sentence capitalised names, with one example line each.

    Translating these first keeps e.g. a character called "Soul" from becoming
    "the soul" in the batches that run before the term list has learned it.
    """
    counts=Counter();examples={};speakers=set()
    for c in cues:
        lines=[l.strip() for l in clean_source(c['original']).split('\n') if l.strip()]
        # A name is written with capitals ("Swordsman Captain"); a first line with lowercase words ("I need your help")
        # is a sentence that continues on the next line, and must be translated, not spelled out.
        # shortcut: a one-word capitalised first line ("Wait") still passes; tell them apart by repetition if it shows up.
        if len(lines)>1 and len(lines[0].split())<=5 and not re.search(r'[.!?,:;]$',lines[0]) and not any(word[:1].islower() for word in lines[0].split()):
            speakers.add(lines[0]);counts[lines[0]]+=1;examples.setdefault(lines[0],' '.join(lines[1:]));lines=lines[1:]
        body=' '.join(lines)
        for m in re.finditer(r"\b[A-Z][\w'-]+(?:[ -](?:of |the )?[A-Z][\w'-]+)*",body):
            term=m.group();before=body[:m.start()].rstrip()
            if not before or before[-1] in '.!?"“':
                # Sentence start: the first word is capitalised anyway ("The Four Axes").
                if ' ' not in term:continue
                term=term.split(' ',1)[1]
                if not term[:1].isupper():continue
            counts[term]+=1;examples.setdefault(term,body)
    keep=[t for t,n in counts.most_common() if t in speakers or ' ' in t or '-' in t or n>=2][:limit]
    return [{'term':t,'speaker':t in speakers,'example':examples[t][:200]} for t in keep]

def batches(entries,max_count=12,max_chars=6000):
    batch=[];size=0
    for entry in entries:
        length=len(entry[1]['original'])
        if batch and (len(batch)>=max_count or size+length>max_chars):
            yield batch;batch=[];size=0
        batch.append(entry);size+=length
    if batch:yield batch

SCHEMA={'type':'object','properties':{
    'translations':{'type':'array','items':{'type':'object','properties':{
        'id':{'type':'integer'},'translation':{'type':'string'},'source_language':{'type':'string'},'uncertain':{'type':'boolean'}},
        'required':['id','translation','source_language','uncertain']}},
    'terms':{'type':'array','items':{'type':'object','properties':{'source':{'type':'string'},'translation':{'type':'string'}},'required':['source','translation']}}
},'required':['translations','terms']}
TERMS_SCHEMA={'type':'object','properties':{'terms':SCHEMA['properties']['terms']},'required':['terms']}

def validate_batch(result,ids):
    if not isinstance(result,dict) or not isinstance(result.get('terms',[]),list):
        raise ValueError('Invalid translation batch; no changes saved.')
    entries=result.get('translations')
    if not isinstance(entries,list):raise ValueError('Translation batch has no result list; retry the batch.')
    mapped={}
    for item in entries:
        if not isinstance(item,dict) or type(item.get('id')) is not int or item['id'] not in ids or item['id'] in mapped:
            raise ValueError('Translation batch contains missing, duplicate, or unexpected cue IDs; no changes saved.')
        if not isinstance(item.get('translation'),str) or not item['translation'].strip():raise ValueError('Translation batch contains empty text; no changes saved.')
        if not isinstance(item.get('source_language'),str) or type(item.get('uncertain')) is not bool:raise ValueError('Invalid translation metadata; no changes saved.')
        mapped[item['id']]=item
    if set(mapped)!=set(ids):raise ValueError('Translation batch omitted cues; no changes saved.')
    return mapped
