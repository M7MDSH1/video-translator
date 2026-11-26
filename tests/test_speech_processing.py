import unittest
from videotranslator.speech import own_words,split_words

class SpeechProcessingTests(unittest.TestCase):
    def test_long_segment_splits_without_losing_words(self):
        words=[{'text':' word'+str(i),'start':i*.4,'end':i*.4+.35} for i in range(70)]
        cues=split_words(words,'en')
        self.assertGreater(len(cues),4)
        self.assertTrue(all(c['end']-c['start']<=6 and len(c['original'])<=84 for c in cues))
        self.assertEqual(sum(len(c['words']) for c in cues),70)
    def test_shifted_boundary_word_is_not_duplicated_or_lost(self):
        tail=[{'text':' enter','start':29.4,'end':29.8}]
        decoded=[{'text':' enter','start':29.6,'end':30.2},{'text':' the','start':30.2,'end':30.5},{'text':' tower','start':30.5,'end':31}]
        result=own_words(decoded,tail,30,60)
        self.assertEqual([w['text'] for w in result],[' the',' tower'])
    def test_word_crossing_boundary_is_retained_whole(self):
        words=[{'text':' crossing','start':29.7,'end':30.2},{'text':' next','start':30.3,'end':30.8}]
        first=own_words(words,[],0,30)
        second=own_words(words,first,30,60)
        self.assertEqual(len(first+second),2)
        self.assertEqual(first[0]['end'],30.2)
    def test_fast_speech_flagged(self):
        self.assertIn('reading speed',' '.join(split_words([{'text':'unusuallylongword','start':0,'end':.2}],'en')[0]['flags']))
