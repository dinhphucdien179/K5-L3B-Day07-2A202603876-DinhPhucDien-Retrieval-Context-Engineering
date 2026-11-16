"""Expand retrieved seeds using same-page neighbors; never accept benchmark gold."""
from collections import defaultdict


class NeighborContext:
    def __init__(self, chunks, radius=0):
        if type(radius) is not int or not 0 <= radius <= 3:
            raise ValueError('Neighbor radius must be 0..3')
        self.radius = radius
        self.groups = defaultdict(list)
        self.positions = {}
        for row in chunks:
            self.groups[(row['source_id'], str(row['page']))].append(row)
        for key, rows in self.groups.items():
            if radius and any(type(r['metadata'].get('char_start')) is not int or type(r['metadata'].get('char_end')) is not int for r in rows):
                raise ValueError('Neighbor context requires source character offsets')
            rows.sort(key=lambda r: (r['metadata'].get('char_start', 0), r['id']))
            for i, row in enumerate(rows):
                self.positions[row['id']] = key, i

    def expand(self, seeds, filters=None):
        if not self.radius:
            return seeds
        filters = filters or {}
        expanded, seen = [], set()
        for seed in seeds:
            key, position = self.positions[seed['id']]
            rows = self.groups[key]
            for row in rows[max(0, position-self.radius):position+self.radius+1]:
                if row['id'] in seen or any(type(row['metadata'].get(k)) is not type(v) or row['metadata'].get(k) != v for k, v in filters.items()):
                    continue
                seen.add(row['id'])
                expanded.append({**row, 'context_seed_id': seed['id'],
                                 'context_role': 'seed' if row['id'] == seed['id'] else 'neighbor'})
        return expanded
