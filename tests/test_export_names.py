import tempfile
from pathlib import Path
from videotranslator.export_paths import reserve_export
from unittest.mock import patch
from videotranslator.project import new_project,save_project,load_project,fingerprint
from videotranslator.engine import Worker
from videotranslator.subtitles import cue

def test_named_bundle_and_repeated_exports_preserve_existing_files():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);p={'video':'My Video (Edited).mp4','target':'ar'}
        first=reserve_export(root,p)
        assert first.name=='My Video (Edited) - Arabic'
        first.with_suffix('.mkv').write_bytes(b'original export')
        second=reserve_export(root,p)
        assert second.parent.name==first.parent.name+' (2)'
        assert first.with_suffix('.mkv').read_bytes()==b'original export'
        assert second.name==first.name

def test_windows_unsafe_characters_arabic_and_dots_are_safe():
    with tempfile.TemporaryDirectory() as tmp:
        prefix=reserve_export(Path(tmp),{'video':'فيديو.v1: test?.mp4','target':'ar'})
        assert 'فيديو' in prefix.name
        assert not any(c in prefix.name for c in '<>:"/\\|?*')
        assert prefix.with_suffix('.srt').stem==prefix.name

def test_long_names_are_bounded():
    with tempfile.TemporaryDirectory() as tmp:
        prefix=reserve_export(Path(tmp),{'video':'a'*220+'.mp4','target':'ar'})
        assert len(prefix.name)<=90
        assert prefix.name.endswith('Arabic')

def test_worker_bundles_video_sidecars_and_project_and_records_location():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);path=root/'project.json';p=new_project(root/'My Movie.mp4',{'width':640,'height':360,'duration':5,'streams':[]})
        p['cues']=[cue(0,2,'Hello',[],.9)];p['cues'][0]['translation']='مرحبا'
        preview=root/'preview.mp4';preview.write_bytes(b'preview')
        p['preview']={'path':str(preview),'fingerprint':fingerprint(p)};p['approval']=fingerprint(p);save_project(p,path)
        def fake_encode(args,*_):Path(args[-1]).write_bytes(b'encoded video')
        with patch('videotranslator.engine.ROOT',root),patch('videotranslator.engine.make_ass',return_value='ASS'),patch('videotranslator.engine.make_srt',return_value='SRT'):
            w=Worker(path)
            with patch.object(w,'command',side_effect=fake_encode):w.render()
            video=Path(load_project(path)['last_export'])
            assert video==root/'exports'/'My Movie - Arabic'/'My Movie - Arabic.mkv'
            assert {f.suffix for f in video.parent.iterdir()}=={'.mkv','.ass','.srt','.json'}
            assert load_project(video.with_suffix('.project.json'))['last_export']==str(video)
            w.p['appearance']='file';w.p['preview']['fingerprint']=fingerprint(w.p);w.p['approval']=fingerprint(w.p);w.render()
            srt=Path(w.p['last_export'])
            assert srt.parent.name=='My Movie - Arabic (2)'
            assert srt.suffix=='.srt' and not list(srt.parent.glob('*.mkv'))
            assert video.read_bytes()==b'encoded video'
