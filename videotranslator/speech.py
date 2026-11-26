"""Timed-word ownership and readable caption grouping for overlapping ASR windows."""
import re
from .subtitles import cue

def normalize_word(text):
    return re.sub(r'[^\w]', '', text, flags=re.UNICODE).casefold()

def own_words(words, tail, start, stop):
    """Reconcile the decoded overlap against committed words, then keep new words.

    A matching suffix anchors the new window even if Whisper moves a word across
    the nominal boundary. Time proximity prevents matching a distant repetition.
    """
    cut=None
    for size in range(min(6,len(tail)),0,-1):
        expected=[normalize_word(w['text']) for w in tail[-size:]]
        if not all(expected):continue
        for i in range(len(words)-size+1):
            candidate=words[i:i+size]
            if ([normalize_word(w['text']) for w in candidate]==expected
                    and abs(candidate[-1]['end']-tail[-1]['end'])<1):
                cut=i+size;break
        if cut is not None:break
    candidates=words[cut:] if cut is not None else words
    floor=tail[-1]['end'] if tail else start
    result=[]
    for word in candidates:
        midpoint=(word['start']+word['end'])/2
        if midpoint>=stop:break
        if cut is None and midpoint<max(start,floor):continue
        if word['end']<=floor:continue
        word=dict(word);word['start']=max(floor,word['start']);result.append(word)
        floor=word['end']
    return result

def word_text(words,language):
    if language in ('zh','ja'):return ''.join(w['text'].strip() for w in words)
    return ''.join(w['text'] if w['text'].startswith(' ') or i==0 or re.match(r'^[,.;:!?؟،。！？]',w['text']) else ' '+w['text'] for i,w in enumerate(words)).strip()

def split_words(words,language,max_duration=6.,max_chars=84,max_cps=20.):
    groups=[];group=[]
    for word in words:
        if group and (word['end']-group[0]['start']>max_duration
                or len(word_text(group+[word],language))>max_chars
                or word['start']-group[-1]['end']>.8):
            groups.append(group);group=[]
        group.append(word)
        if word['text'].rstrip().endswith(('.', '!', '?', '؟', '。','！','？')):
            groups.append(group);group=[]
    if group:groups.append(group)
    result=[]
    for group in groups:
        text=word_text(group,language)
        c=cue(group[0]['start'],group[-1]['end'],text,[],min(w.get('confidence',1) for w in group))
        c['words']=group;c['language']=language
        if len(text)/max(.1,c['end']-c['start'])>max_cps:
            c['flags'].append('Fast speech: review subtitle reading speed')
        result.append(c)
    return result
