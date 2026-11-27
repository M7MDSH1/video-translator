import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from videotranslator.project import new_project,save_project
from videotranslator.subtitles import cue,display_cues,make_srt,make_ass,merge_detections
from videotranslator.translation import clean_ocr,candidate_terms

def project(appearance='replace'):
    p=new_project('movie.mp4',{'width':1920,'height':1080,'duration':60})
    p.update(appearance=appearance,original_kind='burned')
    # Dialogue skipped in-game: three lines on screen for 0.25 s each.
    for i,t in enumerate([10,10.25,10.5]):
        c=cue(t,t+.25,f'Line {i}',[[700,900,500,40]],.9);c['translation']='ترجمة عربية من عشرين حرفا'
        c['cover_spans']=[{'start':t,'end':t+.25,'boxes':[[700,900,500,40]]}];p['cues'].append(c)
    p['cues'].append(dict(cue(40,43,'Later',[[700,900,500,40]],.9),translation='لاحقا'))
    return p

class DisplayTimingTests(unittest.TestCase):
    def test_rapid_lines_become_readable_without_overlap_or_runaway_lag(self):
        pairs=display_cues(project())
        shown=[s for _,s in pairs]
        for a,b in zip(shown,shown[1:]):self.assertLessEqual(a['end'],b['start']+1e-9)
        for c,s in pairs[:3]:
            self.assertGreaterEqual(s['end']-s['start'],1.2)
            self.assertLessEqual(s['start']-c['start'],8)
        self.assertEqual((shown[3]['start'],shown[3]['end']),(40,43))  # an already readable cue is unchanged
        self.assertIs(pairs[3][0],pairs[3][1])

    def test_long_burst_shares_time_instead_of_crushing_last_lines(self):
        p=project();p['cues']=[]
        for i in range(6):
            t=10+i*.2;c=cue(t,t+.2,f'Line {i}',[],.9);c['translation']='ت'*120;p['cues'].append(c)
        pairs=display_cues(p);shown=[s for _,s in pairs]
        for a,b in zip(shown,shown[1:]):self.assertLessEqual(a['end'],b['start']+1e-9)
        for c,s in pairs:
            self.assertGreaterEqual(s['end']-s['start'],1.7)  # about 9 s shared by six lines
            self.assertLessEqual(s['start']-c['start'],8+1e-6)

    def test_held_caption_keeps_original_cover_position_and_covers_keep_original_time(self):
        p=project();held=display_cues(p)[1][1]
        self.assertTrue(held['cover_spans'] and all(s['boxes']==[[700,900,500,40]] for s in held['cover_spans']))
        ass=make_ass(p)
        self.assertIn('Dialogue: 0,0:00:10.00,0:00:10.50',ass)   # original cover from one OCR sample before the original time
        text_events=[l for l in ass.splitlines() if l.startswith('Dialogue: 1,')]
        self.assertTrue(any(l.startswith('Dialogue: 1,0:00:11.') for l in text_events))  # text held later

    def test_srt_uses_display_timing_without_joiners(self):
        p=project('file');p['cues'][0]['translation']='حتى'
        srt=make_srt(p)
        self.assertNotIn('‍',srt)
        self.assertIn('00:00:10,000 --> 00:00:11,200',srt)

class CaptionSizeTests(unittest.TestCase):
    def test_all_lines_of_a_caption_share_one_text_size(self):
        from PySide6.QtWidgets import QApplication
        from videotranslator.subtitles import caption_blocks
        QApplication.instance() or QApplication([])
        p=project();c=cue(0,3,'Name\nA long first line here\nshort',[[860,880,200,40],[460,930,1000,40],[760,980,400,40]],.9)
        c['translation']='الاسم\nسطر أول طويل جدا لا يتسع بسهولة داخل غطائه الضيق هنا\nقصير'
        blocks=caption_blocks(c,p,1920,1080,1)
        self.assertEqual(len(blocks),3)
        self.assertEqual(len({b['style']['size'] for b in blocks}),1)

