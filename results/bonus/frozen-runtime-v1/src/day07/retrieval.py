"""Comparable lexical/dense/hybrid rankings without benchmark labels."""
from collections import Counter
import math
import re
import unicodedata


def tokens(text):
    return re.findall(r'\w+', unicodedata.normalize('NFC', text).casefold())


def check_request(query, top_k, filters):
    if not isinstance(query, str) or not query.strip():
        raise ValueError('Query must be nonempty')
    if type(top_k) is not int or not 1 <= top_k <= 100:
        raise ValueError('top_k must be between 1 and 100')
    allowed = {'chapter', 'section', 'year', 'version', 'category', 'audience', 'language', 'document_type'}
    if not isinstance(filters, dict) or set(filters) - allowed or any(type(v) not in (str, int, bool) for v in filters.values()):
        raise ValueError('Filter must use permitted metadata and scalar values')


class BM25:
    def __init__(self, chunks, k1=1.5, b=0.75):
        if not chunks or len({c['id'] for c in chunks}) != len(chunks):
            raise ValueError('Corpus must contain unique chunks')
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError('Invalid BM25 parameters')
        self.chunks, self.k1, self.b = chunks, k1, b
        self.counts = [Counter(tokens(c['text'])) for c in chunks]
        self.lengths = [sum(row.values()) for row in self.counts]
        self.average = sum(self.lengths) / len(chunks) or 1
        df = Counter(term for row in self.counts for term in row)
        self.idf = {t: math.log(1 + (len(chunks) - n + 0.5)/(n + 0.5)) for t, n in df.items()}

    def search(self, query, *, top_k=3, filters=None):
        filters = {} if filters is None else filters
        check_request(query, top_k, filters)
        terms = set(tokens(query))
        hits = []
        for chunk, row, length in zip(self.chunks, self.counts, self.lengths):
            if any(type(chunk['metadata'].get(k)) is not type(v) or chunk['metadata'].get(k) != v for k, v in filters.items()):
                continue
            score = sum(self.idf.get(t, 0) * row[t] * (self.k1 + 1) /
                        (row[t] + self.k1 * (1 - self.b + self.b * length / self.average))
                        for t in terms if row[t])
            if score > 0:
                hits.append({**chunk, 'score': score, 'method': 'bm25'})
        return [{**hit, 'rank': i} for i, hit in enumerate(sorted(hits, key=lambda h: (-h['score'], h['id']))[:top_k], 1)]


class Hybrid:
    def __init__(self, dense, lexical, candidates=20, rrf_k=60):
        if type(candidates) is not int or not 1 <= candidates <= 100 or rrf_k <= 0:
            raise ValueError('Invalid hybrid parameters')
        self.dense, self.lexical = dense, lexical
        self.candidates, self.rrf_k = candidates, rrf_k

    def search(self, query, *, top_k=3, filters=None):
        filters = {} if filters is None else filters
        check_request(query, top_k, filters)
        count = max(self.candidates, top_k)
        merged = {}
        for name, retriever in [('dense', self.dense), ('bm25', self.lexical)]:
            results = retriever.search(query, top_k=count, filters=filters)
            for rank, row in enumerate(results, 1):
                hit = merged.setdefault(row['id'], {**row, 'score': 0.0, 'method': 'hybrid', 'components': {}})
                hit['score'] += 1 / (self.rrf_k + rank)
                hit['components'][name] = {'rank': rank, 'score': row['score']}
        ordered = sorted(merged.values(), key=lambda h: (-h['score'], h['id']))[:top_k]
        return [{**hit, 'rank': i} for i, hit in enumerate(ordered, 1)]
