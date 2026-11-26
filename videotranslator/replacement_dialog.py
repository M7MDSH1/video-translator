"""Preview and explicitly apply saved replacement rules to final subtitles."""
import copy
import html
import unicodedata
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,
    QTableWidgetItem,QHeaderView,QCheckBox,QPushButton,QTextBrowser)
from .replacements import DEFAULTS,validate_rules,apply_replacements

def text_html(text):
    """Give every paragraph its own direction; never mix an arrow into Arabic."""
    if not text.strip():return '<p dir="ltr"><i>Removed</i></p>'
    paragraphs=[]
    for line in text.split('\n'):
        direction=next((unicodedata.bidirectional(c) for c in line if unicodedata.bidirectional(c) in ('L','R','AL')),'L')
        rtl=direction in ('R','AL')
        paragraphs.append(f'<p dir="{"rtl" if rtl else "ltr"}" align="{"right" if rtl else "left"}">{html.escape(line)}</p>')
    return ''.join(paragraphs)

def align(item):
    """Right-align a rule cell whose text starts in a right-to-left script."""
    rtl=next((unicodedata.bidirectional(c) in ('R','AL') for c in item.text() if unicodedata.bidirectional(c) in ('L','R','AL')),False)
    item.setTextAlignment((Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)|Qt.AlignmentFlag.AlignVCenter)

class ReplacementDialog(QDialog):
    def __init__(self,project,parent=None):
        super().__init__(parent);self.project=project;self.apply_now=False
        self.setWindowTitle('Word & phrase replacements');self.resize(850,650)
        layout=QVBoxLayout(self)
        note=QLabel('Replace final subtitle text after translation. Use words in the output language. Recognised text and audio stay unchanged. Leave Replace with blank to delete a word or phrase.');note.setWordWrap(True);layout.addWidget(note)
        example=QLabel('<table width="100%"><tr><th align="left">Example: Find</th><th align="left">Replace with</th></tr><tr><td>football</td><td>soccer</td></tr><tr><td dir="rtl" align="right">كرة القدم</td><td dir="rtl" align="right">زومبا</td></tr></table>');layout.addWidget(example)
        settings=project.get('replacements',DEFAULTS)
        row=QHBoxLayout();self.enabled=QCheckBox('Enable rules');self.case=QCheckBox('Match case');self.words=QCheckBox('Whole words / phrases')
        for widget,value in ((self.enabled,settings.get('enabled',True)),(self.case,settings.get('match_case',False)),(self.words,settings.get('whole_words',True))):widget.setChecked(value);row.addWidget(widget)
        layout.addLayout(row)
        self.words.setToolTip('Arabic whole-word matching accepts common attached prefixes and vowel marks. Prefixes are retained unless deleting. Matching is literal, not a morphological analysis; inspect the preview.')
        self.table=QTableWidget(0,2);self.table.setHorizontalHeaderLabels(['Find','Replace with'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);layout.addWidget(self.table,1)
        for rule in settings.get('rules',[]):self.add_rule(rule['find'],rule['replace'])
        if not self.table.rowCount():self.add_rule()
        row=QHBoxLayout()
        for text,fn in [('Add rule',lambda:self.add_rule()),('Remove selected rule',self.remove_rule),('Preview matches',self.preview)]:
            b=QPushButton(text);b.clicked.connect(fn);row.addWidget(b)
        layout.addLayout(row)
        self.include_reviewed=QCheckBox('Also change reviewed subtitles (changed lines become unreviewed)');layout.addWidget(self.include_reviewed)
        self.result=QTextBrowser();self.result.setOpenExternalLinks(False);self.result.setMaximumHeight(180);layout.addWidget(self.result)
        hint=QLabel('Save rules applies them to future translation/resume runs. Apply to current subtitles also updates existing lines immediately. Disable/remove rules and Apply to restore untouched pre-rule text. Manual edits are retained.');hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout()
        for text,apply in [('Save rules',False),('Apply to current subtitles',True)]:
            b=QPushButton(text);b.clicked.connect(lambda checked=False,apply=apply:self.finish(apply));row.addWidget(b)
        b=QPushButton('Cancel');b.clicked.connect(self.reject);row.addWidget(b);layout.addLayout(row)
        self.table.itemChanged.connect(self.cell_changed)
        for widget in (self.enabled,self.case,self.words,self.include_reviewed):widget.toggled.connect(self.preview)
        self.preview()

    def add_rule(self,find='',replacement=''):
        self.table.blockSignals(True);r=self.table.rowCount();self.table.insertRow(r)
        for col,text in ((0,find),(1,replacement)):
            item=QTableWidgetItem(text);align(item);self.table.setItem(r,col,item)
        self.table.blockSignals(False)

    def cell_changed(self,item):
        self.table.blockSignals(True);align(item);self.table.blockSignals(False);self.preview()

    def remove_rule(self):
        r=self.table.currentRow()
        if r>=0:self.table.removeRow(r)
        self.preview()

    def settings(self):
        rules=[]
        for r in range(self.table.rowCount()):
            find=self.table.item(r,0).text().strip();replacement=self.table.item(r,1).text().strip()
            if not find and not replacement:continue
            rules.append({'find':find,'replace':replacement})
        settings={'enabled':self.enabled.isChecked(),'match_case':self.case.isChecked(),'whole_words':self.words.isChecked(),'rules':rules}
        validate_rules(settings);return settings

    def preview(self,*args):
        try:
            draft=copy.deepcopy(self.project);draft['replacements']=self.settings()
            changed=apply_replacements(draft,self.include_reviewed.isChecked())
            lines=[f'<p>{changed} {"subtitle" if changed==1 else "subtitles"} would change. Reviewed lines are '+('included.' if self.include_reviewed.isChecked() else 'excluded.')+'</p>']
            for before,after in zip(self.project['cues'],draft['cues']):
                if before['translation']!=after['translation']:
                    lines.append(f'<p dir="ltr">{before.get("start",0):.2f}s</p><table width="100%" cellspacing="8"><tr><th width="50%" align="left">Before</th><th width="50%" align="left">After</th></tr><tr><td width="50%" valign="top">{text_html(before["translation"])}</td><td width="50%" valign="top">{text_html(after["translation"])}</td></tr></table>')
            self.result.setHtml(''.join(lines));return True
        except ValueError as exc:self.result.setPlainText(str(exc));return False

    def finish(self,apply):
        if self.preview():self.apply_now=apply;self.accept()
