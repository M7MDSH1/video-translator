"""UI motion for the desktop app (approved design: design/motion-preview.html).

Every helper snaps to the final state when the widget is hidden, the platform is offscreen (tests),
or Windows animation effects are off (Settings > Accessibility > Visual effects).
Live video, table selection, typing and the seek bar are deliberately never animated.
"""
import sys,time
from PySide6.QtCore import (Qt,QEasingCurve,QPointF,QRectF,QPropertyAnimation,QVariantAnimation,QTimer,QEvent,Signal)
from PySide6.QtGui import QColor,QPainter,QPen,QLinearGradient,QGuiApplication,QFont
from PySide6.QtWidgets import (QPushButton,QStylePainter,QStyleOptionButton,QStyle,QTabBar,QTabWidget,QProgressBar,
    QGraphicsOpacityEffect,QStyledItemDelegate,QWidget,QFrame,QHBoxLayout,QLabel)

TEAL='#57D6B5'
EASE_OUT=QEasingCurve(QEasingCurve.Type.BezierSpline)  # cubic-bezier(0.23, 1, 0.32, 1): fast start, gentle settle
EASE_OUT.addCubicBezierSegment(QPointF(.23,1),QPointF(.32,1),QPointF(1,1))
SPRING=QEasingCurve(QEasingCurve.Type.OutBack);SPRING.setOvershoot(1.2)  # small overshoot for the press spring-back

def enabled(widget):
    return widget.isVisible() and system_allows()

FORCE=None  # tests set True to run real animations on the offscreen platform

def system_allows():
    if FORCE is not None:return FORCE
    if QGuiApplication.platformName()=='offscreen':return False
    if sys.platform!='win32':return True
    return windows_animations_on()

def windows_animations_on():
    """Settings > Accessibility > Visual effects > Animation effects. Defaults to on if Windows cannot say."""
    try:
        import ctypes
        from ctypes import wintypes
        call=ctypes.windll.user32.SystemParametersInfoW
        call.argtypes=[wintypes.UINT,wintypes.UINT,ctypes.c_void_p,wintypes.UINT];call.restype=wintypes.BOOL
        on=wintypes.BOOL(1)  # Windows writes a 4-byte BOOL; a 1-byte c_bool would let it overwrite memory
        if not call(0x1042,0,ctypes.byref(on),0):return True  # SPI_GETCLIENTAREAANIMATION
        return bool(on.value)
    except (AttributeError,OSError):return True

def _tween(owner,name,start,end,ms,curve,step,done=None,loop=False):
    """One reusable QVariantAnimation per (owner, name); kept on the owner so it is not garbage-collected."""
    store=owner.__dict__.setdefault('_tweens',{})
    anim=store.get(name)
    if anim:anim.stop();anim.deleteLater()
    anim=store[name]=QVariantAnimation(owner);anim.setDuration(ms);anim.setEasingCurve(curve)
    anim.setStartValue(start);anim.setEndValue(end);anim.valueChanged.connect(step)
    if loop:anim.setLoopCount(-1)
    if done:anim.finished.connect(done)
    anim.start();return anim

def stop(owner,name):
    anim=owner.__dict__.get('_tweens',{}).pop(name,None)
    if anim:anim.stop();anim.deleteLater()

def progress_to(bar,value):
    """Glide forward to a new value; resets and stage restarts (lower values) snap."""
    stop(bar,'value')
    if value<=bar.value() or not enabled(bar):bar.setValue(value);return
    _tween(bar,'value',bar.value(),value,250,EASE_OUT,lambda v:bar.setValue(int(v)))

def flash(label,end,start=TEAL,ms=600):
    """Briefly colour a label teal, then fade it back to its normal colour (rare success moments only)."""
    if not enabled(label):stop(label,'flash');label.setStyleSheet('');return
    label.setStyleSheet(f'color:{start}')
    _tween(label,'flash',QColor(start),QColor(end),ms,EASE_OUT,lambda c:label.setStyleSheet(f'color:{c.name()}'),
           lambda:label.setStyleSheet(''))  # hand colour back to the app stylesheet role

def reveal(body,show,ms=220):
    """Accordion: grow or shrink the body's height instead of snapping it open or closed."""
    limit=body.__dict__.setdefault('_own_max',body.maximumHeight())  # e.g. the log's 80 px cap survives
    if not enabled(body.parentWidget() or body):
        stop(body,'reveal');body.setMaximumHeight(limit);body.setVisible(show);return
    if show:
        body.setMaximumHeight(0);body.show()
        _tween(body,'reveal',0,min(body.sizeHint().height(),limit),ms,EASE_OUT,lambda v:body.setMaximumHeight(int(v)),
               lambda:body.setMaximumHeight(limit))
    else:
        _tween(body,'reveal',body.height(),0,ms,EASE_OUT,lambda v:body.setMaximumHeight(int(v)),
               lambda:(body.hide(),body.setMaximumHeight(limit)))

