import os
import re
import json
from functools import lru_cache
from difflib import SequenceMatcher
from .typography import prepare_caption,wrap_caption,caption_width,font_family,ass_font_size,line_step

def cue(start,end,text,boxes,confidence):
    return {'start':start,'end':end,'original':text,'translation':'','boxes':boxes,
            'confidence':float(confidence),'flags':(['Low recognition confidence'] if confidence<.8 else [])+['Translation needs review'], 'reviewed':False}

def dialogue_samples(samples,profile,w,h):
    """Apply a project-specific speaker/dialogue layout, retaining blank timestamps.

    This is intentionally opt-in: films with unlabelled dialogue need a different
    profile. Original OCR samples stay untouched for recovery and re-filtering.
    """
    if not profile:return samples
    result=[]
    for sample in samples:
        pairs=list(zip(sample['text'].split('\n'),sample['boxes']))
        def matches(pair,y,tolerance=None):
            text,(x,top,bw,bh)=pair
            return (bool(text.strip()) and bh/h>=profile['min_height'] and
                    abs((x+bw/2)/w-profile['center'])<=profile['tolerance'] and
                    abs((top+bh/2)/h-y)<=(profile['tolerance'] if tolerance is None else tolerance))
        speakers=[v for v in pairs if matches(v,profile['speaker_y'],profile.get('vertical_drift',profile['tolerance']))]
        keep=[]
        for speaker in speakers:
            box=speaker[1];shift=(box[1]+box[3]/2)/h-profile['speaker_y']
            dialogue=[v for v in pairs if v is not speaker and matches(v,profile['dialogue_y']+shift)]
            if dialogue and profile.get('second_line_gap'):
                dialogue += [v for v in pairs if v not in dialogue and v is not speaker and matches(v,profile['dialogue_y']+shift+profile['second_line_gap'])]
            if dialogue:keep=[speaker]+dialogue;break
        if keep and keep[0][0] in profile.get('excluded_speakers',[]):keep=[]
        result.append(dict(sample,text='\n'.join(v[0] for v in keep),boxes=[v[1] for v in keep]))
    return result

def same_subtitle(a,b):
    """Two OCR readings of one subtitle. Garbage tails ('AHHHHQIII' / 'AHHHHLILUL')
    defeat a plain similarity ratio, so also accept equal earlier lines plus a long
    shared start of the last line."""
    a,b=a.casefold(),b.casefold()
    if SequenceMatcher(None,a,b).ratio()>=.90:return True
    a_lines,b_lines=a.split('\n'),b.split('\n')
    if len(a_lines)!=len(b_lines) or a_lines[:-1]!=b_lines[:-1]:return False
    x,y=a_lines[-1],b_lines[-1]
    return len(os.path.commonprefix([x,y]))>=max(6,.6*min(len(x),len(y)))

def merge_detections(samples,interval,duration):
    out=[]; active=None
    for sample in samples:
        text=sample['text'].strip(); t=sample['time']
        if not text:
            active=None; continue
        same=active and t-active['end']<=interval*.6 and same_subtitle(active['original'],text)
        end=min(duration,t+interval)
        span={'start':t,'end':end,'boxes':sample['boxes']}
        if same:
            active['end']=end; active['cover_spans'].append(span)
            if sample['confidence']>active['confidence']:
                active['original']=text; active['confidence']=sample['confidence']; active['boxes']=sample['boxes']
        else:
            active=cue(t,end,text,sample['boxes'],sample['confidence'])
            active['cover_spans']=[span]; out.append(active)
    return out

def _distinct_boxes(boxes):
    # OCR occasionally returns punctuation as a second box entirely inside an
    # already detected line. It is not an extra subtitle line.
    return [b for i,b in enumerate(boxes) if not any(
        j!=i and a[0]<=b[0] and a[1]<=b[1] and a[0]+a[2]>=b[0]+b[2] and a[1]+a[3]>=b[1]+b[3]
        and (a!=b or j<i) for j,a in enumerate(boxes))]