class OcrCleanupTests(unittest.TestCase):
    def test_underscores_become_ellipsis(self):
        self.assertEqual(clean_ocr('The bowstring__. why did it snap? Why_'),'The bowstring... why did it snap? Why...')

    def test_lone_bar_or_slash_is_the_letter_i_in_source_only(self):
        from videotranslator.translation import clean_source
        self.assertEqual(clean_source('But / accidentally\nAfter | took it, and/or'),'But I accidentally\nAfter I took it, and/or')
        self.assertEqual(clean_ocr('سول / مات'),'سول / مات')

    def test_cover_reaches_past_trailing_ellipsis(self):
        from videotranslator.subtitles import cover_rect
        p=project();p['style']['padding']=7
        x,y,w,h=cover_rect([702,926,492,38],p,1920,1080)
        self.assertGreaterEqual(x+w,1222);self.assertLessEqual(x,676)  # "look…" ends at 1220 in the source frame
        self.assertEqual((y,h),(919,52))

    def test_garbled_repeat_merges_but_different_short_lines_do_not(self):
        samples=[{'time':t,'text':'Soul\n'+s,'boxes':[[1,2,3,4]],'confidence':.9} for t,s in
                 [(0,'AHHHHHHHHHQIIII'),(.25,'AHHHHHHHHHLILUL'),(.5,'AHHHHHHHHHWWII'),(.75,'Yes'),(1,'No')]]
        self.assertEqual([c['original'].split('\n')[1] for c in merge_detections(samples,.25,5)],['AHHHHHHHHHQIIII','Yes','No'])

class NameFirstTests(unittest.TestCase):
    def test_candidates_include_speakers_and_mid_sentence_names(self):
        cues=[cue(0,1,'Soul\nI hear the Four Axes are dead.',[],.9),cue(1,2,'Swordsman Captain\nNo wonder he wanted the Four Axes killed',[],.9),
              cue(2,3,'Look. That is not it.',[],.9)]
        terms={t['term']:t for t in candidate_terms(cues)}
        self.assertTrue(terms['Soul']['speaker'])
        self.assertIn('Four Axes',terms);self.assertFalse(terms['Four Axes']['speaker'])
    def test_a_sentence_split_over_two_lines_is_not_a_speaker_name(self):
        cues=[cue(0,1,'I need your help\nright now',[],.9),cue(1,2,'I need your help\nwith this',[],.9),cue(2,3,'Li Wuxiang\nFollow me',[],.9)]
        terms={t['term']:t for t in candidate_terms(cues)}
        self.assertNotIn('I need your help',terms);self.assertTrue(terms['Li Wuxiang']['speaker'])
        self.assertNotIn('That',terms)  # sentence start, not a name

    def test_names_are_translated_before_dialogue_and_used_in_batches(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'project.json';p=new_project('movie.mp4',{'width':640,'height':360,'duration':10,'streams':[]})
            p['cues']=[cue(0,2,'Soul\nThe Four Axes are dead.',[],.9)];save_project(p,path)
            from videotranslator.engine import Worker
            w=Worker(path)
            def reply(content):
                r=MagicMock();r.__enter__.return_value=r;r.iter_lines.return_value=[json.dumps({'message':{'content':json.dumps(content)}}).encode()];return r
            show=MagicMock();show.json.return_value={'details':{'format':'gguf'}}
            terms={'terms':[{'source':'Soul','translation':'سول'},{'source':'Four Axes','translation':'الفؤوس الأربعة'}]}
            batch={'translations':[{'id':0,'translation':'سول / مات الفؤوس الأربعة_','source_language':'en','uncertain':False}],'terms':[]}
            with patch('requests.Session') as session:
                session.return_value.post.side_effect=[show,reply(terms),reply(batch),MagicMock()]  # last: model unload
                w.translate()
                batch_prompt=session.return_value.post.call_args_list[2].kwargs['json']['messages'][0]['content']
            self.assertIn('الفؤوس الأربعة',batch_prompt)
            self.assertEqual(w.p['translation_memory']['terms']['Soul'],'سول')
            self.assertTrue(w.p['translation_memory']['seeded'])
            self.assertEqual(w.p['cues'][0]['translation'],'سول / مات الفؤوس الأربعة...')
