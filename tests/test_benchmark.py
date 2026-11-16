from pathlib import Path
import sys
import unittest
import tempfile
import json
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from day07.benchmark import context_hit, evidence_hit, fraction, load_cases
from day07.benchmark import run_benchmark


def row(start, end, text, page=1):
    return {'source_id': 'doc', 'page': page, 'text': text,
            'metadata': {'char_start': start, 'char_end': end}}


class BenchmarkTests(unittest.TestCase):
    def test_split_evidence_restored_by_contiguous_context_not_by_ranking_hit(self):
        gold = [{'source_id': 'doc', 'page': 1, 'evidence': 'income growth of the bottom forty percent'}]
        rows = [row(0, 20, 'income growth of the'), row(17, 40, 'the bottom forty percent')]
        # Use precise offsets from the same original source, including overlap.
        text = gold[0]['evidence']
        rows = [row(0, 20, text[:20]), row(17, len(text), text[17:])]
        self.assertFalse(evidence_hit(rows, gold))
        self.assertTrue(context_hit(rows, gold))
        self.assertFalse(context_hit([rows[0], {**rows[1], 'page': 2}], gold))

    def test_unseen_gap_is_not_silently_filled(self):
        gold = [{'source_id': 'doc', 'page': 1, 'evidence': 'alpha MISSING omega'}]
        self.assertFalse(context_hit([row(0, 6, 'alpha '), row(14, 19, 'omega')], gold))
        self.assertEqual(fraction([True, False, None]), {'n': 1, 'N': 2, 'rate': 0.5})

    def test_frozen_splits_meet_required_counts_and_offsets(self):
        for split, expected in [('dev', (15, 2)), ('test', (5, 2))]:
            cases = load_cases(split)
            self.assertEqual((sum(c['answerable'] for c in cases), sum(not c['answerable'] for c in cases)), expected)

    def test_resume_preserves_saved_cases_without_duplicate_searches(self):
        chunk = {'id': 'a', 'source_id': 'doc', 'source': 'doc.pdf', 'page': 1,
                 'text': 'alpha', 'metadata': {'char_start': 0, 'char_end': 5}}
        cases = [{'id': 'd1', 'question': 'alpha', 'split': 'dev', 'answerable': True,
                  'gold': [{'source_id': 'doc', 'page': 1, 'evidence': 'alpha'}]}]
        class Store:
            strategy = 'A'
            identity = {'corpus_sha256': 'fixture'}
            chunks = [chunk]
            calls = 0
            def search(self, query, **kwargs): self.calls += 1; return self.chunks
        store = Store()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / 'trials.json'
            config.write_text(json.dumps({'selection_rule': 'fixture', 'trials': [
                {'name': 'dense_baseline', 'method': 'dense', 'index': 'A', 'top_k': 3,
                 'budget': 100, 'max_searches': 1, 'neighbors': 0}]}))
            with patch('day07.benchmark.load_cases', return_value=cases), patch('builtins.print'):
                result = run_benchmark(store, trials_path=config, output=root/'out', workers=2)
                before = (root/'out/dense_baseline/traces.json').read_bytes()
                resumed = run_benchmark(store, trials_path=config, output=root/'out', workers=2, resume=True)
            self.assertEqual(store.calls, 1)
            self.assertEqual(before, (root/'out/dense_baseline/traces.json').read_bytes())
            self.assertEqual(result['summary'], resumed['summary'])


if __name__ == '__main__': unittest.main()
