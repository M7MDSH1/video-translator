import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'tools'))
from compare_models import chrf,spoken,given_names,speaker_label,passages,sample_passages,parse_srt

PROFILE={'speaker_y':.82,'dialogue_y':.88,'tolerance':.018,'vertical_drift':.035}
def project(profile=PROFILE):return {'media':{'height':1000},'dialogue_profile':profile}
SPEAKER_BOX=[400,805,100,30];DIALOGUE_BOX=[300,865,400,30];SECOND_BOX=[300,915,400,30]

class CompareModelsTests(unittest.TestCase):
    def test_chrf_ranks_closer_translation_higher(self):
        ref='لا تقلق، سأستعيد المفتاح لك'
        self.assertAlmostEqual(chrf([(ref,ref)]),100)
        self.assertEqual(chrf([('xyz',ref)]),0)
        self.assertGreater(chrf([('لا تقلق، سأعيد المفتاح',ref)]),chrf([('اهدأ، سأجلبه',ref)]))
    def test_diacritics_do_not_change_the_score(self):
        self.assertAlmostEqual(chrf([('مَرْحَبًا','مرحبا')]),100)

    def test_speaker_verified_by_screen_position(self):
        self.assertEqual(speaker_label({'original':'Soul\nDont panic.','boxes':[SPEAKER_BOX,DIALOGUE_BOX]},project()),'Soul')
    def test_repeated_dialogue_is_not_a_speaker(self):
        # "Run" heads many two-line cues but sits at dialogue height, so it is dialogue.
        run={'original':'Run\nthey are coming','boxes':[DIALOGUE_BOX,SECOND_BOX]}
        self.assertIsNone(speaker_label(run,project()))
        # Without a dialogue layout nothing is guessed from wording; only --speakers names count.
        self.assertIsNone(speaker_label({'original':'Run\nthey are coming','boxes':[SPEAKER_BOX,DIALOGUE_BOX]},project(None)))
        self.assertEqual(speaker_label({'original':'Soul\nWait','boxes':[]},project(None),['Soul']),'Soul')
    def test_name_line_dropped_only_when_model_wrote_the_name(self):
        terms={'Soul':'سول','The Hunt':'الصيّاد'}
        self.assertEqual(spoken('سول\nلا تقلق.','Soul',terms),'لا تقلق.')
        # Punctuation and marks aside: "الصياد:" is still the given name.
        self.assertEqual(spoken('الصياد:\nاقتل!','The Hunt',terms),'اقتل!')
        # The model skipped the name and wrapped the dialogue: both dialogue lines stay.
        self.assertEqual(spoken('لا تقلق\nسأستعيد المفتاح','Soul',terms),'لا تقلق\nسأستعيد المفتاح')
        # No name given to the model: keep everything.
        self.assertEqual(spoken('سول\nلا تقلق.','Soul',{}),'سول\nلا تقلق.')
    def test_repeated_dialogue_without_the_name_is_kept(self):
        # Regression: the model omitted "Soul" twice and both replies start "Help me".
        terms={'Soul':'سول'}
        self.assertEqual(spoken('Help me\nPlease hurry','Soul',terms),'Help me\nPlease hurry')
        self.assertEqual(spoken('Help me\nThey are coming','Soul',terms),'Help me\nThey are coming')
    def test_glossary_spelling_is_the_name_that_counts(self):
        p={'cues':[],'translation_memory':{'terms':{'Soul':'روح'}},'glossary':{'Soul':'سول'}}
        terms=given_names(p)
        self.assertEqual(spoken('سول\nلا تقلق.','Soul',terms),'لا تقلق.')
        self.assertEqual(spoken('روح\nلا تقلق.','Soul',terms),'روح\nلا تقلق.')

    def test_one_cue_spanning_two_reference_lines_keeps_both(self):
        groups,_=passages([{'start':0,'end':6}],[{'start':0,'end':3},{'start':3,'end':6}])
        self.assertEqual(groups,[([0],[0,1])])
    def test_two_cues_under_one_reference_line_join(self):
        groups,_=passages([{'start':.5,'end':2},{'start':2,'end':4.5}],[{'start':0,'end':5}])
        self.assertEqual(groups,[([0,1],[0])])
    def test_passage_cut_by_sample_edge_is_excluded_and_reported(self):
        # Cue 1 (5-10 s) is sampled, but its reference (0-10 s) also covers cue 0, which is not.
        cues=[{'start':0,'end':5},{'start':5,'end':10},{'start':12,'end':14}]
        ref=[{'start':0,'end':10},{'start':12,'end':14}]
        complete,boundary,_,_=sample_passages(cues,ref,1,2)
        self.assertEqual(complete,[([2],[1])]);self.assertEqual(boundary,[([0,1],[0])])
    def test_unmatched_cues_and_reference_lines_are_reported(self):
        cues=[{'start':0,'end':2},{'start':10,'end':11},{'start':20,'end':22}]
        ref=[{'start':0,'end':2},{'start':5,'end':6},{'start':20,'end':22},{'start':50,'end':51}]
        complete,boundary,lost_cues,lost_refs=sample_passages(cues,ref,0,3)
        self.assertEqual(complete,[([0],[0]),([2],[2])]);self.assertEqual(boundary,[])
        self.assertEqual(lost_cues,[1]);self.assertEqual(lost_refs,[1])

    def test_bad_reference_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            empty=Path(d)/'empty.srt';empty.write_text('',encoding='utf-8')
            bad=Path(d)/'bad.srt';bad.write_text('1\n00:00:01 --> 00:00:02\nhi\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'no subtitle'):parse_srt(empty)
            with self.assertRaisesRegex(ValueError,'malformed'):parse_srt(bad)

if __name__=='__main__':unittest.main()
