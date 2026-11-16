from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from day07.context import NeighborContext
from day07.agent import pack_context


def row(cid, start, text, page=1, chapter='1'):
    return {'id': cid, 'source_id': 'doc', 'source': 'doc.pdf', 'page': page,
            'text': text, 'metadata': {'char_start': start, 'char_end': start+len(text), 'chapter': chapter}}


class ContextTests(unittest.TestCase):
    def test_neighbors_use_offsets_not_hash_order_and_stay_on_page(self):
        rows = [row('z', 0, 'The definition is'), row('a', 17, 'income growth'),
                row('c', 31, 'of the bottom forty percent.'), row('b', 0, 'Other page', page=2)]
        expanded = NeighborContext(rows, 1).expand([rows[1]])
        self.assertEqual([r['id'] for r in expanded], ['z', 'a', 'c'])
        self.assertTrue(all(r['page'] == 1 for r in expanded))

    def test_filter_dedup_and_budget_still_hold(self):
        rows = [row('a', 0, 'alpha'), row('b', 6, 'beta'), row('c', 11, 'gamma', chapter='2')]
        expanded = NeighborContext(rows, 1).expand([rows[0], rows[1]], {'chapter': '1'})
        self.assertEqual([r['id'] for r in expanded], ['a', 'b'])
        text, selected = pack_context(expanded, 40)
        self.assertLessEqual(len(text), 40)
        self.assertEqual(len({r['id'] for r in selected}), len(selected))


if __name__ == '__main__': unittest.main()
