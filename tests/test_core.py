import copy
import tempfile
import unittest
from pathlib import Path
from videotranslator.project import new_project, save_project, load_project, fingerprint, validate, recognition_key, ocr_key
from videotranslator.subtitles import merge_detections, make_ass, make_srt


class CoreTests(unittest.TestCase):
    def project(self):
        p = new_project('movie.mp4', {'width':1920,'height':1080,'duration':20})
        p['cues'] = [{'start':1.,'end':3.,'original':'Hello','translation':'مرحبا بالعالم!','boxes':[[800,940,320,40]],'reviewed':False}]
        return p

    def test_atomic_roundtrip(self):
        p = self.project()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'project.json'
            save_project(p,path)
            self.assertEqual(load_project(path)['cues'],p['cues'])
    def test_atomic_save_retries_a_transient_windows_reader_lock(self):
        from unittest.mock import patch
        import os
        replace=os.replace;calls=[]
        def locked_then_replace(source,dest):
            calls.append(1)
            if len(calls)<3:raise PermissionError('Transient Windows reader lock')
            replace(source,dest)
        with tempfile.TemporaryDirectory() as folder,patch('videotranslator.project.os.replace',side_effect=locked_then_replace),patch('videotranslator.project.time.sleep'):
            path=Path(folder)/'p.json';save_project(self.project(),path)
            self.assertEqual(len(calls),3);self.assertEqual(load_project(path)['cues'],self.project()['cues'])
    def test_source_change_invalidates_recognition(self):
        with tempfile.TemporaryDirectory() as d:
            video=Path(d)/'source.mp4';video.write_bytes(b'old')
            p=self.project();p['video']=str(video);before=(recognition_key(p),ocr_key(p))
            video.write_bytes(b'new content')
            self.assertNotEqual(before,(recognition_key(p),ocr_key(p)))

    def test_preview_invalidated_by_edit(self):
        p = self.project()
        a = fingerprint(p)
        p['cues'][0]['translation'] = 'اختبار'
        self.assertNotEqual(a,fingerprint(p))

    def test_merge_repeats_not_across_gap(self):
        samples = [{'time':t,'text':s,'boxes':[[30,70,100,20]],'confidence':.9} for t,s in [(0,'Hi'),(.25,'Hi'),(.5,''),(.75,'Hi'),(1,'Hi')]]
        cues = merge_detections(samples,.25,2)
        self.assertEqual(len(cues),2)
        self.assertLessEqual(cues[0]['end'],cues[1]['start'])

    def test_tight_multiline_covers(self):
        p=self.project(); p['appearance']='replace'; p['original_kind']='burned'
        p['cues'][0]['boxes'].append([850,985,220,35])
        ass=make_ass(p)
        self.assertEqual(ass.count('\\p1'),2)
        self.assertIn('مرحبا',ass);self.assertIn('بالعالم!',ass)
        self.assertIn('0:00:01.00',ass)
        self.assertNotIn('m 0 0 l 1920',ass)

    def test_replacement_caption_sits_on_its_covers(self):
        p=self.project(); p['appearance']='replace'; p['original_kind']='burned'
        p['cues'][0]['boxes']=[[200,300,400,50],[250,355,300,45]]  # subtitle high on the left
        import re
        positions=[tuple(map(int,re.search(r'\\pos\((\d+),(\d+)\)',line).groups())) for line in make_ass(p).splitlines() if line.startswith('Dialogue: 1')]
        self.assertEqual([x for x,y in positions],[400,400])
        self.assertTrue(300<=positions[0][1]<=355 and 355<=positions[1][1]<=405)
        p['appearance']='add'  # adding keeps the user's X/Y position
        self.assertIn(f'\\pos(960,{round(1080*p["style"]["y"])})',make_ass(p))
        p['appearance']='replace';p['cues'][0]['boxes']=[]
        p['cues'][0]['cover_spans']=[{'start':1,'end':3,'boxes':[[100,100,200,40]]}]
        self.assertRegex(make_ass(p),r'\\pos\(200,1[34][0-9]\)')

    def test_track_replacement_has_no_cover(self):
        p=self.project(); p['appearance']='replace'; p['original_kind']='track'
        self.assertNotIn('\\p1',make_ass(p))

    def test_invalid_time_rejected(self):
        p=self.project(); p['cues'][0]['end']=.5
        with self.assertRaises(ValueError): validate(p)

    def test_missing_boxes_rejected(self):
        p=self.project(); p['appearance']='replace'; p['original_kind']='burned'; p['cues'][0]['boxes']=[]
        with self.assertRaises(ValueError): validate(p,render=True)

    def test_srt_millisecond_carry(self):
        p=self.project(); p['cues'][0]['start']=1.9999
        self.assertIn('00:00:02,000',make_srt(p))

    def test_ass_text_cannot_inject_overrides(self):
        p=self.project(); p['cues'][0]['translation']='Hello {\\p1}\\N'
        self.assertNotIn('{\\p1}',make_ass(p))

    def test_arabic_uses_automatic_bidi_base_direction(self):
        style=next(line for line in make_ass(self.project()).splitlines() if line.startswith('Style:'))
        self.assertEqual(style.split(',')[-1],'-1')

if __name__ == '__main__': unittest.main()