def fade_in(widget,ms=220,delay=0,rise_layout=None,rise=8):
    """Fade a widget in (and lift its layout a few pixels). The effect is removed afterwards.
    Never use on anything that contains the live video player."""
    stop(widget,'fade')
    # The layout's own margins, remembered once, so an interrupted lift never becomes the new resting place.
    base=widget.__dict__.setdefault('_rise_base',rise_layout.contentsMargins()) if rise_layout is not None else None
    if not enabled(widget):
        widget.setGraphicsEffect(None)
        if rise_layout is not None:rise_layout.setContentsMargins(base)
        return
    effect=QGraphicsOpacityEffect(widget);effect.setOpacity(0);widget.setGraphicsEffect(effect)
    def step(v):
        effect.setOpacity(v)
        if rise_layout is not None:rise_layout.setContentsMargins(base.left(),base.top()+round(rise*(1-v)),base.right(),base.bottom())
    def done():widget.setGraphicsEffect(None)
    def start():
        if widget.graphicsEffect() is effect:_tween(widget,'fade',0.,1.,ms,EASE_OUT,step,done)
    QTimer.singleShot(delay,start) if delay else start()

def fade_window(dialog,ms=180):
    """Fade a dialog in as it opens; Windows cannot scale top-level windows smoothly, so it only fades."""
    if not system_allows():return
    dialog.setWindowOpacity(0)
    def start():_tween(dialog,'window',0.,1.,ms,EASE_OUT,dialog.setWindowOpacity,lambda:dialog.setWindowOpacity(1))
    QTimer.singleShot(0,start)
    QTimer.singleShot(ms+400,lambda:dialog.setWindowOpacity(1))  # never leave an invisible modal behind

class MotionButton(QPushButton):
    """Hover eases in, a press shrinks to 97 % and springs back, pulse() rings once when the button becomes the next step."""
    def __init__(self,*args):
        super().__init__(*args);self._hover=0.;self._press=1.;self._ring=0.
    def _go(self,name,end,ms,curve):
        if not enabled(self):stop(self,name);setattr(self,name,end);self.update();return
        _tween(self,name,float(getattr(self,name)),float(end),ms,curve,lambda v:(setattr(self,name,v),self.update()))
    def enterEvent(self,e):
        if self.isEnabled():self._go('_hover',1,150,EASE_OUT)
        super().enterEvent(e)
    def leaveEvent(self,e):self._go('_hover',0,150,EASE_OUT);super().leaveEvent(e)
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton and self.isEnabled():self._go('_press',.97,120,EASE_OUT)
        super().mousePressEvent(e)
    def mouseReleaseEvent(self,e):self._go('_press',1,280,SPRING);super().mouseReleaseEvent(e)
    def changeEvent(self,e):
        if e.type()==QEvent.Type.EnabledChange and not self.isEnabled():  # leaveEvent may never arrive
            for n in ('_hover','_press'):stop(self,n)
            self._hover=0.;self._press=1.
        super().changeEvent(e)
    def pulse(self):
        if enabled(self):_tween(self,'_ring',1.,0.,900,QEasingCurve(QEasingCurve.Type.OutQuad),lambda v:(setattr(self,'_ring',v),self.update()))
    def paintEvent(self,e):
        p=QStylePainter(self);opt=QStyleOptionButton();self.initStyleOption(opt)
        opt.state&=~QStyle.StateFlag.State_MouseOver  # the eased overlay below replaces the instant hover style
        if self._press!=1:
            c=QRectF(self.rect()).center();p.translate(c);p.scale(self._press,self._press);p.translate(-c)
        p.drawControl(QStyle.ControlElement.CE_PushButton,opt)
        if (self._hover>0 and self.isEnabled()) or self._ring>0:
            p.setRenderHint(QPainter.RenderHint.Antialiasing);r=QRectF(self.rect()).adjusted(.5,.5,-.5,-.5)
            if self._hover>0 and self.isEnabled():
                p.setPen(QPen(QColor(87,214,181,int(255*self._hover)),1));p.setBrush(QColor(255,255,255,int(22*self._hover)))
                p.drawRoundedRect(r,6,6)
            if self._ring>0:
                ring=QColor(255,255,255) if self.property('primary') else QColor(TEAL);ring.setAlpha(int(255*self._ring))  # teal on a teal button would vanish
                p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(ring,3))
                p.drawRoundedRect(r.adjusted(2,2,-2,-2),5,5)

