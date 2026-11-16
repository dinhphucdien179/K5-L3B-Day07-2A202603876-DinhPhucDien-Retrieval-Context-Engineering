"""Check native import ordering in a fresh Python process without a database."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Day06AdapterTests(unittest.TestCase):
    def test_runtime_precedes_database_numpy_and_is_reused(self):
        script = r'''
import hashlib, json, os, sys, types
from unittest.mock import patch
from day07 import day06
config = json.loads((day06.DAY06 / 'starter/config/pipeline.json').read_text())
identity = {'corpus_sha256': hashlib.sha256((day06.DAY06 / config['corpus']).read_bytes()).hexdigest(),
            'embedding': config['embedding'], 'chunking': config['chunking'],
            'resolved_embedding': {'dimensions': 384}}
class Result:
    def __init__(self, sql): self.sql = sql
    def fetchone(self): return identity, 1
    def fetchall(self): return [('c1', 'insurance', 'doc', 'doc.pdf', '1', {})]
class Connection:
    def execute(self, sql, params=None): return Result(sql)
    def close(self): pass
def connect(*args, **kwargs):
    assert os.environ['OMP_NUM_THREADS'] == str(config['runtime']['native_threads'])
    return Connection()
def register(connection):
    # Reproduce the native import performed by the actual pgvector adapter.
    sys.modules['numpy'] = types.ModuleType('numpy')
psycopg = types.ModuleType('psycopg')
psycopg.connect = connect
pgvector = types.ModuleType('pgvector')
pgvector.__path__ = []
adapter = types.ModuleType('pgvector.psycopg')
adapter.register_vector = register
sys.modules.update({'psycopg': psycopg, 'pgvector': pgvector, 'pgvector.psycopg': adapter})
store = day06.Day06Store('unused-test-dsn')
assert 'numpy' in sys.modules
assert day06.configure_runtime(config['runtime']) is store.runtime
# A lazy model load must reuse the configured runtime after NumPy was imported.
embedding = types.ModuleType('_day06_core.embeddings')
class Model:
    def __init__(self, **kwargs):
        assert kwargs['runtime'] is store.runtime
        self.identity = identity['resolved_embedding']
embedding.MyEmbedder = Model
sys.modules['_day06_core.embeddings'] = embedding
assert store._embedder() is store._embedder()
store.close()
print('runtime ordering verified')
'''
        # The subprocess has no previously imported numerical libraries.
        result = subprocess.run([sys.executable, '-c', "import sys; sys.path.insert(0, 'src');\n" + script],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('runtime ordering verified', result.stdout)


if __name__ == '__main__': unittest.main()
