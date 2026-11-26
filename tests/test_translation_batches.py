import unittest
from videotranslator.translation import batches,validate_batch

class TranslationBatchTests(unittest.TestCase):
    def test_batches_are_bounded_and_keep_all_ids(self):
        groups=list(batches([(i,{'original':'test'}) for i in range(25)]))
        self.assertEqual([len(g) for g in groups],[12,12,1])
        self.assertEqual([i for group in groups for i,c in group],list(range(25)))
    def test_reordered_response_attaches_to_ids(self):
        response={'translations':[{'id':i,'translation':str(i),'source_language':'en','uncertain':False} for i in [2,1]]}
        self.assertEqual(validate_batch(response,[1,2])[1]['translation'],'1')
    def test_missing_duplicate_unknown_and_empty_rejected(self):
        for ids in ([1],[1,1],[1,3]):
            with self.assertRaises(ValueError):validate_batch({'translations':[{'id':i,'translation':'x','source_language':'en','uncertain':False} for i in ids]},[1,2])
