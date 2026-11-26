"""Phone mode window: shows the address and code to type into the phone app, and what the phone's video is doing."""
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QProgressBar,QPushButton

STAGE={'receive':'Receiving the video from the phone','recognize':'Recognising the dialogue','translate':'Translating',
       'export':'Exporting the video','done':'Ready. The phone can download it now.'}

class PhoneDialog(QDialog):
    def __init__(self,server,parent=None):
        super().__init__(parent);self.server=server;self.setWindowTitle('Phone mode');self.resize(460,380)
        layout=QVBoxLayout(self);layout.setSpacing(10);layout.setContentsMargins(28,24,28,24)
        note=QLabel('Open Video Translator on your phone and type these in. The phone and this PC must be on the same Wi-Fi. '
                    'If Windows asks, allow access on private networks.');note.setWordWrap(True);note.setProperty('role','muted');layout.addWidget(note)
        for title,value in (('PC address',server.address()),('Code',' '.join(server.code))):
            label=QLabel(title);label.setProperty('role','muted');layout.addWidget(label)
            big=QLabel(value);big.setStyleSheet('font-size:28px;font-weight:700;color:#57D6B5;');big.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(big)
        layout.addSpacing(8);self.state=QLabel();self.state.setWordWrap(True);layout.addWidget(self.state)
        self.bar=QProgressBar();self.bar.setRange(0,100);layout.addWidget(self.bar);layout.addStretch()
        close=QPushButton('Hide (phone mode stays on)');close.clicked.connect(self.accept);layout.addWidget(close)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(700);self.refresh()
    def refresh(self):
        job=self.server.status();working=job['state'] in ('receiving','working')
        self.bar.setVisible(working);self.bar.setValue(int(job['progress']))
        self.state.setText({'idle':'Waiting for a video from the phone.','error':'Stopped: '+job['message']}.get(job['state'],
            f"{job['name']}\n{STAGE.get(job['stage'],job['stage'])}"))