@lru_cache(maxsize=256)
def _stable_spans(encoded):
    """Union near-identical OCR edges over a stationary run, never across gaps.

    Compare the complete run's edge range, not only adjacent samples, so real
    movement cannot accumulate indefinitely under the jitter tolerance.
    """
    spans=json.loads(encoded);runs=[]
    for span in spans:
        boxes=sorted(_distinct_boxes(span['boxes']),key=lambda b:(b[1],b[0]))
        edges=[[x,y,x+w,y+h] for x,y,w,h in boxes]
        previous=runs[-1] if runs else None
        tolerance=max(2,min(12,min((b[3] for b in boxes),default=0)*.2))
        low=[[min(a,b) for a,b in zip(old,new)] for old,new in zip(previous['low'],edges)] if previous else []
        high=[[max(a,b) for a,b in zip(old,new)] for old,new in zip(previous['high'],edges)] if previous else []
        same=(previous and boxes and len(edges)==len(previous['low']) and abs(previous['end']-span['start'])<.001
              and all(hi-lo<=tolerance for lows,highs in zip(low,high) for lo,hi in zip(lows,highs)))
        if same:previous.update(end=span['end'],low=low,high=high)
        else:runs.append({'start':span['start'],'end':span['end'],'low':edges,'high':edges})
    return [{'start':r['start'],'end':r['end'],'boxes':[[lo[0],lo[1],hi[2]-lo[0],hi[3]-lo[1]] for lo,hi in zip(r['low'],r['high'])]} for r in runs]

def stable_cover_spans(c):
    spans=c.get('cover_spans')
    if not spans:return [{'start':c['start'],'end':c['end'],'boxes':_distinct_boxes(c.get('boxes',[]))}]
    return _stable_spans(json.dumps(spans,sort_keys=True))

def active_covers(c,time):
    if not c['start']<=time<c['end']:return []
    if c.get('cover_spans'):
        return [b for span in stable_cover_spans(c) if span['start']<=time<span['end'] for b in span['boxes']]
    return _distinct_boxes(c.get('boxes',[]))

def lead_cover(c,p):
    """The cue with its first cover started one OCR sample early.

    Recognition first sees a line up to one sample after it appears, so
    without this the original flashes uncovered for that long.
    """
    spans=stable_cover_spans(c);lead=p.get('sample_interval',.25)
    if not spans or not spans[0]['boxes'] or lead<=0:return c
    start=max(0,c['start']-lead)
    return dict(c,start=start,cover_spans=[dict(spans[0],start=start)]+spans[1:])

def display_cues(p,cps=17,minimum=1.2,longest=6,max_lag=8):
    """(cue, text-display cue) pairs in start order.

    Game dialogue skipped in 0.2 s cannot be read in translation. Text is held for
    reading time and may run up to max_lag behind rapid dialogue. Covers for the
    original keep the original timing; a held caption keeps the cover position it
    last had, so it stays where the original was.
    """
    replace=p['appearance']=='replace' and p['original_kind']=='burned'
    from .replacements import deleted_by_rule
    duration=p['media']['duration'];order=sorted((c for c in p['cues'] if not deleted_by_rule(c)),key=lambda c:c['start'])
    need=lambda c:min(longest,max(minimum,len(c.get('translation','').replace('\n',''))/cps))
    def place(cues,scale,free):
        out=[]
        for c in cues:
            start=max(c['start'],free);free=min(duration,max(c['end'],start+need(c)*scale))
            out.append([c,start,free])
        return out
    def scale(cues,free):
        # Share the time evenly instead of crushing the last lines of a burst.
        fits=lambda s:all(t[1]-t[0]['start']<=max_lag for t in place(cues,s,free))
        if fits(1):return 1
        low,high=0,1
        for _ in range(30):
            mid=(low+high)/2;low,high=(mid,high) if fits(mid) else (low,mid)
        return low
    times=[];free=0;i=0
    while i<len(order):
        # A burst: lines that begin while the previous translation is still held.
        j=i+1;s=scale(order[i:j],free)
        while j<len(order) and order[j]['start']<place(order[i:j],s,free)[-1][2]:j+=1;s=scale(order[i:j],free)
        times+=place(order[i:j],s,free);free=times[-1][2];i=j
    pairs=[]
    for c,start,end in times:
        if (start,end)==(c['start'],c['end']):pairs.append((c,c));continue
        held=dict(c,start=start,end=end)
        if replace:
            spans=[s for s in stable_cover_spans(c) if s['boxes']]
            clipped=[dict(s,start=max(s['start'],start),end=min(s['end'],end)) for s in spans]
            held['cover_spans']=[s for s in clipped if s['start']<s['end']]
            tail=max([start]+[s['end'] for s in held['cover_spans']])
            if spans and tail<end:held['cover_spans'].append({'start':tail,'end':end,'boxes':spans[-1]['boxes']})
        pairs.append((c,held))
    pairs.extend((c,c) for c in p['cues'] if deleted_by_rule(c))
    return sorted(pairs,key=lambda pair:pair[0]['start'])

