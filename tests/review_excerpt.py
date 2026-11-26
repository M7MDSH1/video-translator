"""Exercise the real review dialog with corrections read from video frames.
Keeps raw OCR evidence and does not mark user approval or reviewed status.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from videotranslator.app import MainWindow,CueDialog
from videotranslator.project import save_project

app=QApplication([]);window=MainWindow();window.load_path('projects/test-ocr/project.json')
save_project(window.p,'projects/test-ocr/raw-ocr-before-review.json')
originals=[
    "Panicked Mandate Disciple\nMonsters! Faceless monsters... th-they’re inside that tower!",
    "Panicked Mandate Disciple\nThe camp key... I dropped it in there...",
    "Panicked Mandate Disciple\nN-No... those pipes are too high! I’m not going... I’m never going back there!",
    "Soul\nDon’t panic. I’ll get the key back for you.",
]
assert len(window.p['cues'])==4
for i,text in enumerate(originals):
    dialog=CueDialog(window.p['cues'][i],window.p['media']['duration'])
    dialog.original.setPlainText(text);dialog.finish();window.p['cues'][i]=dialog.c
window.save()
assert all(not c['reviewed'] for c in window.p['cues'])
assert window.p['approval'] is None
print('Review dialog corrected four source cues and saved successfully; user review remains pending.')
