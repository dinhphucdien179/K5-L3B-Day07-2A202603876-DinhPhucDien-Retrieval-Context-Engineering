"""Read-only adapter for the bundled Day06 store and pinned embedder."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

from .retrieval import check_request

ROOT = Path(__file__).resolve().parents[2]
DAY06 = ROOT / 'Day06/K5-L3B-Day06-2A202603876-DataIngestionEngineering'
_RUNTIME = None


def load_core():
    # Use an explicit package alias so Day06's `src` cannot shadow Day07 code.
    name = '_day06_core'
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, DAY06 / 'starter/src/__init__.py',
                                                    submodule_search_locations=[str(DAY06 / 'starter/src')])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)


def chunk_record(row):
    cid, text, document_id, source, page, metadata = row
    return {'id': cid, 'text': text, 'source_id': document_id, 'source': source,
            'page': int(page) if str(page).isdigit() else page, 'metadata': metadata}


def configure_runtime(settings):
    """Apply budgets before pgvector (which imports NumPy) or model libraries."""
    global _RUNTIME
    load_core()
    from _day06_core.runtime import RuntimeConfig
    runtime = RuntimeConfig(**settings)
    if _RUNTIME is None:
        runtime.apply_threads()
        _RUNTIME = runtime
    elif _RUNTIME != runtime:
        raise RuntimeError('Runtime settings changed; start a fresh CLI process')
    return _RUNTIME


class Day06Store:
    def __init__(self, database_url, strategy='A', offline=True):
        if strategy not in ('A', 'B'):
            raise ValueError('Choose physical index A or B')
        self.strategy, self.offline = strategy, offline
        self.config = json.loads((DAY06 / 'starter/config/pipeline.json').read_text())
        self.runtime = configure_runtime(self.config['runtime'])
        import psycopg
        self.connection = psycopg.connect(database_url, autocommit=True, connect_timeout=5)
        self.model = None
        try:
            self.connection.execute('SET default_transaction_read_only = on')
            self.connection.execute("SET statement_timeout = '60s'")
            from pgvector.psycopg import register_vector
            register_vector(self.connection)
            record = self.connection.execute('SELECT identity, chunk_count FROM day6_indexes WHERE strategy=%s', [strategy]).fetchone()
            if not record:
                raise ValueError('Day06 index missing; run Day06 ingest first')
            self.identity, self.count = record
            checksum = hashlib.sha256((DAY06 / self.config['corpus']).read_bytes()).hexdigest()
            if self.identity['corpus_sha256'] != checksum or self.identity['embedding'] != self.config['embedding'] or self.identity['chunking'] != self.config['chunking']:
                raise ValueError('Day06 corpus/model/chunking differs from the stored index')
            if self.identity['resolved_embedding']['dimensions'] != 384:
                raise ValueError('Unexpected Day06 vector dimensions')
            self.chunks = [chunk_record(row) for row in self.connection.execute(
                'SELECT chunk_id,content,document_id,source,page,metadata FROM day6_chunks WHERE strategy=%s ORDER BY chunk_id', [strategy]).fetchall()]
            if len(self.chunks) != self.count:
                raise ValueError('Day06 stored chunk count does not match index metadata')
        except Exception:
            self.connection.close()
            raise

    def _embedder(self):
        if self.model is None:
            if self.offline:
                os.environ['HF_HUB_OFFLINE'] = '1'
            load_core()
            from _day06_core.embeddings import MyEmbedder
            model = MyEmbedder(**self.config['embedding'], runtime=self.runtime, cache=DAY06 / self.config['cache'])
            if model.identity != self.identity['resolved_embedding']:
                raise ValueError('Query embedding identity differs from Day06; use the same dependency versions and settings')
            self.model = model
        return self.model

    def search(self, query, *, top_k=3, filters=None):
        filters = {} if filters is None else filters
        check_request(query, top_k, filters)
        from psycopg.types.json import Jsonb
        vector = self._embedder().embed_query(query)
        rows = self.connection.execute('''SELECT chunk_id,content,document_id,source,page,metadata,
            1-(embedding <=> %s) FROM day6_chunks WHERE strategy=%s AND metadata @> %s
            ORDER BY embedding <=> %s,chunk_id LIMIT %s''',
            [vector, self.strategy, Jsonb(filters), vector, top_k]).fetchall()
        return [{**chunk_record(row[:6]), 'score': float(row[6]), 'rank': i, 'method': 'dense'}
                for i, row in enumerate(rows, 1)]

    def close(self):
        self.connection.close()