def caption_anchor(c,p,w,h,time=None):
    """Bottom-centre pixel point for a cue's translation.

    Replacing burned-in originals puts the translation where the original was:
    centred on its cover boxes, bottom on their bottom edge. Otherwise style X/Y.
    """
    s=p['style']
    if p['appearance']=='replace' and p['original_kind']=='burned':
        boxes=active_covers(c,c['start'] if time is None else time)
        if boxes:
            left=min(b[0] for b in boxes);right=max(b[0]+b[2] for b in boxes)
            return (left+right)/2,max(b[1]+b[3] for b in boxes)
    return w*s.get('x',.5),h*s['y']

def caption_intervals(c,p):
    points={c['start'],c['end']}
    if p['appearance']=='replace' and p['original_kind']=='burned':
        for span in stable_cover_spans(c):
            for t in (span['start'],span['end']):
                if c['start']<t<c['end']:points.add(t)
    points=sorted(points)
    return list(zip(points,points[1:]))

def caption_layout(c,p,w,h,time=None):
    """Shared Qt/ASS layout: retain whole words and keep the text block in frame."""
    from PySide6.QtGui import QFont,QFontMetricsF
    from .typography import load_fonts
    load_fonts();style=dict(p['style']);margin=min(8,w/20,h/20)
    available_w=max(1,w-2*margin);available_h=max(1,h-2*margin)
    while True:
        lines=wrap_caption(c['translation'],style,min(caption_width(style,w),available_w))
        font=QFont(font_family(style));font.setPixelSize(round(style['size']));font.setBold(style['bold'])
        metrics=QFontMetricsF(font)
        width=max((max(metrics.horizontalAdvance(t),metrics.boundingRect(t).width()) for t in lines),default=0)+4
        step=line_step(style);height=step*len(lines)
        if (width<=available_w and height<=available_h) or style['size']<=1:break
        style['size']=max(1,min(round(style['size'])-1,int(style['size']*.9)))
    ax,ay=caption_anchor(c,p,w,h,time)
    ax=max(margin+width/2,min(w-margin-width/2,ax))
    ay=max(margin+height,min(h-margin,ay))
    return {'x':ax,'y':ay,'width':width,'height':height,'step':step,'lines':lines,'style':style}

def cover_rect(box,p,w,h):
    x,y,bw,bh=box;pad=p['style']['padding']
    side=pad+.9*bh  # OCR boxes stop before a leading/trailing "…", which would show past the cover
    left=max(0,round(x-side));top=max(0,round(y-pad))
    return [left,top,min(w,round(x+bw+side))-left,min(h,round(y+bh+pad))-top]

def _distribute(text,boxes):
    """Keep whole words and explicit speaker/dialogue lines when possible."""
    if not boxes:return []
    paragraphs=text.split('\n')
    if len(paragraphs)==len(boxes):return paragraphs
    if len(paragraphs)>1 and len(boxes)>1:
        return [paragraphs[0]]+_distribute(' '.join(paragraphs[1:]),boxes[1:])
    words=text.split();result=[]
    for i,box in enumerate(boxes):
        if i==len(boxes)-1:result.append(' '.join(words));break
        if not words:result.append('');continue
        target=len(' '.join(words))*box[2]/max(1,sum(b[2] for b in boxes[i:]))
        count=1
        while count<len(words) and abs(len(' '.join(words[:count+1]))-target)<abs(len(' '.join(words[:count]))-target):count+=1
        if len(words)>=len(boxes)-i:count=min(count,len(words)-(len(boxes)-i-1))
        result.append(' '.join(words[:count]));words=words[count:]
    return result

def caption_blocks(c,p,w,h,time=None):
    blocks=_caption_blocks(c,p,w,h,time)
    if not blocks:return blocks
    scale=p['style'].get('caption_scale',1)*c.get('caption_scale',1)
    if scale!=1:
        left,top,right,bottom=caption_bounds(blocks);cx=(left+right)/2;cy=(top+bottom)/2
        scale=min(max(scale,1/max(.01,min(b['style']['size'] for b in blocks))),w/max(1,right-left),h/max(1,bottom-top))
        resized=[]
        for block in blocks:
            b=dict(block,x=cx+(block['x']-cx)*scale,y=cy+(block['y']-cy)*scale,
                   style=dict(block['style'],size=block['style']['size']*scale))
            for key in ('width','height','doc_width','step'):
                if key in b:b[key]*=scale
            for key in ('cover','ink_bounds'):
                if key in b:
                    x,y,bw,bh=b[key];b[key]=[cx+(x-cx)*scale,cy+(y-cy)*scale,bw*scale,bh*scale]
            resized.append(b)
        blocks=resized
    global_offset=p['style'].get('caption_offset',[0,0]);local_offset=c.get('caption_offset',[0,0])
    dx=(global_offset[0]+local_offset[0])*w;dy=(global_offset[1]+local_offset[1])*h
    bounds=caption_bounds(blocks)
    dx=max(-bounds[0],min(w-bounds[2],dx));dy=max(-bounds[1],min(h-bounds[3],dy))
    result=[]
    for block in blocks:
        b=dict(block,x=block['x']+dx,y=block['y']+dy)
        for key in ('cover','ink_bounds'):
            if key in b:b[key]=[b[key][0]+dx,b[key][1]+dy,*b[key][2:]]
        result.append(b)
    return result

