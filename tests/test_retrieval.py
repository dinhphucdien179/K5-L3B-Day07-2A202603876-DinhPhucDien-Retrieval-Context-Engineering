"""Offline algorithm checks; these do not measure real model quality."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from day07.retrieval import BM25, Hybrid


def chunk(cid, text, chapter='1'):
    return {'id': cid, 'text': text, 'source_id': 'doc', 'source': 'doc.pdf',
            'page': 1, 'metadata': {'chapter': chapter}}


class RetrievalTests(unittest.TestCase):
    def test_bm25_filters_before_cutoff_and_empty_overlap(self):
        index = BM25([chunk('a', 'poverty insurance insurance'), chunk('b', 'insurance coverage', '2')])
        self.assertEqual([h['id'] for h in index.search('insurance', filters={'chapter': '2'}, top_k=1)], ['b'])
        self.assertEqual(index.search('nonexistent'), [])
        with self.assertRaises(ValueError):
            index.search('poverty', filters={'gold_page': 1})

    def test_rrf_merges_ranks_without_adding_raw_scores(self):
        class Ranked:
            def __init__(self, rows): self.rows = rows
            def search(self, query, *, top_k, filters): return self.rows[:top_k]
        a, b, c = chunk('a', 'one'), chunk('b', 'two'), chunk('c', 'three')
        dense = Ranked([{**a, 'score': 0.99}, {**b, 'score': 0.01}])
        lexical = Ranked([{**b, 'score': 1000}, {**c, 'score': 900}])
        hits = Hybrid(dense, lexical).search('query')
        self.assertEqual(hits[0]['id'], 'b')
        self.assertAlmostEqual(hits[0]['score'], 1/62 + 1/61)
        self.assertEqual(len({h['id'] for h in hits}), 3)


if __name__ == '__main__': unittest.main()
