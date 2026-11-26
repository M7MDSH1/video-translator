import json,subprocess,unittest
from videotranslator.typography import prepare_caption,wrap_caption,khaam_style,load_fonts
from videotranslator.subtitles import make_ass
from videotranslator.project import new_project

from pathlib import Path
KHAAM=Path(__file__).resolve().parent.parent/'tools'/'khaam'/'arabic.mjs'

class ArabicTypographyTests(unittest.TestCase):
    @unittest.skipUnless(KHAAM.is_file(),'needs the optional Khaam helper tools/khaam, which is not in the repository')
    def test_mixed_ranges_match_khaam_helper(self):
        text='حتى متى معنى مبنى 35–45 و11-01'
        reference=subprocess.check_output(['node','--input-type=module','-e',"import {arLine} from './tools/khaam/arabic.mjs'; process.stdout.write(arLine("+json.dumps(text,ensure_ascii=True)+"));"],encoding='utf-8')
        self.assertEqual(prepare_caption(text,khaam_style()),reference)
    def test_arabic_punctuation_and_caption_endings(self):
        self.assertEqual(prepare_caption('هل أنت هنا?\nنعم, أنا هنا.',khaam_style()),'هل أنت هنا؟\nنعم، أنا هنا')
        self.assertIn('1,400',prepare_caption('عددها 1,400.',khaam_style()))
    def test_no_arabic_word_is_split(self):
        style=khaam_style();lines=wrap_caption('مرحبا بالعالم في ذلك البرج',style,170)
        self.assertEqual(' '.join(lines),'مرحبا بالعالم في ذلك البرج')
        self.assertFalse(any(line.endswith(' في') or line=='في' for line in lines))
    def test_bundled_font_really_loads(self):
        self.assertIn('Almarai',load_fonts())
    def test_ass_uses_separate_spaced_lines_and_zero_tracking(self):
        p=new_project('tests/fixtures/test_excerpt.mp4',{'width':1920,'height':1080,'duration':10})
        p['style']=khaam_style();p['cues']=[{'start':1,'end':3,'original':'Hello','translation':'حتى متى؟\nمعنى مبنى','boxes':[]}]
        ass=make_ass(p)
        self.assertIn('Almarai',ass)
        self.assertEqual(len([l for l in ass.splitlines() if l.startswith('Dialogue: 1')]),2)
        self.assertIn('\\q2',ass)

if __name__=='__main__':unittest.main()
