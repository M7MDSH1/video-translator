import unittest
from videotranslator.project import new_project
from videotranslator.subtitles import cue,stable_cover_spans,active_covers,caption_blocks,caption_intervals

class StableCoversTests(unittest.TestCase):
    def setUp(self):
        self.p=new_project('fixture.mp4',{'width':1920,'height':1080,'duration':5})
        self.p.update(appearance='replace',original_kind='burned')
        self.c=cue(0,3,'Speaker\nDialogue',[[780,870,360,36],[520,925,880,40]],1)
        self.c['translation']='تلميذ المانديت المذعور\nوحوش! وحوش بلا وجوه... إنها داخل ذلك البرج!'
        self.c['cover_spans']=[{'start':i,'end':i+1,'boxes':[[780+i,870-i,360,36+i],[520-i,925+i,880+i,40]]} for i in range(3)]
        self.p['cues']=[self.c]
    def test_small_ocr_jitter_is_one_fixed_tight_run(self):
        spans=stable_cover_spans(self.c)
        self.assertEqual(len(spans),1)
        self.assertEqual(active_covers(self.c,.5),active_covers(self.c,2.5))
        self.assertEqual(caption_intervals(self.c,self.p),[(0,3)])
        for original in self.c['cover_spans']:
            for b,s in zip(original['boxes'],spans[0]['boxes']):
                self.assertLessEqual(s[0],b[0]);self.assertLessEqual(s[1],b[1])
                self.assertGreaterEqual(s[0]+s[2],b[0]+b[2]);self.assertGreaterEqual(s[1]+s[3],b[1]+b[3])
                self.assertLessEqual(s[2]-b[2],8);self.assertLessEqual(s[3]-b[3],8)
    def test_real_movement_and_gaps_are_not_smoothed_away(self):
        self.c['cover_spans'][1]['boxes'][0][0]+=100
        self.assertEqual(len(stable_cover_spans(self.c)),3)
        self.c['cover_spans'][1]['start']=1.5
        self.assertEqual(active_covers(self.c,1.25),[])
        self.assertEqual(caption_blocks(self.c,self.p,1920,1080,1.25),[])
    def test_nested_punctuation_detection_does_not_create_an_extra_line(self):
        self.c['cover_spans'][1]['boxes'].append([600,940,25,10])
        self.assertEqual(len(stable_cover_spans(self.c)),1)
        self.assertEqual(len(active_covers(self.c,1.5)),2)
    def test_lines_fit_individual_covers_and_stay_identical_through_jitter(self):
        a=caption_blocks(self.c,self.p,1920,1080,.5);b=caption_blocks(self.c,self.p,1920,1080,2.5)
        self.assertEqual(a,b);self.assertEqual(len(a),2)
        for block in a:
            x,y,w,h=block['cover']
            ix,iy,iw,ih=block['ink_bounds']
            self.assertGreaterEqual(ix,x+2);self.assertLessEqual(ix+iw,x+w-2)
            self.assertGreaterEqual(iy,y+2);self.assertLessEqual(iy+ih,y+h-2)
    def test_unsupported_arabic_font_uses_real_arabic_font_for_fitting(self):
        self.p['style']['font']='Algerian'
        self.assertTrue(all(b['style']['font']=='Almarai' for b in caption_blocks(self.c,self.p,1920,1080,1)))
    def test_all_words_retained_when_translation_line_count_changes(self):
        self.c['translation']='one two three four five six seven eight'
        blocks=caption_blocks(self.c,self.p,1920,1080,1)
        self.assertEqual(' '.join(b['lines'][0] for b in blocks),self.c['translation'])