class PillTabBar(QTabBar):
    """A teal highlight slides from the old step tab to the new one."""
    def __init__(self):
        super().__init__();self._pill=None;self.currentChanged.connect(self._move)
    def _target(self,i):return QRectF(self.tabRect(i)).adjusted(4,4,-4,-4)  # the stylesheet's 4 px tab margin
    def _set(self,r):self._pill=r;self.update()
    def _move(self,i):
        if i<0:return
        if self._pill is None or not enabled(self):stop(self,'pill');self._set(self._target(i));return
        _tween(self,'pill',QRectF(self._pill),self._target(i),280,EASE_OUT,self._set)
    def _snap(self):
        stop(self,'pill')
        if self.currentIndex()>=0:self._set(self._target(self.currentIndex()))
    def resizeEvent(self,e):super().resizeEvent(e);self._snap()
    def showEvent(self,e):super().showEvent(e);self._snap()
    def tabLayoutChange(self):super().tabLayoutChange();self._snap()
    def paintEvent(self,e):
        if self._pill is not None and self.count():
            p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setOpacity(1 if self.isEnabled() else .45)
            p.setPen(QPen(QColor('#459E8B'),1));p.setBrush(QColor('#203E3C'));p.drawRoundedRect(self._pill.adjusted(.5,.5,-.5,-.5),6,6);p.end()
        super().paintEvent(e)

class PillTabWidget(QTabWidget):
    def __init__(self,*args):
        super().__init__(*args);bar=PillTabBar();bar.setDrawBase(False);self.setTabBar(bar)

class GlideBar(QProgressBar):
    """Thin progress strip. While busy (range 0-0) a shine runs along it; the loop stops when it is not busy."""
    def __init__(self):super().__init__();self._phase=0.;self.setTextVisible(False);self.setFixedHeight(6)
    def setRange(self,low,high):
        super().setRange(low,high)
        if low==high==0 and enabled(self):_tween(self,'shine',0.,1.,1300,QEasingCurve(QEasingCurve.Type.Linear),self._shine,loop=True)
        else:stop(self,'shine')
        self.update()
    def _shine(self,v):self._phase=v;self.update()
    def hideEvent(self,e):stop(self,'shine');super().hideEvent(e)
    def paintEvent(self,e):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);r=QRectF(self.rect());radius=r.height()/2
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#253241'));p.drawRoundedRect(r,radius,radius)
        if self.maximum()==self.minimum()==0:
            band=r.width()*.45;x=-band+(r.width()+band)*self._phase
            g=QLinearGradient(x,0,x+band,0);g.setColorAt(0,QColor(87,214,181,0));g.setColorAt(.5,QColor(TEAL));g.setColorAt(1,QColor(87,214,181,0))
            p.setBrush(g);p.drawRoundedRect(r,radius,radius)
        elif self.maximum()>self.minimum():
            share=(self.value()-self.minimum())/(self.maximum()-self.minimum())
            if share>0:p.setBrush(QColor(TEAL));p.drawRoundedRect(QRectF(r.x(),r.y(),r.width()*share,r.height()),radius,radius)

