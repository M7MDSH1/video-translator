"""Exercise the real rules dialog and render an Arabic replacement on a QA copy."""
import copy,json,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QProcess,QUrl
from videotranslator.app import create_application,MainWindow
from videotranslator.replacement_dialog import ReplacementDialog
from videotranslator.project import load_project,save_project

out=ROOT/'artifacts'/'replacements';out.mkdir(exist_ok=True)
app=create_application([]);w=MainWindow();w.resize(1440,1000);w.show();w.audio.setVolume(0)
p=load_project(ROOT/'artifacts'/'ui-redesign'/'ocr'/'project.json')
originals=[c['original'] for c in p['cues']];source=Path(p['video']);stat=source.stat()
p['approval']=None;save_project(p,out/'project.json');w.load_path(out/'project.json')
errors=[];w.error=lambda e:errors.append(str(e))
def edit(dialog):
    dialog.table.item(0,0).setText('football');dialog.table.item(0,1).setText('soccer')
    dialog.add_rule('وحوش','مخلوقات');dialog.preview();dialog.show();app.processEvents()
    dialog.grab().save(str(out/'replacement-editor.png'))
    dialog.finish(True);return 1
try:
    with patch.object(ReplacementDialog,'exec',edit):w.edit_replacements()
    assert not errors,errors
    assert any('مخلوقات' in c['translation'] for c in w.p['cues'])
    assert originals==[c['original'] for c in w.p['cues']]
    assert not w.export_button.isEnabled()
    w.tabs.setCurrentIndex(2);w.preview_start.setValue(1);w.preview_length.setValue(5);w.run('preview')
    deadline=time.monotonic()+120
    while w.proc.state()!=QProcess.ProcessState.NotRunning:
        app.processEvents();time.sleep(.03)
        assert time.monotonic()<deadline,'Preview timed out'
    for _ in range(60):app.processEvents();time.sleep(.03)
    assert not errors,errors
    assert w.proc.exitCode()==0,w.log.toPlainText()
    assert w.preview_current() and w.p['approval'] is None
    assert stat.st_size==source.stat().st_size and stat.st_mtime_ns==source.stat().st_mtime_ns
    w.grab().save(str(out/'preview-in-app.png'))
    (out/'result.json').write_text(json.dumps({'preview':w.p['preview']['path'],'original_text_unchanged':True,'source_file_unchanged':True,'approval':None,'rules':w.p['replacements'],'translations':[c['translation'] for c in w.p['cues']]},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Real dialog application, original-text preservation, live update, save, Arabic preview and approval invalidation passed.')
finally:
    w.autosave.stop();w.player.stop();w.player.setSource(QUrl());w.p=None;w.close();app.processEvents()