def caption_bounds(blocks):
    rects=[b.get('cover',b.get('ink_bounds',[b['x']-b['width']/2,b['y']-b['height'],b['width'],b['height']])) for b in blocks]
    return min(r[0] for r in rects),min(r[1] for r in rects),max(r[0]+r[2] for r in rects),max(r[1]+r[3] for r in rects)

def _caption_blocks(c,p,w,h,time=None):
    """Replacement lines fit inside individual covers, not their union."""
    from .replacements import deleted_by_rule
    if deleted_by_rule(c):return []
    time=c['start'] if time is None else time
    boxes=active_covers(c,time) if p['appearance']=='replace' and p['original_kind']=='burned' else []
    if not boxes and p['appearance']=='replace' and p['original_kind']=='burned' and c.get('cover_spans'):
        return []  # A timed cover gap must not leave floating replacement text.
    if not boxes:return [caption_layout(c,p,w,h,time)]
    return _fit_caption_boxes(c['translation'],json.dumps(p['style'],sort_keys=True),json.dumps(boxes),w,h)

@lru_cache(maxsize=4096)
def _fit_caption_boxes(text,style_key,boxes_key,w,h):
    from PySide6.QtGui import QFont,QRawFont
    from .typography import load_fonts,ARABIC,line_ink
    load_fonts();p={'style':json.loads(style_key)};boxes=json.loads(boxes_key)
    fitted=[]
    for text,box in zip(_distribute(prepare_caption(text,p['style']),boxes),boxes):
        if not text.strip():continue
        style=dict(p['style']);rect=cover_rect(box,p,w,h);bw,bh=rect[2:]
        font=QFont(font_family(style));font.setPixelSize(round(style['size']));font.setBold(style['bold'])
        raw=QRawFont.fromFont(font)
        if ARABIC.search(text) and (raw.familyName().casefold()!=font_family(style).casefold() or any(not raw.supportsCharacter(ord(ch)) for ch in text if '\u0621'<=ch<='\u064a')):
            style.update(font='Almarai',arabic_typography=True)
        minimum=min(style['size'],style.get('minimum_size',1))
        while True:
            width,height,ix,iy,iw,ih=line_ink(text,font_family(style),style['size'],style['bold'],style.get('line_height',1.45))
            # Room for small Qt/libass rasterization and baseline differences.
            inset=min(max(3,style['size']*.2),bw/4,bh/4)
            available_w=max(.1,bw-2*inset);available_h=max(.1,bh-2*inset)
            if (iw<=available_w and ih<=available_h) or style['size']<=minimum:break
            style['size']=max(1,round(style['size'])-1)
        fitted.append((text,rect,style,minimum))
    # One caption, one text size: every line uses the size of the tightest line.
    size=min((s['size'] for _,_,s,_ in fitted),default=0);blocks=[]
    for text,rect,style,minimum in fitted:
        style['size']=size;x,y,bw,bh=rect
        width,height,ix,iy,iw,ih=line_ink(text,font_family(style),size,style['bold'],style.get('line_height',1.45))
        inset=min(max(3,size*.2),bw/4,bh/4)
        available_w=max(.1,bw-2*inset);available_h=max(.1,bh-2*inset)
        if minimum>1:
            # A readable minimum may require a wider individual line background.
            # Grow around the same centre; never turn covers into a bottom band.
            new_w=min(w,max(bw,iw+2*inset));new_h=min(h,max(bh,ih+2*inset))
            x=max(0,min(w-new_w,x+(bw-new_w)/2));y=max(0,min(h-new_h,y+(bh-new_h)/2))
            bw,bh=new_w,new_h;rect=[x,y,bw,bh]
            available_w=max(.1,bw-2*inset);available_h=max(.1,bh-2*inset)
        scale=min(1,available_w/max(.1,iw))
        blocks.append({'x':x+bw/2+(width/2-ix-iw/2)*scale,'y':y+bh/2+height-iy-ih/2,
                       'width':width*scale,'doc_width':width,'height':height,'ink_bounds':[x+(bw-iw*scale)/2,y+(bh-ih)/2,iw*scale,ih],
                       'step':height,'lines':[text],'style':style,'scale_x':scale,'cover':rect})
    return blocks

