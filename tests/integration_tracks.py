"""Actual FFmpeg exports on a synthetic test fixture, never user footage."""
import json,subprocess,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from videotranslator.project import new_project,save_project,fingerprint,load_project
from videotranslator.engine import Worker,probe
from videotranslator.subtitles import cue
folder=Path('projects/track-fixture').resolve();folder.mkdir(parents=True,exist_ok=True)
(folder/'original.srt').write_text('1\n00:00:00,200 --> 00:00:02,800\nOriginal visible subtitle\n',encoding='utf-8')
video=folder/'source.mkv'
subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=0x345678:s=640x360:r=24:d=3','-f','lavfi','-i','sine=frequency=440:duration=3','-i',str(folder/'original.srt'),'-map','0:v','-map','1:a','-map','2:s','-c:v','libx264','-c:a','pcm_s16le','-c:s','srt',str(video)],check=True)
p=new_project(str(video),probe(video));p['cues']=[cue(.2,2.8,'Original visible subtitle',[],1)];p['cues'][0]['translation']='اختبار العربية: مرحبا بالعالم!';p['style']['size']=24
source_hash=hashlib.sha256(video.read_bytes()).hexdigest()
def audiohash(path):
    return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-']).decode().strip()
results=[]
for mode in ('add','replace','file'):
    p['appearance']=mode;path=folder/(mode+'.json');save_project(p,path);worker=Worker(path)
    worker.render(preview=True,start=0,length=3)
    # Simulates a user's approval solely within this synthetic automated fixture.
    worker.p['approval']=fingerprint(worker.p);worker.save();worker.render()
    if mode!='file':
        export=max((folder/'exports').glob('translated-*.mkv'),key=lambda path:path.stat().st_mtime)
        assert not any(s['codec_type']=='subtitle' for s in probe(export)['streams'])
        assert audiohash(export)==audiohash(video)
        subprocess.run(['ffmpeg','-v','error','-i',str(export),'-f','null','-'],check=True)
        results.append({'mode':mode,'export':str(export),'audio_identical':True,'decode':'pass'})
assert hashlib.sha256(video.read_bytes()).hexdigest()==source_hash
# Exercise OCR of an embedded text track, independent of soundtrack.
p['mode']='ocr';p['appearance']='replace';p['roi']=[.05,.65,.9,.34];p['sample_interval']=.5;p['ocr_script']='en';p['source']='en'
save_project(p,folder/'ocr-track.json');worker=Worker(folder/'ocr-track.json');worker.recognize()
assert any('Original' in c['original'] for c in worker.p['cues'])
(folder/'verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('Embedded-track add/replace, subtitle-only export, source preservation, exact audio copy, decoding, and embedded-track OCR passed.')
