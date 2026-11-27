import copy
import json
import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QProcess, QTimer, QRectF, Signal, QLocale
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QPushButton,QLabel,QLineEdit,QComboBox,QDoubleSpinBox,QSpinBox,QCheckBox,QFileDialog,QMessageBox,
    QTabWidget,QSplitter,QTableWidget,QTableWidgetItem,QHeaderView,QProgressBar,QPlainTextEdit,QDialog,
    QDialogButtonBox,QFontComboBox,QSlider,QGroupBox,QScrollArea)
from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
from .live_video import LiveVideoWidget
from .project import ROOT, LANGUAGES,new_project,save_project,load_project,fingerprint,approved,validate
from .engine import probe
from .subtitles import cue
from .typography import khaam_style,arabic_warnings
from . import job_steps,motion
VIDEO_TYPES={'.mp4','.mkv','.mov','.avi','.webm','.m4v'}
from .workspace_ui import APPEARANCES
APPEARANCE_KEYS=[key for key,_ in APPEARANCES]

def button(label,fn):
    b=motion.MotionButton(label);b.clicked.connect(fn);return b

def number(low,high,value,decimals=2):
    w=QDoubleSpinBox();w.setRange(low,high);w.setDecimals(decimals);w.setValue(value);return w

def installed_models():
    """Local Ollama model names; cloud/remote entries are left out (the worker refuses them)."""
    import requests
    r=requests.get('http://127.0.0.1:11434/api/tags',timeout=(2,5),allow_redirects=False);r.raise_for_status()
    return sorted(m['name'] for m in r.json().get('models',[]) if not m.get('remote_host') and not m.get('remote_model') and 'cloud' not in m['name'].lower())

def combo(items):
    w=QComboBox();w.addItems(items);return w

def clock_time(seconds):
    seconds=max(0,int(seconds));hours,seconds=divmod(seconds,3600);minutes,seconds=divmod(seconds,60)
    return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'

class FrameCanvas(QWidget):
    """Drag line rectangles in source pixel coordinates on a letterboxed frame."""
    changed=Signal()
    def __init__(self,frame,boxes=None,parent=None):
        super().__init__(parent);self.setMinimumSize(720,405)
        h,w,ch=frame.shape;self.pix=QPixmap.fromImage(QImage(frame.data,w,h,frame.strides[0],QImage.Format.Format_BGR888).copy())
        self.boxes=copy.deepcopy(boxes or []);self.anchor=None;self.cursor=None;self.single=False
    def display_rect(self):
        size=self.pix.size();size.scale(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
    def point(self,p):
        r=self.display_rect()
        return [min(self.pix.width(),max(0,(p.x()-r.x())/r.width()*self.pix.width())),min(self.pix.height(),max(0,(p.y()-r.y())/r.height()*self.pix.height()))]
    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor('#10131a'));r=self.display_rect();painter.drawPixmap(r.toRect(),self.pix)
        boxes=list(self.boxes)
        if self.anchor and self.cursor:boxes.append([min(self.anchor[0],self.cursor[0]),min(self.anchor[1],self.cursor[1]),abs(self.cursor[0]-self.anchor[0]),abs(self.cursor[1]-self.anchor[1])])
        painter.setPen(QPen(QColor('#56dec1'),2))
        for i,(x,y,w,h) in enumerate(boxes):
            rr=QRectF(r.x()+x*r.width()/self.pix.width(),r.y()+y*r.height()/self.pix.height(),w*r.width()/self.pix.width(),h*r.height()/self.pix.height())
            painter.fillRect(rr,QColor(25,40,40,90));painter.drawRect(rr);painter.drawText(rr.topLeft(),str(i+1))
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:self.anchor=self.point(e.position());self.cursor=self.anchor
    def mouseMoveEvent(self,e):
        if self.anchor:self.cursor=self.point(e.position());self.update()
    def mouseReleaseEvent(self,e):
        if not self.anchor:return
        point=self.point(e.position());a=self.anchor
        box=[round(min(a[0],point[0])),round(min(a[1],point[1])),round(abs(a[0]-point[0])),round(abs(a[1]-point[1]))]
        if box[2]>2 and box[3]>2:
            if self.single:self.boxes=[]
            self.boxes.append(box);self.changed.emit()
        self.anchor=None;self.cursor=None;self.update()

def read_frame(path,time):
    import cv2
    cap=cv2.VideoCapture(str(path));cap.set(cv2.CAP_PROP_POS_MSEC,max(0,time)*1000);ok,frame=cap.read();cap.release()
    if not ok:raise ValueError('Cannot read this frame. Choose an earlier timestamp.')
    return frame

class RectangleDialog(QDialog):
    boxesChanged=Signal(list)
    def __init__(self,path,time,boxes,single=False,parent=None):
        super().__init__(parent);self.setWindowTitle('Select subtitle area' if single else 'Edit exact line covers');self.resize(1000,700)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('Drag one rectangle around the subtitle area.' if single else 'Drag a separate tight rectangle for each visible line. Clear first to replace the existing boxes.'))
        self.canvas=FrameCanvas(read_frame(path,time),boxes);self.canvas.single=single;layout.addWidget(self.canvas,1)
        self.values=QPlainTextEdit();self.values.setMaximumHeight(80);layout.addWidget(QLabel('Pixel rectangles: [x, y, width, height]. You can also edit these numbers.'));layout.addWidget(self.values)
        self.canvas.changed.connect(self.sync);self.sync()
        self.values.textChanged.connect(self.live_numbers)
        row=QHBoxLayout();row.addWidget(button('Clear rectangles',self.clear));row.addWidget(button('Apply numbers',self.apply_numbers));layout.addLayout(row)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.finish);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def sync(self):self.values.setPlainText(json.dumps(self.canvas.boxes));self.boxesChanged.emit(copy.deepcopy(self.canvas.boxes))
    def live_numbers(self):
        try:
            boxes=json.loads(self.values.toPlainText());w,h=self.canvas.pix.width(),self.canvas.pix.height()
            if not isinstance(boxes,list) or (self.canvas.single and len(boxes)!=1):return
            for x,y,bw,bh in boxes:
                if min(x,y)<0 or bw<=0 or bh<=0 or x+bw>w or y+bh>h:return
            self.canvas.boxes=boxes;self.canvas.update();self.boxesChanged.emit(copy.deepcopy(boxes))
        except (ValueError,TypeError):pass
    def clear(self):self.canvas.boxes=[];self.canvas.update();self.sync()
    def apply_numbers(self):
        try:
            boxes=json.loads(self.values.toPlainText())
            if not isinstance(boxes,list) or any(len(b)!=4 or not all(isinstance(v,(int,float)) for v in b) for b in boxes):raise ValueError('Use a list of [x,y,width,height] rectangles.')
            if self.canvas.single and len(boxes)!=1:raise ValueError('Select exactly one OCR area.')
            w,h=self.canvas.pix.width(),self.canvas.pix.height()
            for x,y,bw,bh in boxes:
                if min(x,y)<0 or bw<=0 or bh<=0 or x+bw>w or y+bh>h:raise ValueError('Rectangles must stay inside the frame.')
            self.canvas.boxes=boxes;self.canvas.update();self.boxesChanged.emit(copy.deepcopy(boxes));return True
        except Exception as exc:QMessageBox.warning(self,'Invalid rectangles',str(exc));return False
    def finish(self):
        if self.apply_numbers():self.accept()

