"""In-memory editing overlay. Export remains the authoritative libass render."""
import copy
from PySide6.QtCore import Qt,QRectF,QPointF,Signal
from PySide6.QtGui import QImage,QPainter,QColor,QFont,QPen,QTextDocument,QTextOption,QTextCursor,QTextCharFormat,QTextBlockFormat
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QVideoSink
from .subtitles import active_covers,caption_blocks,caption_bounds,cover_rect,rendered_covers,display_cues,lead_cover
from .typography import ARABIC,prepare_caption,wrap_caption,caption_width,load_fonts,font_family,line_step
from .motion import EASE_OUT,enabled,stop,_tween

def snap_center(left,right,dx,width,tolerance):
    """Horizontal drag offset, pulled so the caption is centred when its centre comes within tolerance of the frame centre."""
    centre=(left+right)/2+dx
    return (dx+width/2-centre,True) if abs(centre-width/2)<=tolerance else (dx,False)

class LiveVideoWidget(QWidget):
    boxesEdited=Signal(list)
    captionMoved=Signal(float,float,int)
    captionDragStarted=Signal(int)
    captionResized=Signal(float,int)
    def __init__(self,parent=None):
        super().__init__(parent)
        load_fonts()
        self.sink=QVideoSink(self);self.sink.videoFrameChanged.connect(self.receive_frame)
        self.native_text='';self.show_native=False;self.sink.subtitleTextChanged.connect(self.native_text_changed)
        self.frame=QImage();self.time=0.;self.project=None;self.live=False
        self.edit_covers=False;self.selected=-1;self.drag=None;self.docs={}
        self.drag_subtitles=True;self.caption_scope='all';self.caption_drag=None
        self.caption_resize=None
        self._lift=0.;self._outline=1.;self._outlined=None;self.snap_guide=False
        self.setMinimumSize(600,338);self.setMouseTracking(True)
    def _animate(self,name,end,ms):
        if not enabled(self):stop(self,name);setattr(self,name,end);self.update();return
        _tween(self,name,float(getattr(self,name)),float(end),ms,EASE_OUT,lambda v:(setattr(self,name,v),self.update()))
    def videoSink(self):return self.sink
    def native_text_changed(self,text):
        doc=QTextDocument();doc.setHtml(text);self.native_text=doc.toPlainText();self.update()
    def set_project(self,p):self.project=p;self.update()
    def receive_frame(self,frame):
        if frame.isValid():
            image=frame.toImage()
            if not image.isNull():
                self.frame=image
                if frame.startTime()>=0:self.time=frame.startTime()/1e6
                self.update()
    def frame_rect(self):
        if self.frame.isNull():return QRectF(self.rect())
        scale=min(self.width()/self.frame.width(),self.height()/self.frame.height())
        w,h=self.frame.width()*scale,self.frame.height()*scale
        return QRectF((self.width()-w)/2,(self.height()-h)/2,w,h)
    def source_size(self):
        return (self.project['media']['width'],self.project['media']['height']) if self.project else (self.frame.width(),self.frame.height())
    def document(self,text,style,width,prewrapped=False):
        text=prepare_caption(text,style)
        if style.get('arabic_typography') and not prewrapped:text='\n'.join(wrap_caption(text,style,width))
        key=(text,style['font'],style['size'],style['bold'],style['color'],width,style.get('arabic_typography',False),style.get('line_height',1.45),prewrapped)
        if key not in self.docs:
            if len(self.docs)>24:self.docs.clear()
            doc=QTextDocument();doc.setDocumentMargin(0)
            font=QFont(font_family(style));font.setPixelSize(round(style['size']));font.setBold(style['bold']);font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,0);doc.setDefaultFont(font)
            option=QTextOption();option.setAlignment(Qt.AlignmentFlag.AlignHCenter);option.setTextDirection(Qt.LayoutDirection.LayoutDirectionAuto)
            option.setWrapMode(QTextOption.WrapMode.NoWrap if prewrapped or style.get('arabic_typography') else QTextOption.WrapMode.WordWrap);doc.setDefaultTextOption(option)
            doc.setPlainText(text);doc.setTextWidth(width)
            cursor=QTextCursor(doc);cursor.select(QTextCursor.SelectionType.Document)
            fmt=QTextCharFormat();fmt.setForeground(QColor(style['color']));fmt.setTextOutline(QPen(QColor('#232323'),1.5));cursor.mergeCharFormat(fmt)
            if prewrapped or style.get('arabic_typography'):
                block=QTextBlockFormat();block.setLineHeight(line_step(style),QTextBlockFormat.LineHeightTypes.FixedHeight.value);cursor.mergeBlockFormat(block)
            # Qt strokes overlap the glyph fill. Draw a clean fill pass over
            # the outline so small Arabic letters and dots stay solid white.
            doc.caption_fill=doc.clone()
            fill_cursor=QTextCursor(doc.caption_fill);fill_cursor.select(QTextCursor.SelectionType.Document)
            fill_format=QTextCharFormat();fill_format.setTextOutline(QPen(Qt.PenStyle.NoPen));fill_cursor.mergeCharFormat(fill_format)
            self.docs[key]=doc
        return self.docs[key]
    @staticmethod
    def draw_document(doc,painter):
        doc.drawContents(painter);doc.caption_fill.drawContents(painter)
    def paint_overlay(self,painter):
        p=self.project
        if not p:return
        w,h=self.source_size();s=p['style']
        if self.show_native and self.native_text:
            style={'font':'Arial','size':max(12,round(h*.045)),'bold':False,'color':'#ffffff'}
            doc=self.document(self.native_text,style,max(40,w-80))
            painter.save();painter.translate((w-doc.textWidth())/2,h*.94-doc.size().height());self.draw_document(doc,painter);painter.restore()
        if not self.live:return
        # Edits mutate cues in place, so the cache key is the timing-relevant content.
        key=(id(p),p['appearance'],p['original_kind'],p.get('sample_interval'),tuple((c['start'],c['end'],c.get('translation',''),str(c.get('caption_offset')),c.get('caption_scale',1),id(c.get('cover_spans')),len(c.get('cover_spans') or []),str(c.get('boxes'))) for c in p['cues']))
        if getattr(self,'_display_key',None)!=key:self._display_key=key;self._display=[(c,shown,lead_cover(c,p)) for c,shown in display_cues(p)]
        active=[(c,shown,lead) for c,shown,lead in self._display if lead['start']<=self.time<c['end'] or shown['start']<=self.time<shown['end']]
        # Covers are drawn below all translated text, as in the ASS export layers.
        if p['appearance']=='replace' and p['original_kind']=='burned':
            for c,shown,lead in active:
                for cover_cue in ((lead,) if shown is c else (lead,shown)):
                    if cover_cue['start']<=self.time<cover_cue['end']:
                        for rect in rendered_covers(cover_cue,p,w,h,self.time):
                            painter.fillRect(QRectF(*rect),QColor('#232323'))
        for c in [shown for _,shown,_ in active if shown['start']<=self.time<shown['end']]:
            for layout in caption_blocks(c,p,w,h,self.time):
                doc=self.document('\n'.join(layout['lines']),layout['style'],layout.get('doc_width',layout['width']),prewrapped=True)
                scale=layout.get('scale_x',1)
                painter.save();painter.translate(layout['x']-doc.textWidth()*scale/2,layout['y']-doc.size().height());painter.scale(scale,1);self.draw_document(doc,painter);painter.restore()
        if self.edit_covers and 0<=self.selected<len(p['cues']):
            painter.setPen(QPen(QColor('#56dec1'),2));painter.setBrush(Qt.BrushStyle.NoBrush)
            for x,y,bw,bh in active_covers(p['cues'][self.selected],self.time):
                painter.drawRect(QRectF(x,y,bw,bh));painter.fillRect(QRectF(x+bw-7,y+bh-7,14,14),QColor('#56dec1'))
    def composite(self):
        if self.frame.isNull():return QImage()
        output=self.frame.copy();painter=QPainter(output);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.source_size();painter.scale(output.width()/w,output.height()/h);self.paint_overlay(painter);painter.end();return output
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#10131a'))
        if self.frame.isNull():return
        rect=self.frame_rect();painter.drawImage(rect,self.frame)
        w,h=self.source_size();painter.save();painter.translate(rect.x(),rect.y());painter.scale(rect.width()/w,rect.height()/h)
        painter.setClipRect(QRectF(0,0,w,h));painter.setRenderHint(QPainter.RenderHint.Antialiasing);self.paint_overlay(painter)
        if self.live and self.drag_subtitles and not self.edit_covers and self.project:
            # The outline fades in whenever a different subtitle comes on screen.
            showing=tuple(id(o) for o,s in display_cues(self.project) if s['start']<=self.time<s['end'])
            if showing!=self._outlined:
                self._outlined=showing
                if showing:self._outline=0.;self._animate('_outline',1,180)
            teal=QColor('#57D6B5');teal.setAlphaF(self._outline)
            handle=8*w/max(1,rect.width());painter.setPen(QPen(teal,w/max(1,rect.width()),Qt.PenStyle.DashLine))
            for _,shown in display_cues(self.project):
                if not shown['start']<=self.time<shown['end']:continue
                blocks=caption_blocks(shown,self.project,w,h,self.time)
                if not blocks:continue
                l,t,r,b=caption_bounds(blocks)
                if self._lift>0:  # a dragged subtitle lifts: soft shadow and a solid outline (on screen only, never exported)
                    px=w/max(1,rect.width());painter.setPen(Qt.PenStyle.NoPen)
                    for k in range(1,6):
                        spread=k*3*px;painter.setBrush(QColor(0,0,0,int(26*self._lift)))
                        painter.drawRoundedRect(QRectF(l-spread,t-spread+7*px*self._lift,r-l+2*spread,b-t+2*spread),6*px,6*px)
                    painter.setPen(QPen(teal,2*px))
                else:painter.setPen(QPen(teal,w/max(1,rect.width()),Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRect(QRectF(l,t,r-l,b-t))
                for x,y in ((l,t),(r,t),(l,b),(r,b)):painter.fillRect(QRectF(x-handle/2,y-handle/2,handle,handle),teal)
                painter.setPen(QPen(teal,w/max(1,rect.width()),Qt.PenStyle.DashLine))
            if self.snap_guide:  # centre guide while a dragged subtitle is snapped to the middle
                painter.setPen(QPen(QColor('#57D6B5'),1.5*w/max(1,rect.width()),Qt.PenStyle.DashLine));painter.drawLine(QPointF(w/2,0),QPointF(w/2,h))
        painter.restore()
    def source_point(self,point):
        rect=self.frame_rect();w,h=self.source_size()
        return [max(0,min(w,(point.x()-rect.x())/rect.width()*w)),max(0,min(h,(point.y()-rect.y())/rect.height()*h))]
    def mousePressEvent(self,event):
        if self.live and self.drag_subtitles and not self.edit_covers and self.project and event.button()==Qt.MouseButton.LeftButton and self.frame_rect().contains(event.position()):
            point=self.source_point(event.position());w,h=self.source_size()
            for original,shown in reversed(display_cues(self.project)):
                if not shown['start']<=self.time<shown['end']:continue
                blocks=caption_blocks(shown,self.project,w,h,self.time)
                if not blocks:continue
                left,top,right,bottom=caption_bounds(blocks)
                tolerance=10*w/max(1,self.frame_rect().width())
                corners=((left,top),(right,top),(left,bottom),(right,bottom))
                corner=next((n for n,(x,y) in enumerate(corners) if abs(point[0]-x)<=tolerance and abs(point[1]-y)<=tolerance),None)
                if corner is not None:
                    index=next(i for i,c in enumerate(self.project['cues']) if c is original)
                    target=index if self.caption_scope=='selected' else -1
                    rawp=dict(self.project,style=dict(self.project['style'],caption_scale=1))
                    raw=caption_bounds(caption_blocks(dict(shown,caption_scale=1),rawp,w,h,self.time))
                    other=self.project['style'].get('caption_scale',1) if target>=0 else original.get('caption_scale',1)
                    base=(right-left)/max(.01,raw[2]-raw[0])/other
                    center=((left+right)/2,(top+bottom)/2)
                    vector=(corners[corner][0]-center[0],corners[corner][1]-center[1])
                    self.caption_resize=(center,vector,base,target,(right-left,bottom-top))
                    self.captionDragStarted.emit(index);self.setCursor(Qt.CursorShape.SizeFDiagCursor if corner in (0,3) else Qt.CursorShape.SizeBDiagCursor);return
                if left<=point[0]<=right and top<=point[1]<=bottom:
                    index=next(i for i,c in enumerate(self.project['cues']) if c is original)
                    target=index if self.caption_scope=='selected' else -1
                    bare_project=dict(self.project,style=dict(self.project['style'],caption_offset=[0,0]))
                    bare=caption_blocks(dict(shown,caption_offset=[0,0]),bare_project,w,h,self.time)
                    raw=caption_bounds(bare)
                    other=self.project['style'].get('caption_offset',[0,0]) if target>=0 else original.get('caption_offset',[0,0])
                    base=[(left-raw[0])/w-other[0],(top-raw[1])/h-other[1]]
                    self.caption_drag=(point,base,target,(left,top,right,bottom))
                    self.captionDragStarted.emit(index);self.setCursor(Qt.CursorShape.ClosedHandCursor);self._animate('_lift',1,200);return
        if not self.live or not self.edit_covers or not self.project or not 0<=self.selected<len(self.project['cues']):return
        if event.button()!=Qt.MouseButton.LeftButton or not self.frame_rect().contains(event.position()):return
        c=self.project['cues'][self.selected]
        if not c['start']<=self.time<c['end']:return
        point=self.source_point(event.position());boxes=copy.deepcopy(active_covers(c,self.time))
        tolerance=12*self.source_size()[0]/max(1,self.frame_rect().width())
        for i in reversed(range(len(boxes))):
            x,y,w,h=boxes[i]
            if abs(point[0]-x-w)<tolerance and abs(point[1]-y-h)<tolerance:
                self.drag=('resize',i,point,boxes);return
            if x<=point[0]<=x+w and y<=point[1]<=y+h:
                self.drag=('move',i,point,boxes);return
        boxes.append([point[0],point[1],1,1]);self.drag=('new',len(boxes)-1,point,boxes)
    def mouseMoveEvent(self,event):
        if self.caption_resize:
            center,vector,base,target,size=self.caption_resize;point=self.source_point(event.position());w,h=self.source_size()
            ratio=((point[0]-center[0])*vector[0]+(point[1]-center[1])*vector[1])/max(1,vector[0]**2+vector[1]**2)
            ratio=max(.1/base,min(ratio,w/max(1,size[0]),h/max(1,size[1]),8/base))
            self.captionResized.emit(base*ratio,target);self.update();return
        if self.caption_drag:
            start,base,target,bounds=self.caption_drag;point=self.source_point(event.position());w,h=self.source_size()
            dx=max(-bounds[0],min(w-bounds[2],point[0]-start[0]));dy=max(-bounds[1],min(h-bounds[3],point[1]-start[1]))
            # Snap to the centre only after a real move (a click must not edit), and never with Alt held.
            px=w/max(1,self.frame_rect().width());moved=abs(point[0]-start[0])+abs(point[1]-start[1])>3*px
            self.snap_guide=False
            if moved and not event.modifiers()&Qt.KeyboardModifier.AltModifier:dx,self.snap_guide=snap_center(bounds[0],bounds[2],dx,w,10*px)
            self.captionMoved.emit(base[0]+dx/w,base[1]+dy/h,target);self.update();return
        if not self.drag:
            hovering=False;resize_cursor=None
            if self.live and self.drag_subtitles and not self.edit_covers and self.project and self.frame_rect().contains(event.position()):
                point=self.source_point(event.position());w,h=self.source_size()
                for _,shown in display_cues(self.project):
                    if shown['start']<=self.time<shown['end']:
                        blocks=caption_blocks(shown,self.project,w,h,self.time)
                        if blocks:
                            left,top,right,bottom=caption_bounds(blocks)
                            tolerance=10*w/max(1,self.frame_rect().width())
                            for n,(x,y) in enumerate(((left,top),(right,top),(left,bottom),(right,bottom))):
                                if abs(point[0]-x)<=tolerance and abs(point[1]-y)<=tolerance:resize_cursor=Qt.CursorShape.SizeFDiagCursor if n in (0,3) else Qt.CursorShape.SizeBDiagCursor
                            hovering|=left<=point[0]<=right and top<=point[1]<=bottom
            self.setCursor(resize_cursor or (Qt.CursorShape.OpenHandCursor if hovering else Qt.CursorShape.ArrowCursor));return
        mode,index,start,original=self.drag;point=self.source_point(event.position());boxes=copy.deepcopy(original);x,y,bw,bh=original[index];w,h=self.source_size()
        if mode=='move':boxes[index]=[max(0,min(w-bw,x+point[0]-start[0])),max(0,min(h-bh,y+point[1]-start[1])),bw,bh]
        elif mode=='resize':boxes[index]=[x,y,max(1,point[0]-x),max(1,point[1]-y)]
        else:boxes[index]=[min(start[0],point[0]),min(start[1],point[1]),max(1,abs(point[0]-start[0])),max(1,abs(point[1]-start[1]))]
        self.boxesEdited.emit([[round(v) for v in box] for box in boxes]);self.update()
    def mouseReleaseEvent(self,event):
        if self.caption_resize:
            self.mouseMoveEvent(event);self.caption_resize=None;self.unsetCursor();return
        if self.caption_drag:
            self.mouseMoveEvent(event);self.caption_drag=None;self.snap_guide=False;self.unsetCursor();self._animate('_lift',0,160);return
        if self.drag:self.mouseMoveEvent(event);self.drag=None
