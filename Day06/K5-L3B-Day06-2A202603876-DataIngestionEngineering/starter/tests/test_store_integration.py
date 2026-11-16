"""Real pgvector with synthetic 3D test-only vectors in an isolated test schema.

These vectors are fixtures, not semantic embeddings or lab benchmark results.
Requires a dedicated test DB opt-in.
"""
import os
import uuid
import numpy as np
import pytest
from src.models import Chunk
from src.store import PgVectorStore


@pytest.mark.integration
def test_real_pgvector_reingest_filter_and_rollback():
    url = os.getenv('DAY6_TEST_DATABASE_URL')
    if not url:
        pytest.skip('DAY6_TEST_DATABASE_URL is not configured; no live DB test performed')
    from psycopg import sql
    store = PgVectorStore(url, 3, {'test': True})
    store.connection.execute('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public')
    assert store.connection.execute("SELECT extnamespace::regnamespace::text FROM pg_extension WHERE extname='vector'").fetchone()[0] == 'public'
    schema = 'day6_test_' + uuid.uuid4().hex
    store.connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    store.connection.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(schema)))
    try:
        store.create_schema()
        chunks = [Chunk(str(i), 'doc', 'https://example.org', i, 'text', {'chapter': i}) for i in (1, 2)]
        vectors = np.array([[1,0,0], [0,1,0]], dtype=np.float32)
        store.upsert('B', chunks, vectors)
        store.upsert('B', chunks, vectors)
        assert store.connection.execute('SELECT count(*) FROM day6_chunks').fetchone()[0] == 2
        assert store.search('C', vectors[0], filters={'chapter': 2})[0]['metadata']['chapter'] == 2
        def broken():
            yield chunks[:1], vectors[:1]
            raise RuntimeError('injected failure between write batches')
        with pytest.raises(RuntimeError):
            store.replace_batches('B', broken())
        assert store.connection.execute('SELECT count(*) FROM day6_chunks').fetchone()[0] == 2
        store.upsert('B', chunks[:1], vectors[:1])
        assert [hit['chunk_id'] for hit in store.search('B', vectors[0])] == ['1']
        with store.read_snapshot():
            store.check_identity('C')
    finally:
        store.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        store.close()