class CueDialog(QDialog):
    draftChanged=Signal(dict)
    def __init__(self,c,duration,parent=None):
        super().__init__(parent);self.setWindowTitle('Review subtitle');self.resize(850,450);self.c=copy.deepcopy(c)
        layout=QVBoxLayout(self);form=QFormLayout();self.start=number(0,duration,c['start'],3);self.end=number(0,duration,c['end'],3)
        form.addRow('Start (seconds)',self.start);form.addRow('End (seconds)',self.end);layout.addLayout(form)
        row=QHBoxLayout();self.original=QPlainTextEdit(c['original']);self.translation=QPlainTextEdit(c['translation'])
        for title,widget in [('Original text',self.original),('Translation — keep intentional line breaks',self.translation)]:
            col=QVBoxLayout();col.addWidget(QLabel(title));col.addWidget(widget);row.addLayout(col)
        layout.addLayout(row);self.reviewed=QCheckBox('I reviewed this text, timing and cover placement');self.reviewed.setChecked(c.get('reviewed',False));layout.addWidget(self.reviewed)
        layout.addWidget(QLabel('Flags: '+', '.join(c.get('flags',[]))))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.finish);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.translation.textChanged.connect(self.emit_draft);self.start.valueChanged.connect(self.emit_draft);self.end.valueChanged.connect(self.emit_draft)
    def emit_draft(self):
        if self.end.value()<=self.start.value():return
        draft=copy.deepcopy(self.c);draft.update(start=self.start.value(),end=self.end.value(),translation=self.translation.toPlainText());self.draftChanged.emit(draft)
    def finish(self):
        if self.end.value()<=self.start.value():QMessageBox.warning(self,'Timing','End must be after start.');return
        if self.start.value()!=self.c['start'] or self.end.value()!=self.c['end']:
            if 'cover_spans' in self.c:
                spans=[]
                for span in self.c['cover_spans']:
                    a=max(self.start.value(),span['start']);b=min(self.end.value(),span['end'])
                    if b>a:spans.append(dict(span,start=a,end=b))
                self.c['cover_spans']=spans
                if not spans:self.c['boxes']=[]
                if self.start.value()<self.c['start'] or self.end.value()>self.c['end']:
                    self.c.setdefault('flags',[]).append('Timing extended beyond detected covers; review or redetect covers')
        self.c.update(start=self.start.value(),end=self.end.value(),original=self.original.toPlainText(),translation=self.translation.toPlainText(),reviewed=self.reviewed.isChecked());self.accept()

