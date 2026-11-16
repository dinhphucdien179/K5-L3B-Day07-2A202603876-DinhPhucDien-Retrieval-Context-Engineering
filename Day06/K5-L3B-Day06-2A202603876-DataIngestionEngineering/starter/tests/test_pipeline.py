"""Failure-oriented tests; generated fixtures are NOT lab corpus or benchmark results."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import numpy as np
import pytest

from src.chunking import by_paragraph, fixed_size
from src.embeddings import EmbeddingCache
from src.evaluation import evaluate_query
from src.fetching import OriginPacer, SnapshotFetcher, bounded_map, retry_delay
from src.ingestion import OpenStaxHTML, normalize_text
from src.models import DocumentPage
from src.runtime import RuntimeConfig, atomic_write, exclusive_run
from src.store import PgVectorStore


def test_explicit_unresolved_source_notice_blocks_model_work(tmp_path, monkeypatch):
    from src.run import require_processing_rights
    monkeypatch.setattr('src.run.ROOT', tmp_path)
    manifest = tmp_path / 'data/manifest.json'
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({'rights': {'ai_use_permission': 'not_established'}}))
    with pytest.raises(ValueError, match='not_established'):
        require_processing_rights({'manifest': str(manifest)})
    # A factual permission reference can be recorded without this engineering check
    # purporting to determine copyright law or requesting user approval.
    manifest.write_text(json.dumps({'rights': {'ai_use_permission': 'established',
                                              'basis': 'fixture reference, not actual OpenStax permission'}}))
    require_processing_rights({'manifest': str(manifest)})


def test_chunking_preserves_every_word_and_source_offsets():
    page = DocumentPage('doc', 'https://example.org/doc', 's1', normalize_text('Một ý đầy đủ.\n\n' + 'Đoạn dài hơn. ' * 80), {'chapter': 1})
    for chunks in (fixed_size(page, 130, 15), by_paragraph(page, 130)):
        assert chunks
        seen = set()
        for chunk in chunks:
            assert chunk.text == page.text[chunk.metadata['char_start']:chunk.metadata['char_end']]
            assert len(chunk.text) <= 130
            assert chunk.metadata['chapter'] == 1
            assert chunk.source == page.source and chunk.page == 's1'
            seen.update(range(chunk.metadata['char_start'], chunk.metadata['char_end']))
        assert all(index in seen for index, char in enumerate(page.text) if not char.isspace())
    assert by_paragraph(page, 130) == by_paragraph(page, 130)


def test_html_parser_keeps_paragraphs_and_excludes_ui():
    parser = OpenStaxHTML()
    parser.feed('<nav>outside</nav><div data-type="page"><h1>Heading</h1><p>' + 'Useful text. ' * 30 +
                '</p><div hidden>secret</div><script>bad()</script><p>Next paragraph.</p></div>')
    result = parser.text()
    assert 'Useful text.' in result and '\n\n' in result
    assert all(value not in result for value in ('outside', 'secret', 'bad()'))
    with pytest.raises(ValueError):
        parser = OpenStaxHTML()
        parser.feed('<h1>Challenge</h1>')
        parser.text()


def test_bounded_producer_stops_when_consumer_stops():
    submitted = []
    def items():
        for index in range(100):
            submitted.append(index)
            yield index
    iterator = bounded_map(lambda x: x, items(), workers=2, max_inflight=4)
    assert next(iterator) == 0
    time.sleep(0.02)
    assert len(submitted) == 4
    assert next(iterator) == 1
    assert len(submitted) == 5
    iterator.close()


def test_pacer_shares_cooldown_and_supports_sub_one_request_rate():
    now = [10.0]
    pacer = OriginPacer(0.5, clock=lambda: now[0], sleep=lambda t: now.__setitem__(0, now[0] + t))
    pacer.wait('a')
    pacer.wait('a')
    assert now[0] == 12
    pacer.cooldown('a', 8)
    pacer.wait('a')
    assert now[0] == 20
    pacer.wait('b')
    assert now[0] == 20
    assert retry_delay('2', 0) == 2
    with pytest.raises(RuntimeError):
        retry_delay('120', 0)


class Response:
    def __init__(self, status=200, body=b'<html>content</html>', headers=None):
        self.status_code, self.body = status, body
        self.headers = {'Content-Type': 'text/html', **(headers or {})}
        self.closed = False
    def iter_content(self, chunk_size):
        yield self.body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.closed = True


class Session:
    def __init__(self, responses):
        self.responses, self.headers, self.calls = iter(responses), {}, []
        self.closed = False
    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)
    def close(self):
        self.closed = True


def test_http_cache_revalidation_and_corruption(tmp_path):
    first = Response(headers={'ETag': 'v1'})
    session = Session([first, Response(304), Response(body=b'new content')])
    with SnapshotFetcher(tmp_path, RuntimeConfig(), lambda: session) as fetcher:
        fetcher.pacer.wait = lambda _: None
        a = fetcher.fetch('https://example.org/page')
        assert not a['cache_hit'] and first.closed
        assert fetcher.fetch('https://example.org/page')['cache_hit']
        assert len(session.calls) == 1
        assert fetcher.fetch('https://example.org/page', refresh=True)['revalidated']
        assert session.calls[-1]['headers']['If-None-Match'] == 'v1'
        Path(a['body_path']).write_bytes(b'corrupt')
        b = fetcher.fetch('https://example.org/page')
        assert not b['cache_hit'] and session.calls[-1]['headers'] == {}
    assert session.closed


def test_403_not_retried_and_oversize_body_closed(tmp_path):
    for response, config in [(Response(403), RuntimeConfig()), (Response(body=b'x'*50), RuntimeConfig(max_response_bytes=10))]:
        session = Session([response])
        with SnapshotFetcher(tmp_path, config, lambda: session) as fetcher:
            with pytest.raises((RuntimeError, ValueError)):
                fetcher.fetch('https://example.org/page')
        assert len(session.calls) == 1 and response.closed
        assert not list(tmp_path.glob('*.json'))


def test_retry_budget_and_shared_pacing(tmp_path):
    responses = [Response(429, headers={'Retry-After': '1'}), Response(500), Response()]
    session = Session(responses)
    with SnapshotFetcher(tmp_path, RuntimeConfig(), lambda: session) as fetcher:
        attempts, delays = [], []
        fetcher.pacer.wait = lambda origin: attempts.append(origin)
        fetcher.pacer.cooldown = lambda origin, delay: delays.append(delay)
        assert fetcher.fetch('https://example.org/page')['attempts'] == 3
    assert len(attempts) == 3 and len(delays) == 2 and all(r.closed for r in responses)


def test_embedding_cache_restarts_invalidates_and_never_uses_corrupt_values(tmp_path):
    calls = []
    def encode(texts, role):
        calls.append((texts, role))
        return np.ones((len(texts), 3), dtype=np.float32)
    identity = {'model': 'unit-test-only', 'revision': 'r1', 'dimensions': 3, 'normalize': True}
    cache = EmbeddingCache(tmp_path, identity, 4, encode)
    a = cache.embed(['same', 'same'], 'document')
    assert calls == [(['same'], 'document')] and a.flags.c_contiguous
    assert np.shares_memory(a[0], a)
    restarted = EmbeddingCache(tmp_path, identity, 4, encode)
    np.testing.assert_array_equal(restarted.embed(['same'], 'document'), a[:1])
    assert len(calls) == 1
    restarted.embed(['same'], 'query')
    EmbeddingCache(tmp_path, {**identity, 'revision': 'r2'}, 4, encode).embed(['same'], 'document')
    assert len(calls) == 3
    key = cache._key('same', 'document')
    (tmp_path / f'{key}.npy').write_bytes(b'interrupted')
    cache.embed(['same'], 'document')
    assert len(calls) == 4
    with pytest.raises(ValueError):
        cache.embed(['x']*5, 'document')


def test_embedding_provider_bad_values_are_not_cached(tmp_path):
    cache = EmbeddingCache(tmp_path, {'dimensions': 3}, 2,
                           lambda texts, role: np.full((len(texts), 3), np.nan, dtype=np.float32))
    with pytest.raises(ValueError):
        cache.embed(['x'], 'document')
    assert not list(tmp_path.glob('*.npy'))


def test_correct_document_alone_is_not_evidence_hit():
    q = dict(id='q', split='dev', question='?', expected_answer='condition', gold_source_id='d',
             gold_page='s1', evidence_quote='only under condition')
    metadata = dict(document_id='d', page='s1')
    assert not evaluate_query(q, [dict(text='unrelated', metadata=metadata)])['hit3']
    assert evaluate_query(q, [dict(text='only under\ncondition', metadata=metadata)])['hit1']
    assert PgVectorStore.physical('B') == PgVectorStore.physical('C')


def test_primary_and_alternative_evidence_both_accepted():
    q = dict(id='q', split='dev', question='?', expected_answer='answer', gold_source_id='d',
             gold_page='s1', evidence_quote='primary', gold_alternatives=[
                 dict(gold_source_id='d2', gold_page='s2', evidence_quote='alternative')])
    assert evaluate_query(q, [dict(text='primary', metadata=dict(document_id='d', page='s1'))])['hit1']
    assert evaluate_query(q, [dict(text='alternative', metadata=dict(document_id='d2', page='s2'))])['hit1']


def test_validate_generated_fixture_rejects_leakage_and_bad_evidence(tmp_path, monkeypatch):
    from src.run import validate, SELECTION_RULE
    monkeypatch.setattr('src.run.ROOT', tmp_path)
    pages = [dict(document_id='fixture-only', source='https://example.org/fixture', page=f'unit-{i}',
                  text=f'Evidence {i}. ' + 'Generated test paragraph. ' * 100,
                  metadata={'chapter': str(i % 2)}) for i in range(30)]
    questions = [dict(id=f'q{i}', split='dev' if i < 15 else 'test', question=f'Generated question {i}?',
                      expected_answer=str(i), gold_source_id='fixture-only', gold_page=f'unit-{i}',
                      evidence_quote=f'Evidence {i}.') for i in range(20)]
    for index in (0, 1, 15):
        questions[index].update(filter={'chapter': str(index % 2)}, filter_context='Chapter chosen by the test caller')
    corpus, benchmark = tmp_path / 'data/pages.jsonl', tmp_path / 'benchmark/questions.json'
    corpus.parent.mkdir()
    benchmark.parent.mkdir()
    corpus.write_text(''.join(json.dumps(page) + '\n' for page in pages))
    benchmark.write_text(json.dumps(questions))
    config = dict(corpus=str(corpus), benchmark=str(benchmark), selection_rule=SELECTION_RULE)
    assert validate(config)['splits'] == {'dev': 15, 'test': 5}
    questions[0]['filter'] = {'source': 'gold-leak'}
    benchmark.write_text(json.dumps(questions))
    with pytest.raises(ValueError, match='forbidden'):
        validate(config)
    questions[0]['filter'] = {'chapter': '0'}
    questions[2]['evidence_quote'] = 'invented evidence not in fixture'
    benchmark.write_text(json.dumps(questions))
    with pytest.raises(ValueError, match='Evidence'):
        validate(config)


def test_memory_budget_fails_at_boundary(monkeypatch):
    monkeypatch.setattr('src.runtime.memory_status', lambda: {'rss_bytes': 10*1024*1024, 'total_bytes': 100, 'available_bytes': 90})
    with pytest.raises(MemoryError, match='test-batch'):
        RuntimeConfig(rss_limit_mb=1).guard('test-batch')


def test_nested_cgroup_quotas_and_memory_headroom(monkeypatch):
    import src.runtime as runtime
    child, parent = Path('/synthetic-cgroup/child'), Path('/synthetic-cgroup')
    files = {
        '/proc/meminfo': 'MemTotal: 20000 kB\nMemAvailable: 10000 kB\n',
        '/proc/self/statm': '100 2 0 0 0 0 0',
        str(child / 'cpu.max'): '400000 100000', str(parent / 'cpu.max'): '200000 100000',
        str(child / 'memory.max'): '1000000', str(child / 'memory.current'): '100000',
        str(parent / 'memory.max'): '10000000', str(parent / 'memory.current'): '9500000',
    }
    monkeypatch.setattr(runtime, '_cgroups', lambda: iter((child, parent)))
    monkeypatch.setattr(Path, 'read_text', lambda path, **kwargs: files[str(path)])
    monkeypatch.setattr(runtime.os, 'sched_getaffinity', lambda _: set(range(8)))
    assert runtime.effective_cpus() == 2
    state = runtime.memory_status()
    assert state['total_bytes'] == 1000000 and state['available_bytes'] == 500000
    assert state['available_ratio'] == 0.05
    with pytest.raises(MemoryError):
        RuntimeConfig(min_available_ratio=0.1).guard('ancestor pressure')


def test_nonfinite_rate_is_rejected():
    with pytest.raises(ValueError):
        RuntimeConfig(requests_per_second=float('inf'))


def test_native_threads_are_set_without_a_conda_environment():
    import os
    script = "from src.runtime import RuntimeConfig; import os; RuntimeConfig(native_threads=2).apply_threads(); import numpy; assert os.environ['OMP_NUM_THREADS']=='2'; assert os.environ['OPENBLAS_NUM_THREADS']=='2'"
    environment = {key: value for key, value in os.environ.items() if not key.startswith('CONDA_')}
    subprocess.run([sys.executable, '-c', script], check=True, cwd=Path(__file__).parents[1], env=environment)


def test_atomic_publish_preserves_old_value_on_interruption(tmp_path, monkeypatch):
    path = tmp_path / 'checkpoint'
    atomic_write(path, b'old')
    def fail(*args):
        raise OSError('injected rename failure')
    monkeypatch.setattr('src.runtime.os.replace', fail)
    with pytest.raises(OSError):
        atomic_write(path, b'new')
    assert path.read_bytes() == b'old'
    assert list(tmp_path.iterdir()) == [path]


def test_process_lock_and_lab_path_guard(tmp_path, monkeypatch):
    import src.run as run
    monkeypatch.setattr(run, 'ROOT', tmp_path)
    lock = tmp_path / 'run.lock'
    with exclusive_run(lock):
        with pytest.raises(RuntimeError):
            with exclusive_run(lock):
                pass
    assert run.resolve('data/pages.jsonl') == tmp_path / 'data/pages.jsonl'
    for path in ('unrelated-project/data/file.jsonl', '../outside.json', '.'):
        with pytest.raises(ValueError, match='configured lab directory'):
            run.resolve(path)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/escape').symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(ValueError, match='configured lab directory'):
        run.resolve('data/escape/outside.json')