class StepStrip(QWidget):
    """✓ done · ● running (breathes while a job runs) · ○ to come · ✕ failed, plus a detail on the right.
    Painted, not rich text, so the breathing dot does not relayout the window every frame."""
    def __init__(self):
        super().__init__();self.names=[];self.index=0;self.failed=False;self.detail='';self._breath=0.;self._pop={}
        self.setFixedHeight(24);self.hide()
    def set(self,names,index,failed=False,detail='',running=True):
        newly=[i for i in range(self.index,min(index,len(names))) if names==self.names]
        self.names,self.index,self.failed,self.detail=names,index,failed,detail
        for i in newly:  # a ✓ pops in for each step that just finished
            self._pop[i]=0.
            if enabled(self):_tween(self,f'pop{i}',0.,1.,260,SPRING,lambda v,i=i:(self._pop.__setitem__(i,v),self.update()),lambda i=i:self._pop.pop(i,None))
            else:self._pop.pop(i,None)
        live=running and not failed and index<len(names)
        if live and enabled(self):
            if 'breath' not in self.__dict__.get('_tweens',{}):
                curve=QEasingCurve(QEasingCurve.Type.InOutSine)
                _tween(self,'breath',0.,1.,1400,curve,lambda v:(setattr(self,'_breath',v),self.update()),loop=True)
        else:stop(self,'breath');self._breath=0.
        self.show();self.update()
    def stop(self):stop(self,'breath');self._breath=0.;self.update()
    def hideEvent(self,e):self.stop();super().hideEvent(e)
    def paintEvent(self,e):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);fm=p.fontMetrics();y=self.height()/2;x=0.
        bold=QFont(self.font());bold.setBold(True)
        for i,name in enumerate(self.names):
            if i:
                p.setPen(QColor('#82909F'));p.drawText(QPointF(x+6,y+fm.ascent()/2-1),'›');x+=6+fm.horizontalAdvance('›')+8
            done=i<self.index;now=i==self.index
            color=QColor(TEAL) if done else QColor('#FF8A80') if now and self.failed else QColor('#EDF2FA') if now else QColor('#82909F')
            p.setPen(color);cx=x+6
            if done:
                s=self._pop.get(i,1.);p.save();p.translate(cx,y);p.scale(max(.01,s),max(.01,s));p.setPen(QPen(color,1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
                p.drawPolyline([QPointF(-4,0),QPointF(-1,3),QPointF(4,-3)]);p.restore()
            elif now and self.failed:
                p.setPen(QPen(color,1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));p.drawLine(QPointF(cx-3.5,y-3.5),QPointF(cx+3.5,y+3.5));p.drawLine(QPointF(cx+3.5,y-3.5),QPointF(cx-3.5,y+3.5))
            elif now:
                b=self._breath;p.setPen(Qt.PenStyle.NoPen);c=QColor(color);c.setAlphaF(1-.45*b);p.setBrush(c);r=4*(1+.4*b);p.drawEllipse(QPointF(cx,y),r,r)
            else:
                p.setPen(QPen(color,1.2));p.setBrush(Qt.BrushStyle.NoBrush);p.drawEllipse(QPointF(cx,y),3.5,3.5)
            x+=16;p.setFont(bold if now else self.font());p.setPen(color);p.drawText(QPointF(x,y+fm.ascent()/2-1),name)
            x+=p.fontMetrics().horizontalAdvance(name);p.setFont(self.font())
        if self.detail:
            p.setPen(QColor('#B0BDCE'));w=fm.horizontalAdvance(self.detail);p.drawText(QPointF(self.width()-w,y+fm.ascent()/2-1),self.detail)

class RowFlash(QStyledItemDelegate):
    """Teal row highlights that fade out: new translations after a job, and a line you just saved."""
    def __init__(self,table):
        super().__init__(table);self.table=table;self.rows={};self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self._tick)
    def flash(self,rows,ms=1400,peak=.32,stagger=0):
        if not enabled(self.table):return
        now=time.monotonic()
        for n,r in enumerate(rows):self.rows[r]=(now+n*stagger/1000,ms/1000,peak)
        self.timer.start()
    def alpha(self,row):
        if row not in self.rows:return 0.
        start,length,peak=self.rows[row];t=(time.monotonic()-start)/length
        return peak if t<0 else peak*(1-EASE_OUT.valueForProgress(min(1,t)))
    def _tick(self):
        now=time.monotonic()
        for r,(start,length,_) in list(self.rows.items()):
            if now>start+length:del self.rows[r]
        if not self.rows:self.timer.stop()
        self.table.viewport().update()
    def paint(self,painter,option,index):
        super().paint(painter,option,index)
        a=self.alpha(index.row())
        if a>0:painter.fillRect(option.rect,QColor(87,214,181,int(255*a)))  # over the cell: selection colour must not hide it

class Toast(QFrame):
    """Bottom-right notification that slides in, stays 3.5 s and leaves the same way. Never takes focus."""
    closed=Signal()
    def __init__(self,parent,text,action=None,callback=None):
        super().__init__(parent);self.setObjectName('toast');self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet('#toast{background:#1F2B38;border:1px solid #2F6E62;border-radius:8px;} QLabel{background:transparent;}')
        row=QHBoxLayout(self);row.setContentsMargins(12,8,8 if action else 12,8);row.setSpacing(10)
        tick=QLabel('✓');tick.setStyleSheet(f'color:{TEAL};font-weight:700;');row.addWidget(tick);row.addWidget(QLabel(text))
        if action:
            b=MotionButton(action);b.setFocusPolicy(Qt.FocusPolicy.NoFocus);b.clicked.connect(callback);b.clicked.connect(self.leave);row.addWidget(b)
        self.adjustSize();self._shift=0.;self.effect=QGraphicsOpacityEffect(self);self.setGraphicsEffect(self.effect)
        QTimer.singleShot(3500,self.leave);self._leaving=False
    def enter(self):
        self.show();self.raise_()
        if not enabled(self):self.effect.setOpacity(1);return
        self.effect.setOpacity(0);self._shift=12.
        _tween(self,'move',0.,1.,260,EASE_OUT,self._step)
    placer=None  # the window's function that stacks toasts in the bottom-right corner
    def _step(self,v):
        self.effect.setOpacity(v);self._shift=12*(1-v)
        if self.placer:self.placer()
    def leave(self):
        if self._leaving:return
        self._leaving=True
        if not enabled(self):self._gone();return
        _tween(self,'move',1.,0.,180,EASE_OUT,self._step,self._gone)
    def _gone(self):self.hide();self.closed.emit();self.deleteLater()
