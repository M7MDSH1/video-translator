"""First screen: start a new project from a video (choose or drop it), or open an existing project."""
import json,re,time
from pathlib import Path
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QPixmap,QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QFrame,QRadioButton,QButtonGroup,QListWidget,
    QListWidgetItem,QSizePolicy)
from . import motion
from .project import ROOT

OUTPUTS=[('add','Translated video','Subtitles drawn on the video. You get a new video file.'),
         ('youtube','YouTube captions','A captions file you upload to YouTube. Viewers turn it on or off with the CC button.')]

def recent_projects(root=ROOT/'projects',limit=8):
    """Newest editable projects first. Only <folder>/project.json counts: export snapshots and backups are skipped.
    Reads just the start of each file, because full projects can be several MB."""
    found=[]
    for path in Path(root).glob('*/project.json'):
        try:
            with path.open(encoding='utf-8') as file:head=file.read(4096)
            video=re.search(r'"video":\s*("(?:[^"\\]|\\.)*")',head)
            mode=re.search(r'"mode":\s*"(\w+)"',head);appearance=re.search(r'"appearance":\s*"(\w+)"',head)
            found.append({'path':path,'video':Path(json.loads(video.group(1))).name if video else path.parent.name,
                          'mode':mode.group(1) if mode else '','appearance':appearance.group(1) if appearance else '',
                          'modified':path.stat().st_mtime})
        except (OSError,ValueError):continue
    return sorted(found,key=lambda r:r['modified'],reverse=True)[:limit]

class DropCard(QFrame):
    """The New project card. It lights up while a video is dragged over the window."""
    def __init__(self):
        super().__init__();self.setObjectName('dropCard');self._hot=0.;self._paint()
    def set_hot(self,hot):
        if not motion.enabled(self):motion.stop(self,'_hot');self._hot=1. if hot else 0.;self._paint();return
        motion._tween(self,'_hot',self._hot,1. if hot else 0.,180,motion.EASE_OUT,lambda v:(setattr(self,'_hot',v),self._paint()))
    def _paint(self):
        h=self._hot;a,b=QColor('#354153'),QColor('#57D6B5')
        border=QColor(round(a.red()+(b.red()-a.red())*h),round(a.green()+(b.green()-a.green())*h),round(a.blue()+(b.blue()-a.blue())*h))
        fill=QColor(round(29+(32-29)*h),round(38+(62-38)*h),round(50+(60-50)*h))
        self.setStyleSheet(f'#dropCard{{background:{fill.name()};border:2px dashed {border.name()};border-radius:12px;}} QRadioButton{{background:transparent;}}')

