"""Deterministic final-caption edits; recognition text and audio are never changed."""
import re
import unicodedata

DEFAULTS={'enabled':True,'match_case':False,'whole_words':True,'rules':[]}
MARKS=r'[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]'
RULE_WARNING='Subtitle text changed by replacement rules; review'

def arabic_letter(char):
    return unicodedata.category(char).startswith('L') and 'ARABIC' in unicodedata.name(char,'')

def without_marks(text):return re.sub(MARKS,'',text)

def arabic_whole(find,settings):
    return settings.get('whole_words',True) and bool(find) and arabic_letter(find[0])

def validate_rules(settings):
    if not isinstance(settings,dict):raise ValueError('Replacement settings must be an object.')
    for name in ('enabled','match_case','whole_words'):
        if name in settings and not isinstance(settings[name],bool):raise ValueError('Replacement options must be true or false.')
    rules=settings.get('rules',[])
    if not isinstance(rules,list) or len(rules)>200:raise ValueError('Use at most 200 replacement rules.')
    seen=set()
    for rule in rules:
        if not isinstance(rule,dict) or not isinstance(rule.get('find'),str) or not rule['find'].strip() or not isinstance(rule.get('replace'),str):
            raise ValueError('Every rule needs non-empty Find text. Leave Replace with blank to delete.')
        if len(rule['find'])>500 or len(rule['replace'])>2000:raise ValueError('A replacement rule is too long (Find: 500; Replace: 2000 characters).')
        key=re.sub(r'\s+',' ',rule['find'])
        if arabic_whole(key,settings):key=without_marks(key)
        if not settings.get('match_case',False):key=key.casefold()
        if key in seen:raise ValueError('Duplicate Find text: '+rule['find'])
        seen.add(key)

def compile_rules(settings):
    validate_rules(settings)
    rules=settings.get('rules',[]) if settings.get('enabled',True) else []
    rules=sorted(rules,key=lambda r:len(r['find']),reverse=True)
    parts=[]
    boundary=r'[\w\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]'
    def vocalized(text):return ''.join(re.escape(c)+(MARKS+'*' if arabic_letter(c) else '') for c in without_marks(text))
    prefixes={conjunction+prefix for conjunction in ('','و','ف') for prefix in ('','ب','ك','ل','ال','بال','كال','لل')}
    prefix_pattern='|'.join(vocalized(p) for p in sorted(prefixes,key=len,reverse=True))
    for i,rule in enumerate(rules):
        arabic=arabic_whole(rule['find'],settings)
        literal=r'\s+'.join((vocalized(s) if arabic else re.escape(s)) for s in re.split(r'\s+',rule['find']))
        # A one- or two-letter word would otherwise match inside others (ما in كما, لما).
        if arabic and len(re.sub(r'\s+','',without_marks(rule['find'])))>=3:literal=f'(?P<p{i}>{prefix_pattern})'+literal
        elif arabic:literal=f'(?P<p{i}>)'+literal
        if settings.get('whole_words',True):literal=f'(?<!{boundary}){literal}(?!{boundary})'
        parts.append(f'(?P<r{i}>{literal})')
    if not parts:return None,[]
    return re.compile('|'.join(parts),0 if settings.get('match_case',False) else re.IGNORECASE),rules

def replacement(match,rules):
    index=int(match.lastgroup[1:]);text=rules[index]['replace']
    # Deleting a word deletes its attached prefix too, not a stranded conjunction.
    prefix=match.groupdict().get(f'p{index}') or ''
    return prefix+text if text else ''

def tidy(text):
    """Close the gap a deleted word leaves: no double, edge or pre-punctuation spaces, no empty lines."""
    lines=[re.sub(r' +([.,!?؟،؛:…])',r'\1',re.sub(r'[ \t]{2,}',' ',line)).strip() for line in text.split('\n')]
    return '\n'.join(line for line in lines if line)

def substitute(pattern,rules,text):
    deleted=[]
    def swap(m):
        new=replacement(m,rules)
        if not new:deleted.append(m)
        return new
    result,hits=pattern.subn(swap,text)
    return (tidy(result) if deleted else result),hits

def replace_text(text,settings):
    pattern,rules=compile_rules(settings)
    if pattern is None:return text,0
    return substitute(pattern,rules,text)

def deleted_by_rule(cue):
    state=cue.get('replacement_state') or {}
    return bool(state.get('deleted') and state.get('base','').strip() and not cue.get('translation','').strip() and cue.get('translation','')==state.get('result'))

def apply_replacements(project,include_reviewed=False):
    pattern,rules=compile_rules(project.get('replacements',{}));changed=0
    for cue in project['cues']:
        if cue.get('reviewed') and not include_reviewed:continue
        current=cue.get('translation','');state=cue.get('replacement_state') or {}
        base=state.get('base',current) if current==state.get('result') else current
        result,hits=(substitute(pattern,rules,base) if pattern else (base,0))
        if hits and not result.strip():result=''
        flags=cue.setdefault('flags',[])
        for flag in [RULE_WARNING]+state.get('added_flags',[]):
            if flag in flags:flags.remove(flag)
        added=[]
        if hits and result!=base:
            flags.append(RULE_WARNING)
            if 'start' in cue and 'end' in cue and len(result)/max(.1,cue['end']-cue['start'])>20:
                speed='Translation reading speed exceeds 20 characters/second'
                if speed not in flags:flags.append(speed);added.append(speed)
            cue['replacement_state']={'base':base,'result':result,'deleted':not result.strip(),'added_flags':added}
        else:cue.pop('replacement_state',None)
        if result!=current:
            cue['translation']=result;cue['reviewed']=False;changed+=1
    return changed
