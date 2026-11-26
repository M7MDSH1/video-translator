import json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
Path('artifacts/verification').mkdir(parents=True,exist_ok=True)
from videotranslator.project import new_project,save_project,load_project
from videotranslator.engine import probe
path=Path('projects/cancel-test/project.json').resolve()
p=new_project('tests/fixtures/test_excerpt.mp4',probe('tests/fixtures/test_excerpt.mp4'));p.update(mode='ocr',roi=[.15,.78,.7,.15],range_end=8)
save_project(p,path);path.with_suffix('.cancel').unlink(missing_ok=True)
with open('artifacts/verification/cancel-test.log','w',encoding='utf-8') as log:
    proc=subprocess.Popen([sys.executable,'-m','videotranslator.engine','recognize',str(path)],stdout=log,stderr=log)
    deadline=time.time()+120
    while time.time()<deadline:
        cp=load_project(path)['checkpoints']
        if cp.get('ocr_cursor',0)>=2:break
        if proc.poll() is not None:raise AssertionError('Worker ended before cancellation point')
        time.sleep(.2)
    else:
        proc.kill();raise AssertionError('No checkpoint')
    path.with_suffix('.cancel').touch();proc.wait(timeout=20)
    assert proc.returncode==2
    saved=load_project(path);count=len(saved['ocr_samples']);assert 0<count<32
    path.with_suffix('.cancel').unlink()
    subprocess.run([sys.executable,'-m','videotranslator.engine','recognize',str(path)],stdout=log,stderr=log,check=True,timeout=120)
    final=load_project(path)
    assert len(final['ocr_samples'])==32
    assert final['ocr_samples'][:count]==saved['ocr_samples']
    assert final['checkpoints']['recognized']
    print(f'Cancelled after {count} saved frames; resumed to 32 without duplication or loss.')