class StartScreen(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window
        from .app import button
        outer=QVBoxLayout(self);outer.setContentsMargins(40,36,40,28);outer.setSpacing(22)
        outer.addStretch(1)
        head=QWidget();hl=QHBoxLayout(head);hl.setContentsMargins(0,0,0,0);hl.setSpacing(16)
        logo=QLabel();logo.setPixmap(QPixmap(str(ROOT/'assets'/'video-translator.png')).scaled(64,64,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        hl.addStretch();hl.addWidget(logo);titles=QVBoxLayout();titles.setSpacing(2)
        title=QLabel('Video Translator');title.setProperty('role','title');titles.addWidget(title)
        tag=QLabel('Translate a video on this PC. Nothing is uploaded.');tag.setProperty('role','muted');titles.addWidget(tag)
        hl.addLayout(titles);hl.addStretch();outer.addWidget(head)

        cards=QWidget();cl=QHBoxLayout(cards);cl.setContentsMargins(0,0,0,0);cl.setSpacing(20)
        # New project: drop or choose a video, and pick what to make.
        self.drop=DropCard();dl=QVBoxLayout(self.drop);dl.setContentsMargins(28,24,28,24);dl.setSpacing(10)
        h=QLabel('New project');h.setStyleSheet('font-size:18px;font-weight:700;');dl.addWidget(h)
        hint=QLabel('Drop a video anywhere on this window, or choose one.');hint.setProperty('role','muted');hint.setWordWrap(True);dl.addWidget(hint)
        dl.addSpacing(6);ask=QLabel('What do you want to make?');ask.setStyleSheet('font-weight:600;');dl.addWidget(ask)
        self.output=QButtonGroup(self)
        for n,(key,name,text) in enumerate(OUTPUTS):
            radio=QRadioButton(name);radio.setStyleSheet('font-weight:600;');self.output.addButton(radio,n);dl.addWidget(radio)
            note=QLabel(text);note.setProperty('role','muted');note.setWordWrap(True);note.setContentsMargins(26,0,0,4);dl.addWidget(note)
        self.output.button(0).setChecked(True)
        dl.addStretch();self.choose=button('Choose video…',self.choose_video);self.choose.setProperty('primary',True);dl.addWidget(self.choose)
        cl.addWidget(self.drop,1)
        # Open project: recent list plus a file browser.
        recent=QFrame();recent.setObjectName('recentCard');recent.setStyleSheet('#recentCard{background:#1D2632;border:1px solid #354153;border-radius:12px;}')
        rl=QVBoxLayout(recent);rl.setContentsMargins(28,24,28,24);rl.setSpacing(10)
        h=QLabel('Open a project');h.setStyleSheet('font-size:18px;font-weight:700;');rl.addWidget(h)
        self.recent_hint=QLabel('Continue a translation you already started.');self.recent_hint.setProperty('role','muted');self.recent_hint.setWordWrap(True);rl.addWidget(self.recent_hint)
        self.list=QListWidget();self.list.setStyleSheet('QListWidget{background:#121923;border:1px solid #293544;border-radius:6px;padding:4px;} QListWidget::item{padding:8px;border-radius:4px;} QListWidget::item:selected{background:#234D49;}')
        self.list.itemDoubleClicked.connect(self.open_item);self.list.itemSelectionChanged.connect(lambda:self.open_button.setEnabled(bool(self.list.selectedItems())))
        rl.addWidget(self.list,1)
        row=QHBoxLayout();self.open_button=button('Open selected',lambda:self.open_item(self.list.currentItem()));self.open_button.setEnabled(False)
        row.addWidget(self.open_button);row.addWidget(button('Browse for a project…',window.open_project));rl.addLayout(row)
        cl.addWidget(recent,1)
        cards.setMaximumWidth(1100);cards.setMinimumHeight(420);outer.addWidget(cards,0,Qt.AlignmentFlag.AlignHCenter)
        cards.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        foot=QLabel('Local AI  /  No uploads  /  Original audio kept');foot.setProperty('role','muted');foot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(foot);outer.addStretch(1)
        self.launch_parts=[head,cards,foot]
        self.refresh()
    def appearance(self):return OUTPUTS[max(0,self.output.checkedId())][0]
    def choose_video(self):self.window.select_video(self.appearance())
    def refresh(self):
        self.list.clear()
        kinds={'speech':'Spoken dialogue','ocr':'On-screen subtitles'}
        for r in recent_projects():
            output='YouTube captions' if r['appearance']=='youtube' else 'Translated video'
            item=QListWidgetItem(f"{r['video']}\n{time.strftime('%d %b %Y, %H:%M',time.localtime(r['modified']))} · {output} · {kinds.get(r['mode'],'')}")
            item.setToolTip(str(r['path']))
            item.setData(Qt.ItemDataRole.UserRole,str(r['path']));item.setSizeHint(QSize(0,52));self.list.addItem(item)
        self.recent_hint.setText('Continue a translation you already started.' if self.list.count() else 'No projects yet. Your projects will appear here.')
        self.open_button.setEnabled(False)
    def open_item(self,item):
        if item:self.window.load_path(item.data(Qt.ItemDataRole.UserRole))
