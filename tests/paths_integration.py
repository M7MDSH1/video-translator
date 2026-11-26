import sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from videotranslator.project import new_project,save_project
from videotranslator.engine import Worker,probe
from videotranslator.subtitles import cue
folder=Path("projects/path's test").resolve();folder.mkdir(parents=True,exist_ok=True)
source=folder/"movie's source.mkv";shutil.copyfile('projects/track-fixture/source.mkv',source)
p=new_project(source,probe(source));p['cues']=[cue(.2,2.8,'Original visible subtitle',[],1)];p['cues'][0]['translation']='اختبار';p['style']['size']=24
save_project(p,folder/'project.json');Worker(folder/'project.json').render(preview=True,start=.5,length=2)
print('Apostrophes/spaces in original, project and output paths passed.')