class MainWindow(QMainWindow):
    update_found=Signal(dict)  # from the background check to the window
    def __init__(self):
        super().__init__();self.setWindowTitle('Local Video Translator');self.resize(1440,950)
        self.p=None;self.path=None;self.proc=None;self.buffer='';self._loading=False;self._editing_fields=False
        self.autosave=QTimer(self);self.autosave.setSingleShot(True);self.autosave.setInterval(700);self.autosave.timeout.connect(self.save_live_edits)
        from .workspace_ui import build
        self.update_info=None;self.update_found.connect(self.show_update)
        build(self)
        self.live_text.textChanged.connect(self.live_text_changed);self.live_start.valueChanged.connect(self.live_timing_changed);self.live_end.valueChanged.connect(self.live_timing_changed)
        self.live_boxes.textChanged.connect(self.live_boxes_input);self.draw_covers.toggled.connect(self.toggle_cover_edit)
        for control in (self.size,self.minimum_size,self.x,self.y,self.padding,self.line_height):control.valueChanged.connect(self.live_style_changed)
        self.font.currentFontChanged.connect(self.live_style_changed);self.bold.toggled.connect(self.live_style_changed);self.color.textChanged.connect(self.live_style_changed)
        self.appearance.currentIndexChanged.connect(self.live_style_changed);self.kind.currentIndexChanged.connect(self.live_style_changed)
        self.mode.currentIndexChanged.connect(self.update_setup_mode)
        for control in (self.mode,self.source,self.target,self.script,self.model,self.asr,self.kind):
            control.currentTextChanged.connect(self.settings_changed)
        for control in (self.interval,self.track):control.valueChanged.connect(self.settings_changed)
        for control in (self.begin,self.end):control.valueChanged.connect(self.range_changed)
        self.full_video.toggled.connect(self.select_full_video)
        self.model.currentTextChanged.connect(self.update_model_status)
        self.audio_track.currentIndexChanged.connect(self.settings_changed)
        self.preview_start.editingFinished.connect(self.preview_range_changed);self.preview_length.editingFinished.connect(self.preview_range_changed)
        self.elapsed=QTimer(self);self.elapsed.setInterval(1000);self.elapsed.timeout.connect(self.update_elapsed)
        self.update_setup_mode();self.refresh_approval()
        self.model_refresh_timer=QTimer(self);self.model_refresh_timer.setSingleShot(True)
        self.model_refresh_timer.timeout.connect(lambda:self.refresh_models(quiet=True))
        self.model_refresh_timer.start(700)  # the Ollama check blocks briefly; run it after the launch fade, not during it
        self.toasts=[];self._launched=False;self.job_running=False;self.setAcceptDrops(True)
        self._undo=[];self._redo=[];self._undo_for=None;self._undo_tag=None
        # Space and Enter act only while the video or the subtitle table has focus, so typing in a field is unaffected.
        for keys,fn,scope in [('Ctrl+Z',self.undo,self),('Ctrl+Y',lambda:self.undo(redo=True),self),('Space',self.toggle_play,self.review_split),
                              ('Return',self.edit_cue,self.table),('Ctrl+Return',self.review_and_next,self.review_split)]:
            QShortcut(QKeySequence(keys),scope,fn).setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        # Text fields would paste a dropped file's path into a subtitle; videos dropped anywhere open instead.
        for field in self.findChildren(QLineEdit)+self.findChildren(QPlainTextEdit):field.setAcceptDrops(False)
    def showEvent(self,event):
        super().showEvent(event)
        if not self._launched:
            self._launched=True
            for n,part in enumerate(self.start.launch_parts):motion.fade_in(part,340,30+n*50)  # hidden now, rising after the first layout
    def checkpoint(self,tag=None):
        """Remember the subtitles before an edit, for Ctrl+Z. Edits in a row with the same tag (typing in one line) are one step."""
        if not self.p:return
        if self._undo_for is not self.p:self._undo=[];self._redo=[];self._undo_for=self.p;self._undo_tag=None  # a finished job reloads the project
        if tag is not None and tag==self._undo_tag:return
        self._undo_tag=tag;self._redo.clear();self._undo.append(copy.deepcopy(self.p['cues']));del self._undo[:-50]
    def undo(self,redo=False):
        if not self.p or self.stack.currentIndex()!=1 or not self.idle():return
        source,other=(self._redo,self._undo) if redo else (self._undo,self._redo)
        if self._undo_for is not self.p or not source:self.status.setText('Nothing to redo.' if redo else 'Nothing to undo.');return
        other.append(copy.deepcopy(self.p['cues']));self.p['cues']=source.pop();self._undo_tag=None
        self.refresh();self.autosave.start();self.status.setText('Redone.' if redo else 'Undone. Ctrl+Y brings it back.')
    def review_and_next(self):
        r=self.selected()
        if r is None or not self.idle():return
        self.mark_reviewed()
        following=next((i for i in range(r+1,len(self.p['cues'])) if not self.p['cues'][i].get('reviewed') and not self.table.isRowHidden(i)),None)
        if following is not None:self.table.selectRow(following)
    def toast(self,text,action=None,callback=None):
        t=motion.Toast(self.centralWidget(),text,action,callback);t.placer=self.place_toasts;self.toasts.append(t)
        t.closed.connect(lambda t=t:(self.toasts.remove(t) if t in self.toasts else None,self.place_toasts()))
        self.place_toasts();t.enter()
    def place_toasts(self):
        area=self.centralWidget();y=area.height()-16
        for t in reversed(self.toasts):
            y-=t.height();t.move(area.width()-16-t.width(),y+round(t._shift));t.raise_();y-=8
    def resizeEvent(self,event):super().resizeEvent(event);self.place_toasts()
    def dropped_video(self,event):
        urls=event.mimeData().urls() if event.mimeData().hasUrls() else []
        path=urls[0].toLocalFile() if len(urls)==1 else ''
        return path if path and Path(path).suffix.lower() in VIDEO_TYPES and Path(path).is_file() else ''
    def dragEnterEvent(self,event):
        if self.p is None and self.dropped_video(event):  # start screen only: a drop never replaces an open project
            event.acceptProposedAction();self.start.drop.set_hot(True)
    def dragLeaveEvent(self,event):self.start.drop.set_hot(False)
    def dropEvent(self,event):
        self.start.drop.set_hot(False);path=self.dropped_video(event)
        if path and self.p is None:event.acceptProposedAction();self.open_video(path,self.start.appearance())
    def show_workspace(self):
        if self.stack.currentIndex()!=1:
            self.stack.setCurrentIndex(1)
            for n,part in enumerate(self.workspace_parts):motion.fade_in(part,260,n*40)
    def go_home(self):
        """Back to the start screen: save the project, release the video, and allow new drops."""
        if not self.idle():return
        self.autosave.stop()
        if self.p and self.path:
            try:self.collect();save_project(self.p,self.path)
            except Exception as exc:self.error(exc);return
        self.player.stop();self.player.setSource(QUrl());self.p=None;self.path=None
        self.video.set_project(None);self.video.frame=QImage();self.table.setRowCount(0)
        self.start.refresh();self.stack.setCurrentIndex(0);motion.fade_in(self.start,220)

    def style_panel_setup(self):
        self.style_panel=QGroupBox('LIVE TEXT STYLE • all subtitles');form=QFormLayout(self.style_panel)
        self.drag_caption=QCheckBox('Drag / resize subtitle in video');self.drag_caption.setChecked(True)
        self.drag_caption.toggled.connect(self.toggle_caption_drag);form.addRow(self.drag_caption)
        self.drag_scope=combo(['All subtitles','Only selected subtitle']);self.drag_scope.currentIndexChanged.connect(lambda i:setattr(self.video,'caption_scope','selected' if i else 'all'));form.addRow('Move',self.drag_scope)
        form.addRow(button('Reset dragged position',self.reset_caption_position))
        form.addRow(button('Reset dragged size',self.reset_caption_size))
        drag_hint=QLabel('Drag the text to move it. Drag a teal corner to make it larger or smaller around its centre. Original-text covers stay in place.');drag_hint.setWordWrap(True);form.addRow(drag_hint)
        self.font=QFontComboBox();self.font.setCurrentFont(QFont('Arial'));self.size=number(12,180,48,0);self.bold=QCheckBox('Bold');self.bold.setChecked(True)
        self.size.setToolTip('Requested size. Replacement lines share a consistent caption size; Minimum size prevents tiny lettering by widening individual line covers.')
        self.font.setToolTip('Fonts without Arabic glyphs use Almarai for Arabic replacement text.')
        form.addRow('Font',self.font)
        row=QHBoxLayout();row.addWidget(self.size);row.addWidget(self.bold);form.addRow('Base size',row)
        self.minimum_size=number(1,64,26,0);self.minimum_size.setToolTip('Readable minimum for replacement text. Each line cover grows only as needed. Set 1 to keep the original tight bounds.')
        form.addRow('Minimum size',self.minimum_size)
        form.addRow(button('Apply Khaam Arabic style',self.apply_arabic_style));self.line_height=number(1.4,1.7,1.45,2);form.addRow('Line height',self.line_height)
        self.color=QLineEdit('#ffffff');self.y=number(.05,.98,.76,2);self.x=number(.05,.95,.5,2);self.padding=number(0,25,5,0)
        form.addRow('Horizontal position (0–1)',self.x)
        form.addRow('Color',self.color);form.addRow('Vertical position (0–1)',self.y);form.addRow('Cover padding',self.padding)
        hint=QLabel('Changes appear immediately in Live edits. Position uses 0–1 coordinates.');hint.setWordWrap(True);form.addRow(hint)

    def error(self,exc):QMessageBox.warning(self,'Video Translator',str(exc))
    def change_page(self,index):
        host=self.review_player_layout if index==1 else self.player_hosts[index]
        host.insertWidget(0,self.player_panel,1);self.player_panel.show()
        # Only the side panel fades and lifts; the video player is never inside a faded widget.
        if self.tabs.graphicsEffect() is None:motion.fade_in(self.side_panels[index],220,rise_layout=self.side_layouts[index])
        if index==1 and self.p:self.live_view()
        self.refresh_approval()

    def filter_rows(self):
        choice=self.review_filter.currentIndex()
        for i,c in enumerate((self.p or {}).get('cues',[])):
            show=(choice==0 or choice==1 and not c.get('reviewed') or choice==2 and bool(c.get('flags')) or choice==3 and bool(c.get('reviewed')))
            self.table.setRowHidden(i,not show)

    def update_setup_mode(self):
        speech=self.mode.currentIndex()==0
        self.ocr_panel.setVisible(not speech);self.speech_panel.setVisible(speech)

    def update_model_status(self):
        names=getattr(self,'_model_names',None)
        self.ollama_setup.setVisible(names is None or self.model.currentText() not in names)
        text=('Ollama unavailable · press Set up translation, then Refresh' if names is None else
              f'Ollama running · {self.model.currentText()} '+('installed' if self.model.currentText() in names else 'not installed locally'))
        self.model_status.setText(text)

    def pending_work(self):
        if not self.p:return False,False
        from .project import recognition_key
        baseline=self.p.get('ui_baseline',{})
        recognition=bool(self.p['cues'] and baseline.get('recognition') and baseline['recognition']!=recognition_key(self.p))
        translation=bool(self.p['cues'] and baseline.get('translation') and baseline['translation']!=[self.p['model'],self.p['target']])
        return recognition,translation

    def settings_changed(self,*args):
        if self._loading or not self.p:return
        try:
            self.collect()
            self.live_text.setLayoutDirection(Qt.LayoutDirection.RightToLeft if self.p['target'] in ('ar','fa','ur') else Qt.LayoutDirection.LeftToRight)
            if any(self.pending_work()):self.p['approval']=None
            self.refresh_approval();self.autosave.start()
        except ValueError as exc:self.run_hint.setText(str(exc))

    def select_full_video(self,checked):
        if self._loading or not self.p:return
        if checked:
            self.begin.blockSignals(True);self.end.blockSignals(True)
            self.begin.setValue(0);self.end.setValue(self.p['media']['duration'])
            self.begin.blockSignals(False);self.end.blockSignals(False)
        if not checked:self.advanced.setChecked(True)
        self.begin.setEnabled(not checked);self.end.setEnabled(not checked);self.settings_changed()

    def range_changed(self,*args):
        if self._loading or not self.p:return
        full=self.begin.value()==0 and abs(self.end.value()-self.p['media']['duration'])<.01
        self.full_video.blockSignals(True);self.full_video.setChecked(full);self.full_video.blockSignals(False)
        self.begin.setEnabled(not full);self.end.setEnabled(not full);self.settings_changed()

    def preview_range_changed(self):
        if not self.p or self._loading:return
        preview=self.p.get('preview') or {}
        length=min(self.preview_length.value(),self.p['media']['duration']-self.preview_start.value())
        if preview and (abs(preview['start']-self.preview_start.value())>.001 or abs(preview['duration']-length)>.001):
            self.p['preview']=None;self.p['approval']=None;self.refresh_approval();self.autosave.start()

    def update_elapsed(self):
        import time
        seconds=int(time.monotonic()-self.job_started)
        self.elapsed_label.setText(f'{seconds//60}:{seconds%60:02d} elapsed')

    def worker_error(self,error):
        if error==QProcess.ProcessError.FailedToStart:
            self.elapsed.stop();self.cancel.setEnabled(False);self.tabs.setEnabled(True);self.style_panel.setEnabled(True);self.table.setEnabled(True);self.video.setEnabled(True);self.populate_live_editor()
            if getattr(self,'step_names',None):self.end_steps(1)
            self.status.setText('Worker could not start. Check the local Python installation, then retry. Your project is saved.')

    def primary_process(self):
        if not self.p:self.error('Select a video first.');return
        recognition,_=self.pending_work()
        self.run('process' if recognition or not self.p['checkpoints'].get('recognized') else 'translate')

    def start_over(self):
        if not self.p or not self.idle():return
        try:
            self.collect()
            if QMessageBox.question(self,'Start over',f'This replaces all {len(self.p["cues"])} subtitles, including reviewed lines and hand corrections. A project backup will be saved first. Continue?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
            import time
            save_project(self.p,self.path.with_name('before-reprocess-'+str(time.time_ns())+'.json'))
            self.p['checkpoints']={};self.p['cues']=[];self.p['ocr_samples']=[];self.p['preview']=None;self.p['approval']=None
            self.run('process')
        except Exception as exc:self.error(exc)

    def open_export_video(self):
        path=(self.p or {}).get('last_export','')
        if path and Path(path).is_file():os.startfile(path)
        else:self.status.setText('Export first; the completed file will be available here.')
    def lock_dialogue_layout(self):
        if not self.p or not self.idle():return
        r=self.selected()
        if r is None:return
        try:
            from .dialogue import profile_from_cue,filter_project
            self.collect()
            profile=profile_from_cue(self.p['cues'][r],self.p['media']['width'],self.p['media']['height'])
            roi=self.p['roi'];bottom=min(1,profile['dialogue_y']+profile['vertical_drift']+profile['second_line_gap']+.03)
            roi[3]=max(roi[3],bottom-roi[1])
            count=filter_project(self.p,profile);self.save();self.refresh()
            self.status.setText(f'Dialogue layout locked. {count} other detections saved in excluded_cues; raw OCR retained.')
        except Exception as exc:self.error(exc)
    def edit_replacements(self):
        if not self.p or not self.idle():return
        from .replacement_dialog import ReplacementDialog
        from .replacements import apply_replacements
        self.player.pause();dialog=ReplacementDialog(self.p,self)
        motion.fade_window(dialog)
        if dialog.exec():
            try:
                draft=copy.deepcopy(self.p);draft['replacements']=dialog.settings()
                count=apply_replacements(draft,dialog.include_reviewed.isChecked()) if dialog.apply_now else 0
                validate(draft);save_project(draft,self.path);self.p=draft;self.refresh()
                if count:self.live_view()
                self.status.setText(f'Replacement rules saved. {count} existing subtitles changed.' if dialog.apply_now else 'Replacement rules saved for future translation/resume. Existing subtitles unchanged.')
            except Exception as exc:self.error(exc)

    def compare_models(self):
        if not self.p or not self.idle():return
        if not self.p['cues']:self.error('Process the video first. The comparison translates the recognised lines of this project.');return
        from .compare_dialog import CompareDialog
        self.save();dialog=CompareDialog(self.path,self._model_names or [self.model.currentText()],self.model.currentText(),self)
        motion.fade_window(dialog);dialog.exec()
    def edit_glossary(self):
        if not self.p or not self.idle():return
        dialog=QDialog(self);dialog.setWindowTitle('Names and terminology');dialog.resize(580,360);layout=QVBoxLayout(dialog)
        label=QLabel('One source name = preferred translation per line. These choices override learned terminology for future translation batches. Reviewed subtitles remain unchanged.');label.setWordWrap(True);layout.addWidget(label)
        editor=QPlainTextEdit();terms=dict(self.p.get('translation_memory',{}).get('terms',{}));terms.update(self.p.get('glossary',{}));editor.setPlainText('\n'.join(k+' = '+v for k,v in terms.items()));layout.addWidget(editor)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons)
        def accept():
            terms={}
            for line in editor.toPlainText().splitlines():
                if not line.strip():continue
                source,sep,target=line.partition('=')
                if not sep or not source.strip() or not target.strip():self.error('Each line needs a source name = translation.');return
                terms[source.strip()]=target.strip()
            self.p['glossary']=terms;self.save_live_edits();dialog.accept()
        buttons.accepted.connect(accept);buttons.rejected.connect(dialog.reject);motion.fade_window(dialog);dialog.exec()
    def idle(self):
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:self.error('Wait for processing or cancel it first.');return False
        return True
    def select_video(self,appearance='add'):
        if not self.idle():return
        path,_=QFileDialog.getOpenFileName(self,'Select video',str(Path.home()/'Videos'),'Videos (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All files (*)')
        if path:self.open_video(path,appearance)
    def open_video(self,path,appearance='add'):
        if not self.idle():return
        try:
            media=probe(path);p=new_project(path,media);p['appearance']=appearance;self.p=p
            import time
            folder=ROOT/'projects'/(Path(path).stem[:70]+'-'+time.strftime('%Y%m%d-%H%M%S'));folder.mkdir(parents=True,exist_ok=True)
            self.path=folder/'project.json';self.load_ui();self.save();self.show_workspace();self.process.pulse()
        except Exception as exc:self.error(exc)
    def open_project(self):
        if not self.idle():return
        path,_=QFileDialog.getOpenFileName(self,'Open editable project',str(ROOT/'projects'),'Project (*.json)')
        if path:self.load_path(path)
    def load_path(self,path):
        try:
            p=load_project(path)
            if not Path(p['video']).is_file():raise ValueError('Original video is missing. Restore it to '+p['video'])
            self.p=p;self.path=Path(path);self.load_ui();self.show_workspace()
        except Exception as exc:self.error(exc)
    def load_ui(self):
        self._loading=True
        p=self.p;names={v:k for k,v in LANGUAGES.items()};self.file_label.setText(Path(p['video']).name)
        self.mode.setCurrentIndex(0 if p['mode']=='speech' else 1);self.source.setCurrentText(names.get(p['source'],'Auto'));self.target.setCurrentText(names.get(p['target'],'Arabic'));self.script.setCurrentText(names.get(p['ocr_script'],'English'))
        self.begin.setValue(p['range_start']);self.end.setValue(p['range_end']);self.interval.setValue(p['sample_interval']);self.model.setCurrentText(p['model'])
        full=p['range_start']==0 and abs(p['range_end']-p['media']['duration'])<.01
        self.full_video.setChecked(full);self.begin.setEnabled(not full);self.end.setEnabled(not full)
        self.file_label.setText(f'{Path(p["video"]).name} · Full video: {clock_time(p["media"]["duration"])}')
        self.asr.setCurrentText(p.get('asr_model','turbo'));self.device.setCurrentIndex({'auto':0,'cuda':1,'cpu':2}.get(p.get('device','auto'),0))
        self.audio_track.clear()
        for i,s in enumerate(s for s in p['media'].get('streams',[]) if s.get('codec_type')=='audio'):
            self.audio_track.addItem(f'{i+1} · {s.get("tags",{}).get("language","und")} · {s.get("codec_name","audio")}',i)
        self.audio_track.setCurrentIndex(self.audio_track.findData(p.get('audio_track',0)))
        self.appearance.setCurrentIndex(APPEARANCE_KEYS.index(p['appearance']));self.kind.setCurrentIndex(0 if p['original_kind']=='burned' else 1)
        self.track.setValue(p.get('subtitle_track',0))
        s=p['style'];self.font.setCurrentFont(QFont(s['font']));self.size.setValue(s['size']);self.bold.setChecked(s['bold']);self.color.setText(s['color']);self.y.setValue(s['y']);self.padding.setValue(s['padding'])
        self.minimum_size.setValue(s.get('minimum_size',1))
        self.x.setValue(s.get('x',.5))
        self.line_height.setValue(s.get('line_height',1.45));self.line_height.setEnabled(s.get('arabic_typography',False))
        from .project import recognition_key
        p.setdefault('ui_baseline',{'recognition':recognition_key(p),'translation':[p['model'],p['target']]})
        self.live_text.setLayoutDirection(Qt.LayoutDirection.RightToLeft if p['target'] in ('ar','fa','ur') else Qt.LayoutDirection.LeftToRight)
        self._loading=False;self.update_setup_mode();self.update_model_status();self.video.set_project(p);self.original_video();self.refresh()
        self.live_view(start=max(0,p['cues'][0]['start']+.1) if p['cues'] else 0)
        if p['cues']:self.table.selectRow(0)
        preview=p.get('preview') or {}
        if preview:
            self.preview_start.setValue(preview['start']);self.preview_length.setValue(preview['duration'])
        elif p['cues']:self.preview_start.setValue(max(0,p['cues'][0]['start']-.5))
        self.tabs.setCurrentIndex(1 if p['cues'] else 0)
    def collect(self):
        if not self.p:raise ValueError('Select a video or open a project first.')
        if self.end.value()<=self.begin.value() or self.end.value()>self.p['media']['duration']+.05:raise ValueError('Processing range must be inside the video, with end after start.')
        if not QColor(self.color.text()).isValid():raise ValueError('Choose a valid text color, for example #ffffff.')
        self.p.update(mode='speech' if self.mode.currentIndex()==0 else 'ocr',source=LANGUAGES[self.source.currentText()],target=LANGUAGES[self.target.currentText()],ocr_script=LANGUAGES[self.script.currentText()],range_start=self.begin.value(),range_end=min(self.end.value(),self.p['media']['duration']),sample_interval=self.interval.value(),model=self.model.currentText().strip(),appearance=APPEARANCE_KEYS[self.appearance.currentIndex()],original_kind='burned' if self.kind.currentIndex()==0 else 'track')
        self.p['asr_model']=self.asr.currentText()
        self.p['process_full_video']=self.full_video.isChecked()
        if self.full_video.isChecked():self.p['range_start']=0.;self.p['range_end']=self.p['media']['duration']
        if self.audio_track.currentData():self.p['audio_track']=self.audio_track.currentData()
        else:self.p.pop('audio_track',None)
        self.p['device']=['auto','cuda','cpu'][self.device.currentIndex()]
        self.p['subtitle_track']=self.track.value()
        self.p['style'].update(font=self.font.currentFont().family(),size=self.size.value(),bold=self.bold.isChecked(),color=QColor(self.color.text()).name(),x=self.x.value(),y=self.y.value(),padding=self.padding.value(),minimum_size=self.minimum_size.value())
        if self.p['style'].get('arabic_typography'):self.p['style']['line_height']=self.line_height.value()
        validate(self.p)
    def save_from_button(self):
        self.save()
        if self.status.text().startswith('Project saved'):self.toast('Project saved')
    def save(self):
        if not self.idle():return
        try:self.collect();save_project(self.p,self.path);self.status.setText('Project saved: '+str(self.path));self.refresh_approval()
        except Exception as exc:self.error(exc)
    def refresh(self):
        selected=self.table.currentRow()
        self.table.blockSignals(True);self.table.setRowCount(len(self.p['cues']))
        for r,c in enumerate(self.p['cues']):
            values=[f'{c["start"]:.3f}',f'{c["end"]:.3f}',c['original'],c['translation'],'Reviewed' if c.get('reviewed') else 'Check']
            for col,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip('\n'.join(c.get('flags',[])))
                if col==4:item.setForeground(QColor('#6cdec1' if c.get('reviewed') else '#ffd17b'))
                self.table.setItem(r,col,item)
        self.table.resizeRowsToContents();self.table.blockSignals(False)
        count=sum(not c.get('reviewed') for c in self.p['cues']);self.summary.setText(f'{len(self.p["cues"])} cues • {count} need review. Recognition confidence and translation flags are estimates, not guarantees.');self.refresh_approval()
        self.video.set_project(self.p)
        if selected>=0 and selected<len(self.p['cues']):
            self.table.blockSignals(True);self.table.selectRow(selected);self.table.blockSignals(False)
        self.populate_live_editor()
        self.filter_rows()
    def refresh_approval(self):
        if not self.p:
            for control in (self.generate_button,self.approve_button,self.continue_export,self.export_button):control.setEnabled(False)
            return
        recognition,translation=self.pending_work();pending=recognition or translation
        self.range_summary.setText(('Entire video' if self.full_video.isChecked() else 'Custom range')+f': {clock_time(self.p["range_start"])} – {clock_time(self.p["range_end"])} / full video {clock_time(self.p["media"]["duration"])}')
        youtube=self.p['appearance']=='youtube'
        # YouTube captions are a text file: no rendered video to approve, so the preview is optional.
        ok=(bool(self.p['cues']) and not pending) if youtube else approved(self.p) and not pending
        self.generate_button.setEnabled(bool(self.p['cues']) and not pending)
        self.approve_button.setEnabled(self.preview_current() and not pending)
        self.continue_export.setEnabled(ok);self.export_button.setEnabled(ok)
        self.process.setText('Recognise again…' if recognition else 'Process / Resume' if not self.p['checkpoints'].get('recognized') else 'Translate again')
        self.run_hint.setText('Recognition settings changed. Re-recognition replaces all cues, including reviewed lines.' if recognition else 'Translation settings changed. Translate again to update unreviewed lines.' if translation else 'Translate again retains recognised text and reviewed translations. Processing checkpoints support Resume.')
        self.approval_label.setText('Current preview approved. Ready to export.' if ok else 'Return to Setup to process changed settings.' if pending else 'Generate and watch the current preview, then approve it. Any text/style edit requires a new preview.')
        if youtube:
            self.approval_label.setText('Return to Setup to process changed settings.' if pending else 'Optional for YouTube captions. The rendered preview uses this app\'s text style; YouTube shows captions in its own style.')
        self.export_approval.setText('Return to Setup to process changed settings.' if youtube and pending else 'Ready to save the captions file.' if youtube and ok else self.approval_label.text())
        self.youtube_help.setVisible(youtube);self.open_video_button.setVisible(not youtube)  # captions mode makes no video
        if youtube:self.youtube_help.setText(self.youtube_steps())
        from .export_paths import next_export
        self.output_label.setText('Next export folder:\n'+str(next_export(ROOT/'exports',self.p).parent))
        only=self.p['appearance']=='file'
        self.output_files.setText('SRT captions file for YouTube · Editable project' if youtube else 'SRT · ASS · Editable project' if only else 'MKV video · SRT · ASS · Editable project')
        self.export_button.setText('Save YouTube captions' if youtube else 'Export subtitle files' if only else 'Export translated video')
        self.roi_label.setText('Selected area (x, y, width, height): '+', '.join(f'{v:.0%}' for v in self.p['roi']))
        self.dialogue_status.setText('Dialogue layout filter active. Menus and other layouts are excluded.' if self.p.get('dialogue_profile') else 'To exclude menus: select a dialogue cue in Review, then keep its layout.')
        preview=self.p.get('preview') or {}
        if self.showing_path(preview.get('path')) and not self.preview_current():
            self.view_label.setText('Older translated preview — edits are not rendered yet. Generate a new preview.')
    def youtube_steps(self):
        language=next((name for name,code in LANGUAGES.items() if code==self.p['target']),'the translation language')
        notes=['<b>Upload to YouTube</b>',
               '1. Open YouTube Studio and go to <i>Subtitles</i>.',
               '2. Choose your video, then <i>Add language</i> and pick '+language+'.',
               '3. Under subtitles choose <i>Add</i> › <i>Upload file</i> › <i>With timing</i>, and select the .srt file.',
               '4. Publish. Viewers switch it on or off with the CC button and pick it under Settings › Subtitles.',
               '<br>Lines stay on screen long enough to read, as in Review. Text style settings do not apply: YouTube uses its own caption style.']
        if self.p['mode']=='ocr' and self.p['original_kind']=='burned':
            notes.append('<br><b>Note:</b> this video has subtitles burned into the picture. They stay visible; YouTube captions appear on top of them.')
        return '<br>'.join(notes)
    def toggle_play(self):
        self.preview_freeze_position=None
        self.player.pause() if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState else self.player.play()
    def position(self,ms):
        if not self.seek.isSliderDown():self.seek.setValue(ms)
        self.time_label.setText(f'{clock_time(ms/1000)} / {clock_time(self.player.duration()/1000)}')
    def original_video(self):
        if self.p:
            self.video.live=False;self.video.update()
            self.preview_freeze_position=None
            self.pending_position=None
            self.player.setSource(QUrl.fromLocalFile(self.p['video']))
            self.configure_subtitle_track()
            self.view_label.setText('Original video — translated text and covers are shown in Translated preview.')
    def live_view(self,checked=False,start=None):
        if not self.p:return
        position=self.source_position() if start is None else start
        if start is None and self.video.frame.isNull() and self.pending_position is not None:
            position=self.pending_position/1000
        self.video.live=True;self.video.set_project(self.p)
        self.view_label.setText('Live edits — instant text and covers. Rendered preview checks final export layout.')
        if not self.showing_path(self.p['video']) or self.video.frame.isNull() or start is not None:
            was_playing=self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState
            self.pending_position=round(max(0,position)*1000)
            self.preview_freeze_position=None if was_playing else self.pending_position
            self.player.setSource(QUrl.fromLocalFile(self.p['video']));self.player.play()
        self.configure_subtitle_track()
    def configure_subtitle_track(self):
        if not self.p:return
        enabled=self.showing_path(self.p['video']) and self.p['original_kind']=='track' and (not self.video.live or self.p['appearance']!='replace')
        self.video.show_native=enabled
        index=int(self.p.get('subtitle_track',0)) if enabled else -1
        if index>=len(self.player.subtitleTracks()):index=-1
        if self.player.activeSubtitleTrack()!=index:self.player.setActiveSubtitleTrack(index)
        self.video.update()
    def populate_live_editor(self):
        r=self.selected();self.video.selected=r if r is not None else -1
        self.live_panel.setEnabled(r is not None and not (self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning))
        if r is None:return
        c=self.p['cues'][r];self._editing_fields=True
        self.live_text.setPlainText(c['translation']);self.live_start.setValue(c['start']);self.live_end.setValue(c['end']);self.live_boxes.setPlainText(json.dumps(c.get('boxes',[])))
        self._editing_fields=False;self.video.update()
    def edit_changed(self):
        self.live_view();self.video.update();self.refresh_approval();self.autosave.start()
        r=self.selected()
        if r is not None:
            c=self.p['cues'][r];self.table.blockSignals(True)
            for column,text in ((0,f'{c["start"]:.3f}'),(1,f'{c["end"]:.3f}'),(3,c['translation']),(4,'Check')):
                self.table.item(r,column).setText(text)
            self.table.blockSignals(False);self.table.resizeRowToContents(r)
    def save_live_edits(self):
        if not self.p or not self.path or (self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning):return
        try:
            validate(self.p);save_project(self.p,self.path);self.status.setText('Live edits saved. Render a preview when ready to approve export.')
            if self.selected() is not None:self.row_flash.flash([self.selected()],900,.45)
        except Exception as exc:self.status.setText('Live edit not saved: '+str(exc))
    def live_text_changed(self):
        if self._editing_fields:return
        r=self.selected()
        if r is None:return
        self.checkpoint(('text',r));self.p['cues'][r]['translation']=self.live_text.toPlainText();self.p['cues'][r]['reviewed']=False;self.edit_changed()
        warnings=arabic_warnings(self.live_text.toPlainText())
        if warnings:self.live_hint.setText('Arabic check: '+'; '.join(warnings))
    def live_timing_changed(self):
        if self._editing_fields:return
        r=self.selected()
        if r is None:return
        start,end=self.live_start.value(),self.live_end.value()
        if not 0<=start<end<=self.p['media']['duration']:
            self.live_hint.setText('Timing needs 0 ≤ start < end ≤ video duration.');return
        self.checkpoint(('time',r));c=self.p['cues'][r]
        if c.get('cover_spans'):
            spans=[dict(span,start=max(start,span['start']),end=min(end,span['end'])) for span in c['cover_spans'] if max(start,span['start'])<min(end,span['end'])]
            c['cover_spans']=spans
            if not spans:c['boxes']=[]
            if start<c['start'] or end>c['end']:c.setdefault('flags',[]).append('Timing extended beyond detected covers; review or redetect covers')
        c.update(start=start,end=end,reviewed=False)
        self.live_hint.setText('Timing updated live. Detected cover spans retain their source timestamps.');self.edit_changed()
    def live_boxes_input(self):
        if self._editing_fields:return
        try:
            boxes=json.loads(self.live_boxes.toPlainText());r=self.selected()
            if r is None:return
            draft=copy.deepcopy(self.p);draft['cues'][r]['boxes']=boxes;validate(draft)
            if not isinstance(boxes,list):raise ValueError('Use a list of rectangles.')
        except Exception:
            self.live_hint.setText('Enter valid rectangles inside the frame: [[x, y, width, height], ...]');return
        self.live_boxes_changed(boxes,sync_fields=False)
    def live_boxes_changed(self,boxes,sync_fields=True):
        r=self.selected()
        if r is None:return
        self.checkpoint(('boxes',r));c=self.p['cues'][r];c['boxes']=copy.deepcopy(boxes);c.pop('cover_spans',None);c['reviewed']=False
        if sync_fields:
            self._editing_fields=True;self.live_boxes.setPlainText(json.dumps(boxes));self._editing_fields=False
        self.live_hint.setText('Manual covers apply throughout this cue. Drag inside to move, or the corner to resize.');self.edit_changed()
    def toggle_cover_edit(self,enabled):
        self.video.edit_covers=enabled
        if enabled:
            self.drag_caption.setChecked(False)
            self.live_view();self.player.pause();r=self.selected()
            if r is not None and not self.p['cues'][r]['start']<=self.source_position()<self.p['cues'][r]['end']:
                self.player.setPosition(round((self.p['cues'][r]['start']+.05)*1000))
        self.video.update()
    def live_style_changed(self,*args):
        if self._loading or not self.p or not QColor(self.color.text()).isValid():return
        self.p['appearance']=APPEARANCE_KEYS[self.appearance.currentIndex()];self.p['original_kind']='burned' if self.kind.currentIndex()==0 else 'track'
        self.p['style'].update(font=self.font.currentFont().family(),size=self.size.value(),bold=self.bold.isChecked(),color=QColor(self.color.text()).name(),x=self.x.value(),y=self.y.value(),padding=self.padding.value(),minimum_size=self.minimum_size.value())
        if self.p['style'].get('arabic_typography'):self.p['style']['line_height']=self.line_height.value()
        self.edit_changed()

    def toggle_caption_drag(self,enabled):
        self.video.drag_subtitles=enabled
        if enabled and self.p:
            self.draw_covers.setChecked(False);self.live_view()

    def begin_caption_drag(self,index):
        self._undo_tag=None;self.player.pause();self.table.blockSignals(True);self.table.selectRow(index);self.table.blockSignals(False);self.populate_live_editor()

    def move_caption(self,x,y,index):
        if not self.p:return
        owner=self.p['cues'][index] if index>=0 else self.p['style']
        # A click without movement is not an edit: keep approval and reviewed state.
        if all(abs(a-b)<1e-9 for a,b in zip(owner.get('caption_offset',[0,0]),(x,y))):return
        if index>=0:self.checkpoint(('move',index))
        owner['caption_offset']=[x,y]
        if index>=0:
            owner['reviewed']=False
            item=self.table.item(index,4)
            if item:item.setText('Check');item.setForeground(QColor('#ffd17b'))
        self.video.update();self.refresh_approval();self.autosave.start()

    def reset_caption_position(self):
        if not self.p or not self.idle():return
        self.checkpoint()
        if self.drag_scope.currentIndex()==0:
            self.p['style'].pop('caption_offset',None)
            for c in self.p['cues']:c.pop('caption_offset',None)
        else:
            index=self.selected()
            if index is None:return
            self.p['cues'][index].pop('caption_offset',None)
        self.edit_changed()

    def resize_caption(self,scale,index):
        if not self.p:return
        owner=self.p['cues'][index] if index>=0 else self.p['style']
        if abs(owner.get('caption_scale',1)-scale)<1e-9:return
        if index>=0:self.checkpoint(('size',index))
        owner['caption_scale']=scale
        if index>=0:
            owner['reviewed']=False
            item=self.table.item(index,4)
            if item:item.setText('Check');item.setForeground(QColor('#ffd17b'))
        self.video.update();self.refresh_approval();self.autosave.start()

    def reset_caption_size(self):
        if not self.p or not self.idle():return
        self.checkpoint()
        if self.drag_scope.currentIndex()==0:
            self.p['style'].pop('caption_scale',None)
            for c in self.p['cues']:c.pop('caption_scale',None)
        else:
            index=self.selected()
            if index is None:return
            self.p['cues'][index].pop('caption_scale',None)
        self.edit_changed()
    def apply_arabic_style(self):
        if not self.p or not self.idle():return
        self.p['style']=khaam_style(self.p['style']);self._loading=True
        self.font.setCurrentFont(QFont('Almarai'));self.size.setValue(48);self.bold.setChecked(True);self.color.setText('#ffffff');self.line_height.setValue(1.45);self.line_height.setEnabled(True)
        self._loading=False;self.edit_changed()
    def preview_current(self):
        preview=(self.p or {}).get('preview') or {}
        return bool(self.p and preview.get('fingerprint')==fingerprint(self.p) and Path(preview.get('path','')).is_file())
    def showing_path(self,path):
        current=self.player.source().toLocalFile()
        return bool(path and current and Path(current).resolve()==Path(path).resolve())
    def source_position(self):
        preview=(self.p or {}).get('preview') or {}
        offset=preview.get('start',0) if self.showing_path(preview.get('path')) else 0
        return self.player.position()/1000+offset
    def media_loaded(self,status):
        if status==QMediaPlayer.MediaStatus.LoadedMedia and self.pending_position is not None:
            self.player.setPosition(self.pending_position);self.pending_position=None
    def preview_frame_ready(self,frame):
        if self.preview_freeze_position is not None and frame.isValid() and frame.startTime()/1000>=self.preview_freeze_position:
            self.preview_freeze_position=None;self.player.pause()
    def show_preview(self,play=True):
        self.video.live=False;self.video.show_native=False;self.video.update()
        preview=self.p['preview']
        first=next((c for c in self.p['cues'] if c['end']>preview['start'] and c['start']<preview['start']+preview['duration']),None)
        position=max(0,max(preview['start'],first['start'])-preview['start']+.2) if first else 0
        self.pending_position=round(position*1000)
        self.preview_freeze_position=self.pending_position if not play else None
        self.player.setSource(QUrl.fromLocalFile(preview['path']))
        self.view_label.setText('Translated preview — rendered subtitles and covers. Generate again after edits.')
        self.player.play()
    def selected(self):
        r=self.table.currentRow()
        return r if self.p and 0<=r<len(self.p['cues']) else None
    def seek_cue(self):
        r=self.selected()
        if r is not None:
            t=self.p['cues'][r]['start'];preview=self.p.get('preview') or {}
            if self.showing_path(preview.get('path')) and self.preview_current() and preview['start']<=t<preview['start']+preview['duration']:
                self.player.setPosition(round((t-preview['start'])*1000))
            else:
                if not self.showing_path(self.p['video']):self.original_video()
                self.player.setPosition(round(t*1000))
            self.preview_start.setValue(max(0,t-.5));self._undo_tag=None  # edits to another line are a new undo step
            self.populate_live_editor()
    def edit_cue(self):
        if not self.idle():return
        r=self.selected()
        if r is None:return
        self.live_view();self.player.pause();dialog=CueDialog(self.p['cues'][r],self.p['media']['duration'],self)
        def draft_changed(c):
            draft=copy.deepcopy(self.p);draft['cues'][r]=c;self.video.set_project(draft)
        dialog.draftChanged.connect(draft_changed)
        motion.fade_window(dialog)
        if dialog.exec():self.checkpoint();self.p['cues'][r]=dialog.c;self.save();self.refresh();self.row_flash.flash([r],900,.45)
        self.video.set_project(self.p);self.populate_live_editor()
    def edit_covers(self):
        if not self.idle():return
        r=self.selected()
        if r is None:return
        try:
            c=self.p['cues'][r];t=min(c['end']-.01,c['start']+.15)
            self.live_view();self.player.pause();self.player.setPosition(round(t*1000))
            dialog=RectangleDialog(self.p['video'],t,c.get('boxes',[]),parent=self)
            def draft_boxes(boxes):
                draft=copy.deepcopy(self.p);draft['cues'][r]['boxes']=boxes;draft['cues'][r].pop('cover_spans',None);self.video.set_project(draft)
            dialog.boxesChanged.connect(draft_boxes)
            motion.fade_window(dialog)
            if dialog.exec():
                self.checkpoint();c['boxes']=dialog.canvas.boxes;c.pop('cover_spans',None);c['reviewed']=False;self.save();self.refresh()
            self.video.set_project(self.p);self.populate_live_editor()
        except Exception as exc:self.error(exc)
    def select_roi(self):
        if not self.idle() or not self.p:return
        try:
            w,h=self.p['media']['width'],self.p['media']['height'];x,y,rw,rh=self.p['roi']
            dialog=RectangleDialog(self.p['video'],self.source_position(),[[x*w,y*h,rw*w,rh*h]],True,self)
            motion.fade_window(dialog)
            if dialog.exec():
                x,y,rw,rh=dialog.canvas.boxes[0];self.p['roi']=[x/w,y/h,rw/w,rh/h]
                self.p['ocr_samples']=[];self.p['checkpoints'].pop('ocr_cursor',None);self.p['checkpoints'].pop('ocr_complete',None);self.save()
        except Exception as exc:self.error(exc)
    def add_cue(self):
        if not self.idle() or not self.p:return
        self.checkpoint();start=min(self.source_position(),self.p['media']['duration']-.1);self.p['cues'].append(cue(start,min(start+2,self.p['media']['duration']),'','',0))
        self.p['cues'][-1]['boxes']=[];self.refresh();self.table.selectRow(len(self.p['cues'])-1);self.edit_cue()
    def delete_cue(self):
        if not self.idle():return
        r=self.selected()
        if r is not None:self.checkpoint();self.p['cues'].pop(r);self.save();self.refresh()
    def mark_reviewed(self):
        if not self.idle():return
        if self.p:self.checkpoint()
        for index in self.table.selectionModel().selectedRows():self.p['cues'][index.row()]['reviewed']=True
        if self.p:self.save();self.refresh()
    def run(self,action):
        if not self.idle():return
        try:
            self.collect()
            # YouTube captions are a text file with nothing rendered to approve (engine.render skips the check too).
            if action=='export' and self.p['appearance']!='youtube' and not approved(self.p):raise ValueError('Watch and approve a preview of the current edit before exporting.')
            if action in ('translate','preview','export') and self.pending_work()[0]:raise ValueError('Recognition settings changed. Return to Setup and choose Recognise again first.')
            if action in ('preview','export') and self.pending_work()[1]:raise ValueError('Translation settings changed. Return to Setup and choose Translate again first.')
            if action in ('preview','export'):validate(self.p,render=True)
            if action=='process' and self.p['cues']:
                from .project import recognition_key
                if self.p['checkpoints'].get('recognition_key')!=recognition_key(self.p):
                    if QMessageBox.question(self,'Reprocess','Source settings changed. This replaces all subtitles, including reviewed lines and hand corrections. A backup will be saved first. Continue?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
                    import time
                    save_project(self.p,self.path.with_name('before-reprocess-'+str(time.time_ns())+'.json'))
            if action=='translate':
                for c in self.p['cues']:
                    if not c.get('reviewed'):c.pop('translation_key',None)
                self.p['approval']=None
            save_project(self.p,self.path);cancel_path=self.path.with_suffix('.cancel');cancel_path.unlink(missing_ok=True)
            self.player.pause();self.buffer='';self.proc=QProcess(self);self.proc.setWorkingDirectory(str(ROOT));self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            self.proc.readyReadStandardOutput.connect(self.read_output);self.proc.finished.connect(self.finished)
            args=['-m','videotranslator.engine',action,str(self.path)]
            if action=='preview':args+=['--start',str(self.preview_start.value()),'--length',str(self.preview_length.value())]
            self.job_action=action
            import time
            self.job_started=time.monotonic();self.elapsed.start();self.proc.errorOccurred.connect(self.worker_error)
            self.proc.start(str(ROOT/'.venv'/'Scripts'/'python.exe'),args);self.cancel.setEnabled(True);self.begin_steps('captions' if action=='export' and self.p['appearance']=='youtube' else action);self.status.setText('Starting '+action+'…')
            # Editing settings while a worker owns the project is disabled.
            self.autosave.stop();self.tabs.setEnabled(False);self.style_panel.setEnabled(False);self.table.setEnabled(False);self.live_panel.setEnabled(False);self.video.setEnabled(False)
        except Exception as exc:self.error(exc)
    def read_output(self):
        self.buffer+=bytes(self.proc.readAllStandardOutput()).decode('utf-8',errors='replace')
        while '\n' in self.buffer:
            line,self.buffer=self.buffer.split('\n',1)
            try:
                obj=json.loads(line);self.job_progress(round(obj['progress']),obj['message']);self.status.setText(obj['message'])
            except (ValueError,KeyError):pass
            self.log.appendPlainText(line)
    def setup_ollama(self):
        """Installs Ollama, starts it and downloads the chosen model, in a console window so the long download shows its progress."""
        import re,subprocess
        model=self.model.currentText().strip() or 'gemma4:12b'
        if not re.fullmatch(r'[\w.:/-]+',model):self.status.setText('That model name is not valid. Pick or type a name such as gemma4:12b.');return
        subprocess.Popen(['cmd','/c','powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'install.ps1'),'-OllamaOnly','-Model',model,'&','pause'],creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.status.setText('Setting up translation in a separate window. When it says it is ready, press Refresh.')
    def refresh_models(self,quiet=False):
        current=self.model.currentText().strip()
        try:names=installed_models()
        except Exception as e:
            self._model_names=None;self.update_model_status()
            if not quiet:self.status.setText(f'Could not list Ollama models ({type(e).__name__}). Is Ollama running? You can still type a model name.')
            return
        self._model_names=names;self.model.blockSignals(True);self.model.clear();self.model.addItems(names);self.model.setCurrentText(current or (names[0] if names else ''));self.model.blockSignals(False);self.update_model_status()
        if not quiet:self.status.setText(f'{len(names)} local Ollama models found.' if names else 'Ollama has no local models installed.')

    def setup_ocr(self):
        if not self.idle():return
        code=LANGUAGES[self.script.currentText()]
        if QMessageBox.question(self,'Download OCR model','Download selected OCR weights from the official EasyOCR GitHub releases? Approximately 15–250 MB per alphabet. No video is sent. English and Arabic are already installed.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        if self.p:self.collect();save_project(self.p,self.path)
        self.autosave.stop();self.live_panel.setEnabled(False);self.video.setEnabled(False)
        self.job_action='setup';self.buffer='';self.proc=QProcess(self);self.proc.setWorkingDirectory(str(ROOT));self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.read_output);self.proc.finished.connect(self.finished)
        self.proc.start(str(ROOT/'.venv'/'Scripts'/'python.exe'),[str(ROOT/'setup_models.py'),'--ocr',code]);self.tabs.setEnabled(False);self.style_panel.setEnabled(False);self.table.setEnabled(False);self.begin_steps('ocr-model');self.status.setText('Downloading OCR model; details in log.');self.cancel.setEnabled(True)
    def begin_steps(self,key):
        self.step_key=key;self.step_names=job_steps.steps(key,self.p['mode'] if self.p else 'ocr');self.step_index=0
        self.job_running=True;self.progress_target=0;self.progress.setRange(0,0)  # busy bar until the worker reports real progress; model loading reports none
        self.show_steps()
    def show_steps(self,failed=False):
        names=self.step_names;work=len(names)-1  # the last step is the result, not work
        step=min(self.step_index,work-1);busy=self.progress.maximum()==0
        percent='' if busy else f' · {self.progress_target}%'
        if self.step_index>=work and not failed:detail='Done'
        elif failed:detail='Stopped'
        else:detail=(f'Step {step+1} of {work} · ' if work>1 else '')+names[step]+percent
        self.steps.set(names,self.step_index,failed,detail,running=self.job_running)
    def job_progress(self,value,message):
        self.step_index=max(self.step_index,job_steps.current(self.step_key,value,message))  # steps never go back
        if value>0 and self.progress.maximum()==0:self.progress.setRange(0,100)
        if self.progress.maximum():self.progress_target=value;motion.progress_to(self.progress,value)
        self.show_steps()
    def end_steps(self,code):
        self.job_running=False;self.progress.setRange(0,100)
        if code==0:self.step_index=len(self.step_names);self.progress_target=100;motion.progress_to(self.progress,100)
        self.show_steps(failed=code!=0)
        QApplication.alert(self,0)  # flashes the taskbar button only when the window is in the background
    def finished(self,code,status):
        self.elapsed.stop();before=[c.get('translation') for c in self.p['cues']] if self.p else []
        if getattr(self,'step_names',None):self.end_steps(code)
        self.read_output();self.cancel.setEnabled(False);self.tabs.setEnabled(True);self.style_panel.setEnabled(True);self.table.setEnabled(True);self.video.setEnabled(True)
        if self.path and self.path.is_file():
            self.p=load_project(self.path)
            if code==0 and getattr(self,'job_action',None) in ('process','translate'):
                from .project import recognition_key
                self.p['ui_baseline']={'recognition':recognition_key(self.p),'translation':[self.p['model'],self.p['target']]};save_project(self.p,self.path)
            self.refresh()
        action=getattr(self,'job_action',None)
        if code==0 and action in ('process','translate'):
            self.tabs.setCurrentIndex(1)
            # New translations fade in with a teal highlight (table rows are cue indices).
            changed=[i for i,c in enumerate(self.p['cues']) if i>=len(before) or c.get('translation')!=before[i]]
            self.row_flash.flash(changed,1400,.32,stagger=min(30,600/max(1,len(changed))));self.toast('Translation ready for review')
        if code==0 and action=='preview' and self.preview_current():self.show_preview(play=False);self.approve_button.pulse();self.toast('Preview ready to watch')
        if code==0 and action=='export':
            self.status.setText('Export complete: '+self.p.get('last_export',''))
            if self.p['appearance']=='youtube':self.toast('YouTube captions saved','Show file',self.open_outputs)
            else:self.toast('Export complete','Open video',self.open_export_video)
        if code==0:motion.flash(self.status,'#B0BDCE')
        if code not in (0,2):
            # The worker's last line is "Error: <reason>"; show the reason itself, not only where to look for it.
            reason=self.status.text()[7:] if self.status.text().startswith('Error: ') else 'See the log for the error.'
            self.error(f'Processing stopped. {reason}\n\nSaved checkpoints are available for Resume.')
    def cancel_job(self):
        if self.path:self.path.with_suffix('.cancel').touch();self.status.setText('Cancellation requested; waiting for the current model step. Checkpoints are safe.');self.cancel.setEnabled(False)
        # Some native inference calls cannot be interrupted cooperatively.
        proc=self.proc
        def terminate_tree():
            if proc and proc.state()!=QProcess.ProcessState.NotRunning:
                import subprocess
                subprocess.run(['taskkill','/PID',str(proc.processId()),'/T','/F'],capture_output=True,creationflags=0x08000000)
        QTimer.singleShot(5000,terminate_tree)
    def play_preview(self):
        try:
            self.collect();preview=self.p.get('preview') or {}
            if any(self.pending_work()):raise ValueError('Process changed settings in Setup before approving a preview.')
            if preview.get('fingerprint')!=fingerprint(self.p):raise ValueError('Preview is missing or out of date. Generate a new preview.')
            self.show_preview()
        except Exception as exc:self.error(exc)
    def approve(self):
        if not self.idle():return
        try:
            self.collect();preview=self.p.get('preview') or {}
            if any(self.pending_work()):raise ValueError('Process changed settings in Setup before approving a preview.')
            if preview.get('fingerprint')!=fingerprint(self.p) or not Path(preview.get('path','')).is_file():raise ValueError('Generate a current preview first.')
            if QMessageBox.question(self,'Approve preview','Have you watched this preview and approved its translation, timing, Arabic rendering, and cover placement?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
                self.p['approval']=fingerprint(self.p);self.save();motion.flash(self.approval_label,'#EDF2FA')
                self.continue_export.pulse();self.export_button.pulse();self.toast('Preview approved')
        except Exception as exc:self.error(exc)
    def open_outputs(self):
        if self.path:
            latest=self.p.get('last_export') if self.p else None
            folder=Path(latest).parent if latest and Path(latest).is_file() else ROOT/'exports'
            folder.mkdir(parents=True,exist_ok=True);os.startfile(str(folder))
    def look_for_update(self):
        """Asks GitHub in the background whether a newer version exists. Offline or unsure means silence."""
        import threading
        from .updates import check
        def run():
            info=check()
            if info:self.update_found.emit(info)
        threading.Thread(target=run,daemon=True).start()
    def show_update(self,info):
        self.update_info=info
        for b in self.update_buttons:b.show()
        self.install_update()
    def install_update(self):
        """The popup behind the Update button: Update now or Later. Later keeps the button."""
        info=self.update_info
        if not info:return
        box=QMessageBox(self);box.setWindowTitle('Update available');box.setText('A newer version of Video Translator is ready.')
        box.setInformativeText((f"What is new: {info['message']}\n\n" if info['message'] else '')+'Updating closes the app, installs the new version and opens it again. Your projects, exports and models are kept.')
        yes=box.addButton('Update now',QMessageBox.ButtonRole.AcceptRole);box.addButton('Later',QMessageBox.ButtonRole.RejectRole);box.exec()
        if box.clickedButton() is not yes or not self.idle():return
        if getattr(self,'phone',None) and self.phone.status()['state'] in ('receiving','working'):return self.error('A video from your phone is being translated. Update when it finishes.')
        import subprocess
        subprocess.Popen([str(ROOT/'.venv'/'Scripts'/'python.exe'),'-m','videotranslator.updates',info['sha']],cwd=ROOT,creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.close()
    def phone_mode(self):
        # The server starts on first use and stays on until the app closes, so the phone keeps working with this window hidden.
        try:
            if not getattr(self,'phone',None):
                from .phone_server import PhoneServer
                self.phone=PhoneServer().start()
            from .phone_dialog import PhoneDialog
            PhoneDialog(self.phone,self).exec()
        except OSError as exc:self.error(f'Phone mode could not start: {exc}')
    def closeEvent(self,event):
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
            self.cancel_job();self.status.setText('Cancelling. Close again after the worker stops.');event.ignore();return
        if self.p:
            try:self.collect();save_project(self.p,self.path)
            except Exception:pass
        if getattr(self,'phone',None):self.phone.stop();self.phone=None
        event.accept()

def create_application(argv):
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('LocalVideoTranslator.Desktop')
    app=QApplication(argv);app.setApplicationName('Local Video Translator')
    # The interface is English: show 0-9 digits in number boxes even on an Arabic Windows locale.
    QLocale.setDefault(QLocale(QLocale.Language.English,QLocale.Country.UnitedStates))
    app.setWindowIcon(QIcon(str(ROOT/'assets'/'video-translator.ico')))
    from .workspace_ui import STYLE
    app.setStyle('Fusion');app.setStyleSheet(STYLE)
    return app

def main():
    app=create_application(sys.argv);window=MainWindow();window.show();window.look_for_update()
    if len(sys.argv)>1:window.load_path(sys.argv[1])
    sys.exit(app.exec())

if __name__=='__main__':main()

