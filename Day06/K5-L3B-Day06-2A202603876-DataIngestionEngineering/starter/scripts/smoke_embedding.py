"""Real model / optional pgvector smoke on authored text, never the lab corpus."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from src.runtime import RuntimeConfig, Telemetry, atomic_json, exclusive_run, require_python

ROOT = Path(__file__).resolve().parents[2]
TEXTS = [
    'A durable database preserves committed records after restarting the application.',
    'A gardener waters tomato plants when the soil becomes dry.',
    'A database transaction rolls back all its changes if a write fails.',
]


def database_smoke(model, vectors):
    """Only a dedicated test database; isolate and remove application tables."""
    import numpy as np
    from psycopg import sql
    from src.models import Chunk
    from src.store import PgVectorStore

    url = os.environ['DAY6_TEST_DATABASE_URL']
    schema = 'day6_smoke_' + uuid.uuid4().hex
    store = PgVectorStore(url, model.dimensions, model.identity)
    created = False
    try:
        store.connection.execute('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public')
        store.connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        created = True
        store.connection.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(schema)))
        store.create_schema()
        chunks = [Chunk(f'authored-{i}', 'authored-smoke', 'urn:day6:authored-smoke', i,
                        text, {'category': 'garden' if i == 1 else 'database'})
                  for i, text in enumerate(TEXTS)]
        store.upsert('B', chunks, vectors)
        store.upsert('B', chunks, vectors)
        assert store.connection.execute('SELECT count(*) FROM day6_chunks').fetchone()[0] == len(TEXTS)
        query = model.embed_query(TEXTS[0])
        expected = (vectors @ query) / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(query))
        with store.read_snapshot():
            store.check_identity('C')
            hits = store.search('B', query)
            filtered = store.search('C', query, filters={'category': 'garden'})
        expected_order = sorted(range(len(TEXTS)), key=lambda i: (-float(expected[i]), f'authored-{i}'))
        assert [h['chunk_id'] for h in hits] == [f'authored-{i}' for i in expected_order]
        assert all(abs(h['score'] - float(expected[int(h['chunk_id'].split('-')[1])])) < 1e-5 for h in hits)
        assert [h['chunk_id'] for h in filtered] == ['authored-1']
        # Verify persistence through an independent connection, not just a local object.
        check = PgVectorStore(url, model.dimensions, model.identity)
        try:
            check.connection.execute(sql.SQL('SET search_path TO {}, public').format(sql.Identifier(schema)))
            check.create_schema()
            check.check_identity('B')
            assert check.search('B', query)[0]['chunk_id'] == hits[0]['chunk_id']
            versions = check.connection.execute("SELECT current_setting('server_version'), extversion FROM pg_extension WHERE extname='vector'").fetchone()
        finally:
            check.close()
        return {'status': 'passed', 'postgresql': versions[0], 'pgvector': versions[1],
                'rows': len(TEXTS), 'cosine_tolerance': 1e-5, 'persistence_reconnect': True,
                'filter_and_B_C_alias': True, 'duplicate_reingest': False,
                'hits': hits, 'filtered_hits': filtered}
    finally:
        if created:
            store.connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', action='store_true', help='Requires DAY6_TEST_DATABASE_URL')
    parser.add_argument('--offline', action='store_true', help='Require an already downloaded model')
    args = parser.parse_args()
    require_python()
    from dotenv import load_dotenv
    load_dotenv(ROOT / 'starter/.env')
    if args.database and not os.getenv('DAY6_TEST_DATABASE_URL'):
        parser.error('Set DAY6_TEST_DATABASE_URL to a dedicated test DB')
    if args.offline:
        os.environ['HF_HUB_OFFLINE'] = '1'
    config = json.loads((ROOT / 'starter/config/pipeline.json').read_text())
    runtime = RuntimeConfig(**config['runtime'])
    hardware = runtime.apply_threads()
    output = ROOT / 'results' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-model-smoke')
    cache = ROOT / config['cache']
    with exclusive_run(cache / 'pipeline.lock'):
        telemetry = Telemetry(output / 'telemetry.jsonl', runtime)
        atomic_json(output / 'run.json', {'command': 'model-smoke', 'input': 'three authored sentences; no OpenStax content',
                                         'hardware': hardware, 'database_requested': args.database, 'offline': args.offline})
        try:
            from src.embeddings import MyEmbedder
            import numpy as np
            with telemetry.stage('model-load'):
                model = MyEmbedder(**config['embedding'], runtime=runtime, cache=cache)
            with telemetry.stage('authored-embedding'):
                vectors = model.embed_documents(TEXTS)
                assert vectors.shape == (len(TEXTS), model.dimensions) and vectors.dtype == np.float32
                assert np.isfinite(vectors).all()
                assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
                repeated = model.embed_documents(TEXTS)
                assert np.array_equal(vectors, repeated)
                # Both public entry points must reject, never truncate, oversized input.
                for encode in (lambda t: model.embed_documents([t]), model.embed_query):
                    try:
                        encode('database ' * (model.model.max_seq_length + 10))
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('Token overflow was silently accepted')
            with telemetry.stage('database-roundtrip'):
                db = database_smoke(model, vectors) if args.database else {'status': 'not_requested'}
            atomic_json(output / 'result.json', {'status': 'passed', 'kind': 'infrastructure smoke, not corpus benchmark',
                        'model': model.identity, 'shape': list(vectors.shape), 'dtype': str(vectors.dtype),
                        'finite_unit_vectors': True, 'truncation_rejected': True,
                        'cache_hits': model.cached.hits, 'cache_misses': model.cached.misses, 'database': db})
            print(json.dumps({'artifacts': str(output.relative_to(ROOT)), 'status': 'passed'}))
        except BaseException as exc:
            atomic_json(output / 'result.json', {'status': 'failed', 'error_type': type(exc).__name__})
            raise
        finally:
            telemetry.close()


if __name__ == '__main__':
    main()
