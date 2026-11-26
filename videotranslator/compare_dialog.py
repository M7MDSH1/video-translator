"""Compare installed translation models on this project against a subtitle file you corrected by hand.

Runs tools/compare_models.py in its own process; the project itself is not changed."""
import sys
from PySide6.QtCore import Qt,QProcess
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,
    QPlainTextEdit,QPushButton,QFileDialog,QSpinBox)
from .project import ROOT

class CompareDialog(QDialog):
    def __init__(self,project_path,models,current,parent=None):
        super().__init__(parent);self.project_path=str(project_path);self.proc=None
        self.setWindowTitle('Compare translation models');self.resize(820,620);layout=QVBoxLayout(self)
        note=QLabel('Each ticked model translates the same lines of this video. The result is scored against a subtitle file '
                    'you already corrected by hand (SRT, in the target language). Higher is better; a point or two apart is noise. '
                    'Your project is not changed.');note.setWordWrap(True);layout.addWidget(note)
        row=QHBoxLayout();self.reference=QLineEdit();self.reference.setPlaceholderText('Hand-corrected SRT file for this video')
        browse=QPushButton('Browse…');browse.clicked.connect(self.browse);row.addWidget(self.reference,1);row.addWidget(browse);layout.addLayout(row)
        self.models=QListWidget();self.models.setMaximumHeight(170)
        for name in models:
            item=QListWidgetItem(name);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if name==current else Qt.CheckState.Unchecked);self.models.addItem(item)
        layout.addWidget(self.models)
        row=QHBoxLayout();row.addWidget(QLabel('Lines to translate'));self.count=QSpinBox();self.count.setRange(20,2000);self.count.setValue(60)
        row.addWidget(self.count);row.addStretch();self.run_button=QPushButton('Run comparison');self.run_button.clicked.connect(self.toggle)
        row.addWidget(self.run_button);layout.addLayout(row)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setStyleSheet('font-family:Consolas,monospace;');layout.addWidget(self.output,1)
    def browse(self):
        path,_=QFileDialog.getOpenFileName(self,'Hand-corrected subtitles','','Subtitles (*.srt)')
        if path:self.reference.setText(path)
    def chosen(self):
        return [self.models.item(i).text() for i in range(self.models.count()) if self.models.item(i).checkState()==Qt.CheckState.Checked]
    def command(self):
        return ['-u',str(ROOT/'tools'/'compare_models.py'),self.project_path,self.reference.text().strip(),'--models',*self.chosen(),'--count',str(self.count.value())]
    def toggle(self):
        if self.proc:self.proc.kill();return
        if not self.reference.text().strip() or not self.chosen():self.output.setPlainText('Choose a reference SRT file and tick at least one model.');return
        self.output.setPlainText('Running. About one to four minutes per model…\n')
        self.proc=QProcess(self);self.proc.setWorkingDirectory(str(ROOT));self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(lambda:self.output.appendPlainText(bytes(self.proc.readAllStandardOutput()).decode('utf-8',errors='replace').rstrip()))
        self.proc.finished.connect(self.finished);self.run_button.setText('Stop')
        self.proc.start(str(ROOT/'.venv'/'Scripts'/'python.exe') if (ROOT/'.venv').is_dir() else sys.executable,self.command())
    def finished(self,*_):
        self.proc=None;self.run_button.setText('Run comparison');self.output.appendPlainText('\nFinished.')
    def reject(self):
        if self.proc:self.proc.finished.disconnect(self.finished);self.proc.kill();self.proc.waitForFinished(3000)
        super().reject()
