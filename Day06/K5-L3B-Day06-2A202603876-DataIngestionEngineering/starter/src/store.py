"""Transactional pgvector snapshots; B/C share storage, exact cosine search."""
from __future__ import annotations
from contextlib import contextmanager
from typing import Any
from .models import Chunk


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int, identity: dict | None = None):
        if type(dimensions) is not int or not 0 < dimensions <= 16000:
            raise ValueError('Invalid embedding dimensions')
        self.dimensions, self.identity = dimensions, identity or {}
        import psycopg
        self.connection = psycopg.connect(database_url, autocommit=True, connect_timeout=5)
        self.connection.execute("SET statement_timeout = '60s'")
        self.connection.execute("SET lock_timeout = '5s'")

    @staticmethod
    def physical(strategy):
        if strategy not in {'A', 'B', 'C'}:
            raise ValueError('Unknown strategy')
        return 'B' if strategy == 'C' else strategy

    def create_schema(self):
        from psycopg import sql
        from pgvector.psycopg import register_vector
        self.connection.execute('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public')
        self.connection.execute(sql.SQL('''CREATE TABLE IF NOT EXISTS day6_chunks (
            strategy text NOT NULL, chunk_id text NOT NULL,
            document_id text NOT NULL, source text NOT NULL, page text NOT NULL,
            content text NOT NULL, metadata jsonb NOT NULL,
            embedding vector({}), PRIMARY KEY (strategy, chunk_id))''').format(sql.Literal(self.dimensions)))
        self.connection.execute('''CREATE TABLE IF NOT EXISTS day6_indexes (
            strategy text PRIMARY KEY, identity jsonb NOT NULL, chunk_count bigint NOT NULL)''')
        stored_type = self.connection.execute("""SELECT format_type(atttypid, atttypmod)
            FROM pg_attribute WHERE attrelid='day6_chunks'::regclass AND attname='embedding'""").fetchone()[0]
        if stored_type != f'vector({self.dimensions})':
            raise RuntimeError('Stored schema has different dimensions; use a separate database or explicit migration')
        register_vector(self.connection)

    def _validate_vectors(self, vectors, count):
        import numpy as np
        if not isinstance(vectors, np.ndarray) or vectors.dtype != np.float32 or vectors.shape != (count, self.dimensions):
            raise ValueError('Expected a float32 matrix matching chunks and dimensions')
        if not np.isfinite(vectors).all() or not np.all(np.any(vectors != 0, axis=1)):
            raise ValueError('Invalid embedding values')

    def replace_batches(self, strategy, batches) -> int:
        """Replace a complete strategy in ONE transaction; rollback preserves old rows.

        Consume only one embedding batch at a time. Row views are serialized by the
        DB adapter at the storage boundary; this boundary is not zero-copy.
        """
        from psycopg.types.json import Jsonb
        if strategy not in {'A', 'B'}:
            raise ValueError('Only A/B are stored; C reuses B')
        count = 0
        with self.connection.transaction():
            self.connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ['day6:' + strategy])
            self.connection.execute('DELETE FROM day6_chunks WHERE strategy=%s', [strategy])
            for chunks, vectors in batches:
                self._validate_vectors(vectors, len(chunks))
                with self.connection.cursor().copy('''COPY day6_chunks
                    (strategy,chunk_id,document_id,source,page,content,metadata,embedding) FROM STDIN''') as copy:
                    for chunk, vector in zip(chunks, vectors):
                        metadata = {**chunk.metadata, 'document_id': chunk.document_id,
                                    'source': chunk.source, 'page': chunk.page}
                        copy.write_row((strategy, chunk.chunk_id, chunk.document_id, chunk.source,
                                        str(chunk.page), chunk.text, Jsonb(metadata), vector))
                count += len(chunks)
            if count == 0:
                raise ValueError('Refusing to publish an empty index')
            self.connection.execute('''INSERT INTO day6_indexes VALUES (%s,%s,%s)
                ON CONFLICT (strategy) DO UPDATE SET identity=excluded.identity, chunk_count=excluded.chunk_count''',
                [strategy, Jsonb(self.identity), count])
        return count

    def upsert(self, strategy: str, chunks: list[Chunk], vectors):
        """Compatibility entry: chunks are the COMPLETE replacement, not a partial batch."""
        return self.replace_batches(strategy, [(chunks, vectors)])

    @contextmanager
    def read_snapshot(self):
        with self.connection.transaction():
            self.connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            yield

    def check_identity(self, strategy):
        record = self.connection.execute('SELECT identity FROM day6_indexes WHERE strategy=%s',
                                         [self.physical(strategy)]).fetchone()
        if not record or record[0] != self.identity:
            raise RuntimeError('Index missing or model/corpus/config fingerprint differs; ingest first')

    def search(self, strategy: str, query_vector, top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        import numpy as np
        from psycopg.types.json import Jsonb
        query = np.asarray(query_vector, dtype=np.float32)
        self._validate_vectors(query.reshape(1, -1), 1)
        if not 1 <= top_k <= 100:
            raise ValueError('Invalid top_k')
        filters = filters or {}
        allowed = {'chapter', 'section', 'year', 'version', 'category', 'audience', 'language', 'document_type'}
        if set(filters) - allowed or any(type(v) not in {str, int, bool} for v in filters.values()):
            raise ValueError('Filter must contain allowed metadata and scalar values; gold source/page forbidden')
        rows = self.connection.execute('''SELECT chunk_id, content, metadata, 1-(embedding <=> %s) AS score
            FROM day6_chunks WHERE strategy=%s AND metadata @> %s
            ORDER BY embedding <=> %s, chunk_id LIMIT %s''',
            [query, self.physical(strategy), Jsonb(filters), query, top_k]).fetchall()
        return [{'chunk_id': cid, 'text': text, 'metadata': metadata, 'score': float(score)}
                for cid, text, metadata, score in rows]

    def close(self):
        self.connection.close()