def rendered_covers(c,p,w,h,time):
    """Background rectangles shared by live playback and export."""
    original=[cover_rect(b,p,w,h) for b in active_covers(c,time)]
    blocks=caption_blocks(c,p,w,h,time)
    return original+[b['cover'] for b in blocks if 'cover' in b and b['cover'] not in original]

def stamp(seconds,ass=False):
    unit=100 if ass else 1000; ticks=round(seconds*unit)
    whole,frac=divmod(ticks,unit); mins,s=divmod(whole,60); h,m=divmod(mins,60)
    return f'{h}:{m:02}:{s:02}.{frac:02}' if ass else f'{h:02}:{m:02}:{s:02},{frac:03}'

RTL_LANGUAGES={'ar','fa','ur','he'}

def make_srt(p,rtl_marks=False,speaker_names=True):
    # The zero-width joiners added for libass rendering are noise in a sidecar file.
    from .replacements import deleted_by_rule
    from .dialogue import speaker_label,spoken,given_names
    visible=((a,c) for a,c in display_cues(p) if not deleted_by_rule(c))
    names=given_names(p)
    def text(c):
        # Without names: only a first line verified as a speaker label by its position is dropped; anything unsure stays.
        t=c["translation"] if speaker_names else spoken(c["translation"],speaker_label(c,p),names)
        t=prepare_caption(t,p["style"]).replace(chr(0x200d),"")
        # A right-to-left mark keeps lines that start with "...", a digit or a Latin name right-aligned in players.
        return '\n'.join('\u200f'+line for line in t.split('\n')) if rtl_marks else t
    return '\n\n'.join(f'{i}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{text(c)}' for i,(_,c) in enumerate(visible,1))+'\n'

def clean(text):
    # Never let a transcript inject ASS commands. Unicode stays in logical order;
    # libass/HarfBuzz/FriBidi handle Arabic shaping and bidirectional punctuation.
    return text.replace('\\','＼').replace('{','｛').replace('}','｝').replace('\r','').replace('\n',r'\N')

def make_ass(p,offset=0):
    w,h=p['media']['width'],p['media']['height']; s=p['style']
    color=s['color'].lstrip('#'); color='&H00'+color[4:6]+color[2:4]+color[0:2]
    font=re.sub(r'[,\r\n]','',font_family(s));font_size=ass_font_size(s)
    lines=['[Script Info]','ScriptType: v4.00+',f'PlayResX: {w}',f'PlayResY: {h}','WrapStyle: 0','ScaledBorderAndShadow: yes',
           '[V4+ Styles]','Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
           f'Style: Default,{font},{font_size},{color},&H000000FF,&H00232323,&H00232323,{-1 if s["bold"] else 0},0,0,0,100,100,0,0,1,1.5,0,2,40,40,30,-1',
           '[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    def event(layer,start,end,text):
        if end<=offset or end<=start:return
        lines.append(f'Dialogue: {layer},{stamp(max(0,start-offset),True)},{stamp(end-offset,True)},Default,,0,0,0,,{text}')
    for c,shown in display_cues(p):
        if p['appearance']=='replace' and p['original_kind']=='burned':
            # Original timing hides the original; a held caption brings its own box.
            for cover_cue in ((lead_cover(c,p),) if shown is c else (lead_cover(c,p),shown)):
                for start,end in caption_intervals(cover_cue,p):
                    for x0,y0,bw,bh in rendered_covers(cover_cue,p,w,h,start):
                        draw=f'{{\\an7\\pos({x0},{y0})\\bord0\\shad0\\1c&H232323&\\p1}}m 0 0 l {bw} 0 l {bw} {bh} l 0 {bh}{{\\p0}}'
                        event(0,start,end,draw)
        for start,end in caption_intervals(shown,p):
            for layout in caption_blocks(shown,p,w,h,start):
                font_name=re.sub(r'[,\r\n]','',font_family(layout['style']))
                overrides=f'\\fn{font_name}\\fs{ass_font_size(layout["style"])}\\fscx{layout.get("scale_x",1)*100:.3f}'
                for index,line in enumerate(layout['lines']):
                    y=round(layout['y']-(len(layout['lines'])-1-index)*layout['step'])
                    text=f'{{\\an2\\q2{overrides}\\pos({round(layout["x"])},{y})}}'+clean(line)
                    event(1,start,end,text)
    return '\n'.join(lines)+'\n'

