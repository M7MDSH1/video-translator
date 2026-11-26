"""Arabic caption rules adapted from the invoked Khaam Motion helpers.

The reference helper is tools/khaam/arabic.mjs; tests compare shaping and bidi
isolation against arLine(). Qt and libass remain the production renderers.
"""
import re
import unicodedata
import struct
from functools import lru_cache
from pathlib import Path

FONT_DIR=Path(__file__).resolve().parent.parent/'assets'/'fonts'/'Almarai'
ARABIC=re.compile(r'[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]')
_application=None
_families=None

@lru_cache(maxsize=1024)
def line_ink(text,family,size,bold,spacing):
    """Measure shaped glyph pixels, including Arabic dots, descenders and outline.

    QTextDocument's nominal height can exclude visible ink below a fixed-height
    line. Use the same document settings as the live single-line renderer.
    """
    import math
    import numpy as np
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont,QFontMetricsF,QTextDocument,QTextOption,QTextCursor,QTextCharFormat,QTextBlockFormat,QPen,QColor,QImage,QPainter
    font=QFont(family);font.setPixelSize(round(size));font.setBold(bold);font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,0)
    metrics=QFontMetricsF(font);width=max(metrics.horizontalAdvance(text),metrics.boundingRect(text).width())+4
    doc=QTextDocument();doc.setDocumentMargin(0);doc.setDefaultFont(font)
    option=QTextOption();option.setAlignment(Qt.AlignmentFlag.AlignHCenter);option.setTextDirection(Qt.LayoutDirection.LayoutDirectionAuto);option.setWrapMode(QTextOption.WrapMode.NoWrap);doc.setDefaultTextOption(option)
    doc.setPlainText(text);doc.setTextWidth(width)
    cursor=QTextCursor(doc);cursor.select(QTextCursor.SelectionType.Document)
    fmt=QTextCharFormat();fmt.setForeground(QColor('white'));fmt.setTextOutline(QPen(QColor('#232323'),1.5));cursor.mergeCharFormat(fmt)
    block=QTextBlockFormat();block.setLineHeight(max(size*spacing,metrics.height()),QTextBlockFormat.LineHeightTypes.FixedHeight.value);cursor.mergeBlockFormat(block)
    height=doc.size().height();pad=math.ceil(size+8)
    image=QImage(math.ceil(width+2*pad),math.ceil(height+2*pad),QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
    painter=QPainter(image);painter.translate(pad,pad);doc.drawContents(painter);painter.end()
    pixels=np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.width(),4)
    yy,xx=np.where(pixels[:,:,3]>0)
    if not len(xx):return width,height,0,0,0,0
    return width,height,float(xx.min()-pad),float(yy.min()-pad),float(xx.max()-xx.min()+1),float(yy.max()-yy.min()+1)

def load_fonts():
    global _application,_families
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase
    if QApplication.instance() is None:_application=QApplication([])
    if _families is None:
        _families=[]
        for file in sorted(FONT_DIR.glob('*.ttf')):
            index=QFontDatabase.addApplicationFont(str(file))
            if index<0:raise RuntimeError(f'Cannot load bundled caption font: {file.name}')
            _families.extend(QFontDatabase.applicationFontFamilies(index))
    return sorted(set(_families))

def khaam_style(existing=None):
    style=dict(existing or {})
    style.update(font='Almarai',size=48,bold=True,color='#ffffff',arabic_typography=True,line_height=1.45,max_width=.84)
    for key,value in {'x':.5,'y':.90,'padding':5}.items():style.setdefault(key,value)
    return style

def prepare_caption(text,style):
    if not style.get('arabic_typography') or not ARABIC.search(text):return text
    text=unicodedata.normalize('NFC',text)
    # Khaam shapeAr: protect final alef-maqsura joins, including IBM Plex users.
    text=re.sub(r'([بتثنيئ])ى',lambda m:m.group(1)+'\u200dى',text)
    # Khaam arLine: dates/ranges stay LTR inside the complete RTL line.
    # Negative lookbehind makes repeated formatting idempotent.
    text=re.sub(r'(?<![\d\u2066])\d+(?:[-–—/]\d+)+(?!\d)',lambda m:'\u2066'+m.group()+'\u2069',text)
    text=text.replace('?', '؟').replace(';','؛')
    text=re.sub(r'(?<!\d),|,(?!\d)','،',text)
    # Caption cuts provide the pause; retain ellipses and decimal values.
    return '\n'.join(re.sub(r'(?<![.\d])[.،]\s*$','',line.rstrip()) for line in text.splitlines())

def caption_width(style,width):
    if not style.get('arabic_typography'):return max(40,width-80)
    return max(40,min(width*style.get('max_width',.84),width-80))

def font_family(style):
    return 'Almarai Bold' if style['font']=='Almarai' and style['bold'] else style['font']

def ass_font_size(style):
    # ASS sizes Almarai by its Windows ascent+descent, whereas Qt pixelSize is
    # em-sized. Read the actual bundled font metrics so both use the same scale.
    if not style.get('arabic_typography') or style['font']!='Almarai':return style['size']
    load_fonts()
    from PySide6.QtGui import QRawFont
    raw=QRawFont(str(FONT_DIR/('Almarai-Bold.ttf' if style['bold'] else 'Almarai-Regular.ttf')),style['size'])
    units=struct.unpack('>H',bytes(raw.fontTable('head'))[18:20])[0]
    ascent,descent=struct.unpack('>HH',bytes(raw.fontTable('OS/2'))[74:78])
    return round(style['size']*(ascent+descent)/units,3)

def line_step(style):
    load_fonts()
    from PySide6.QtGui import QFont,QFontMetricsF
    font=QFont(font_family(style));font.setPixelSize(round(style['size']));font.setBold(style['bold'])
    return max(style['size']*style.get('line_height',1.45),QFontMetricsF(font).height())

def wrap_caption(text,style,width):
    load_fonts()
    from PySide6.QtGui import QFont,QFontMetricsF
    font=QFont(font_family(style));font.setPixelSize(round(style['size']));font.setBold(style['bold']);font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,0)
    metrics=QFontMetricsF(font);lines=[]
    prepositions={'في','من','على','إلى','عن','مع','و'}
    for paragraph in prepare_caption(text,style).split('\n'):
        words=paragraph.split();groups=[];i=0
        while i<len(words):
            if words[i] in prepositions and i+1<len(words):groups.append(words[i]+' '+words[i+1]);i+=2
            else:groups.append(words[i]);i+=1
        line=''
        for group in groups:
            candidate=(line+' '+group).strip()
            if line and metrics.horizontalAdvance(candidate)>width:lines.append(line);line=group
            else:line=candidate
        lines.append(line)
    return lines

def arabic_warnings(text):
    """Conservative typography checks, not a promise of grammatical correctness."""
    if not ARABIC.search(text):return []
    issues=[]
    if re.search(r'[?;,]',text):issues.append('Check Arabic punctuation')
    if re.search(r'(?:[\u0621-\u064a]\s+){3,}[\u0621-\u064a]',text):issues.append('Possible separated Arabic letters')
    if 'ـ' in text:issues.append('Check stretched letters / kashida')
    if re.search(r'[\u202a-\u202e]',text):issues.append('Directional override present; check mixed text')
    return issues
