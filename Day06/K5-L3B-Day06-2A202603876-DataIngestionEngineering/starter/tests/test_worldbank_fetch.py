"""Synthetic HTTP/PDF fixtures only; these tests are not corpus measurements."""
import hashlib
import json
from pathlib import Path

import pytest

from src.fetching import SnapshotFetcher
from src.ingestion import iter_selected_pdf_pages
from src.runtime import RuntimeConfig


class FixtureResponse:
    def __init__(self, body, content_type):
        self.body, self.headers = body, {'Content-Type': content_type}
        self.status_code, self.closed = 200, False

    def iter_content(self, chunk_size):
        for start in range(0, len(self.body), 31):
            yield self.body[start:start + 31]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


class FixtureSession:
    def __init__(self, responses):
        self.responses, self.headers, self.calls = iter(responses), {}, []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs, self.headers.copy()))
        return next(self.responses)

    def close(self):
        self.closed = True


def write_fixture_pdf(path, texts):
    """Create tiny, explicitly synthetic text pages without another PDF dependency."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
        NameObject('/BaseFont'): NameObject('/Helvetica')}))
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        content = DecodedStreamObject()
        escaped = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        content.set_data(f'BT /F1 10 Tf 72 720 Td ({escaped}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(content)
    writer.write(path)


def pdf_source(pages):
    return {'format': 'pdf', 'document_id': 'synthetic-pdf-only',
            'url': 'https://example.org/synthetic.pdf', 'title': 'Generated PDF fixture',
            'license_or_permission': 'Test fixture generated locally',
            'license_url': 'https://example.org/fixture-license',
            'metadata': {'language': 'en'}, 'pages': pages}


@pytest.mark.parametrize('declared,mime,body', [
    ('application/pdf', 'text/html', b'<html>access challenge</html>'),
    ('application/pdf', 'application/pdf', b'<html>not a PDF</html>'),
    ('application/json', 'application/json', b'{invalid json}'),
    ('application/json', 'application/json', b'{"nonstandard":NaN}'),
    ('text/plain', 'text/plain', b'not\x00plain text'),
])
def test_invalid_typed_response_never_publishes_checkpoint(tmp_path, declared, mime, body):
    response = FixtureResponse(body, mime)
    session = FixtureSession([response])
    with SnapshotFetcher(tmp_path, RuntimeConfig(), lambda: session) as fetcher:
        with pytest.raises(ValueError):
            fetcher.fetch('https://example.org/source', content_type=declared)
    assert response.closed and session.closed and len(session.calls) == 1
    assert not list(tmp_path.iterdir())


def test_type_isolated_cache_accept_headers_and_corruption_recovery(tmp_path):
    # Identical bytes are permitted as PDF/text but must never share type identities.
    body = b'%PDF-1.7 synthetic HTTP signature fixture only'
    session = FixtureSession([FixtureResponse(body, 'application/pdf'),
                              FixtureResponse(body, 'text/plain; charset=UTF-8'),
                              FixtureResponse(body + b' repaired', 'application/pdf')])
    with SnapshotFetcher(tmp_path, RuntimeConfig(), lambda: session) as fetcher:
        fetcher.pacer.wait = lambda _: None
        first = fetcher.fetch('https://example.org/source', content_type='application/pdf')
        plain = fetcher.fetch('https://example.org/source', content_type='text/plain')
        assert first['body_path'].endswith('.pdf') and plain['body_path'].endswith('.txt')
        assert Path(first['body_path']) != Path(plain['body_path'])
        assert fetcher.fetch('https://example.org/source', content_type='application/pdf')['cache_hit']
        Path(first['body_path']).write_bytes(b'corrupt')
        repaired = fetcher.fetch('https://example.org/source', content_type='application/pdf')
        assert not repaired['cache_hit'] and len(session.calls) == 3
    assert [call[2]['Accept'] for call in session.calls] == ['application/pdf', 'text/plain', 'application/pdf']


def test_malformed_cache_checkpoint_recovers_without_trusting_its_shape(tmp_path):
    body, url = b'{"documents":{}}', 'https://example.org/source'
    session = FixtureSession([FixtureResponse(body, 'application/json') for _ in range(3)])
    with SnapshotFetcher(tmp_path, RuntimeConfig(), lambda: session) as fetcher:
        fetcher.pacer.wait = lambda _: None
        fetcher.fetch(url, content_type='application/json')
        index = next(path for path in tmp_path.glob('*.json') if json.loads(path.read_text()).get('url') == url)
        for corrupted in ([], {'sha256': None}):
            index.write_text(json.dumps(corrupted))
            assert not fetcher.fetch(url, content_type='application/json')['cache_hit']
    assert len(session.calls) == 3


def test_public_worldbank_api_only_allows_explicit_json_and_public_query_parameters(tmp_path):
    endpoint = 'https://search.worldbank.org/api/v3/wds'
    session = FixtureSession([FixtureResponse(b'{"total":1,"documents":{}}', 'application/json')])
    with SnapshotFetcher(tmp_path, RuntimeConfig(), lambda: session) as fetcher:
        good = endpoint + '?format=json&rows=1&guid=099115004242216918'
        snapshot = fetcher.fetch(good, content_type='application/json')
        assert snapshot['content_type'] == 'application/json'
        assert fetcher.fetch(good, content_type='application/json')['cache_hit']
        invalid = [endpoint + '?format=json&token=secret', endpoint + '?format=json&rows=999999',
                   endpoint + '?format=json&rows=1&rows=2', endpoint + '?format=xml',
                   'https://example.org/api?format=json',
                   'https://search.worldbank.org/other?format=json',
                   'https://user:password@search.worldbank.org/api/v3/wds?format=json',
                   'https://@search.worldbank.org/api/v3/wds?format=json',
                   good + '#fragment']
        for url in invalid:
            with pytest.raises(ValueError):
                fetcher.fetch(url, content_type='application/json')
        with pytest.raises(ValueError):
            fetcher.fetch(good)  # A query must not become allowed for HTML by its hostname alone.
    assert len(session.calls) == 1


def test_selected_pdf_physical_order_metadata_and_normalized_offsets(tmp_path):
    path = tmp_path / 'fixture.pdf'
    write_fixture_pdf(path, ['Page one useful source paragraph. ' * 12, '',
                             'Page three separate source paragraph. ' * 12])
    source = pdf_source([{'page': 3, 'metadata': {'section': 'third'}},
                         {'page': 1, 'metadata': {'section': 'first'}}])
    guards = []
    pages = list(iter_selected_pdf_pages(path, source, guards.append))
    assert [page.page for page in pages] == [3, 1]
    assert [page.metadata['section'] for page in pages] == ['third', 'first']
    assert all(page.document_id == source['document_id'] and page.source == source['url']
               and page.metadata['language'] == 'en' for page in pages)
    assert len(guards) == 4  # Empty unselected page 2 was never extracted.
    from src.chunking import by_paragraph
    for page in pages:
        for chunk in by_paragraph(page, 100):
            assert chunk.text == page.text[chunk.metadata['char_start']:chunk.metadata['char_end']]
            assert chunk.page == page.page


def test_pdf_invalid_selection_and_empty_page_are_explicit_errors(tmp_path):
    path = tmp_path / 'fixture.pdf'
    write_fixture_pdf(path, ['A useful generated paragraph. ' * 12, ''])
    selections = [[], [{'page': 0, 'metadata': {}}], [{'page': True, 'metadata': {}}],
                  [{'page': 3, 'metadata': {}}], [{'page': 1, 'metadata': {}}] * 2,
                  [{'page': 2, 'metadata': {}}], [{'page': 1}]]
    for selected in selections:
        with pytest.raises(ValueError):
            list(iter_selected_pdf_pages(path, pdf_source(selected)))


def test_pdf_fetch_manifest_and_failure_preserve_existing_corpus(tmp_path, monkeypatch):
    from src.run import fetch_sources
    monkeypatch.setattr('src.run.ROOT', tmp_path)
    import requests
    path = tmp_path / 'fixture.pdf'
    write_fixture_pdf(path, ['First content paragraph for provenance. ' * 10, '',
                             'Third content paragraph for provenance. ' * 10])
    source = pdf_source([{'page': 1, 'metadata': {'section': 'first'}},
                         {'page': 3, 'metadata': {'section': 'third'}}])
    sources, corpus, output = tmp_path / 'data/sources.json', tmp_path / 'data/pages.jsonl', tmp_path / 'results'
    sources.parent.mkdir()
    sources.write_text(json.dumps([source]))
    session = FixtureSession([FixtureResponse(path.read_bytes(), 'application/pdf')])
    monkeypatch.setattr(requests, 'Session', lambda: session)
    config = {'sources': 'data/sources.json', 'corpus': 'data/pages.jsonl', 'cache': '.cache'}
    fetch_sources(config, RuntimeConfig(fetch_workers=1, max_inflight=1), output, False)
    original = corpus.read_bytes()
    records = [json.loads(line) for line in original.splitlines()]
    manifest = json.loads((output / 'fetch-manifest.json').read_text())
    assert [record['page'] for record in records] == [1, 3]
    assert [record['unit_id'] for record in manifest['sources']] == [1, 3]
    assert manifest['corpus_sha256'] == hashlib.sha256(original).hexdigest()
    assert all(not Path(record['body_path']).is_absolute()
               and (tmp_path / record['body_path']).is_file() for record in manifest['sources'])
    assert all(record['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
               and record['bytes'] == path.stat().st_size and record['normalized_characters'] >= 200
               and record['document_id'] == source['document_id'] for record in manifest['sources'])
    source['pages'].append({'page': 2, 'metadata': {'section': 'empty'}})
    sources.write_text(json.dumps([source]))
    with pytest.raises(ValueError, match='fewer than 200'):
        fetch_sources(config, RuntimeConfig(fetch_workers=1, max_inflight=1), output, False)
    assert corpus.read_bytes() == original
    assert json.loads((output / 'fetch-manifest.json').read_text()) == manifest
    assert not list(corpus.parent.glob('.pages.*'))


def test_pinned_raw_pdf_mismatch_cannot_replace_corpus(tmp_path, monkeypatch):
    from src.run import fetch_sources
    monkeypatch.setattr('src.run.ROOT', tmp_path)
    import requests
    path = tmp_path / 'fixture.pdf'
    write_fixture_pdf(path, ['Generated source changed after selection. ' * 10])
    source = pdf_source([{'page': 1, 'metadata': {'section': 'first'}}])
    source['expected_sha256'] = '0' * 64  # Deliberately mismatches this synthetic PDF.
    sources, corpus, output = tmp_path / 'data/sources.json', tmp_path / 'data/pages.jsonl', tmp_path / 'results'
    sources.parent.mkdir()
    sources.write_text(json.dumps([source]))
    corpus.write_bytes(b'previous validated corpus must survive')
    session = FixtureSession([FixtureResponse(path.read_bytes(), 'application/pdf')])
    monkeypatch.setattr(requests, 'Session', lambda: session)
    config = {'sources': 'data/sources.json', 'corpus': 'data/pages.jsonl', 'cache': '.cache'}
    with pytest.raises(ValueError, match='expected_sha256'):
        fetch_sources(config, RuntimeConfig(fetch_workers=1, max_inflight=1), output, False)
    assert corpus.read_bytes() == b'previous validated corpus must survive'
    assert not (output / 'fetch-manifest.json').exists()
    assert not list(corpus.parent.glob('.pages.*'))
