"""Generated fixtures test provenance and frozen-input failure modes, never retrieval scores."""
import hashlib
import json
from pathlib import Path

import pytest

from src.ingestion import NORMALIZATION_VERSION, OpenStaxHTML, normalize_text
from src.openstax import public_state, verify_source
from src.run import SELECTION_RULE, sha256, validate


def test_code_block_indentation_quotes_and_operators_survive():
    parser = OpenStaxHTML()
    parser.feed('<div data-type="page"><p>' + 'Original instructional prose. ' * 12 +
                '</p><pre><code>if x &lt; 3:\n    print("value", x)\n</code></pre></div>')
    text = parser.text()
    assert '```\nif x < 3:\n    print("value", x)\n```' in text
    assert normalize_text(text) == text


def test_page_state_is_parsed_without_executing_javascript_and_detects_drift():
    state = {'content': {'book': {'id': 'book-fixture', 'contentVersion': 'v1'},
                         'page': {'id': 'page-fixture'}}}
    raw = '<script>window.__PRELOADED_STATE__ = ' + json.dumps(state) + '; throw new Error("never execute");</script>'
    assert public_state(raw)['page']['id'] == 'page-fixture'
    source = dict(book_id='book-fixture', book_content_version='v1', page_id='page-fixture')
    verify_source(raw, source)
    with pytest.raises(ValueError, match='version changed'):
        verify_source(raw, {**source, 'book_content_version': 'v2'})
    with pytest.raises(ValueError, match='TOC page ID'):
        verify_source(raw, {**source, 'page_id': 'wrong-page'})


@pytest.fixture
def frozen_fixture(tmp_path, monkeypatch):
    # These are generated inputs, not the actual OpenStax corpus or its benchmark.
    import src.run as run
    monkeypatch.setattr(run, 'resolve', lambda value: tmp_path / value)
    pages = [dict(document_id='generated-fixture', source='https://example.org', page=f'u{i}',
                  text=f'Evidence {i}. ' + 'Generated text only. ' * 100,
                  metadata={'chapter': str(i % 2)}) for i in range(30)]
    questions = [dict(id=f'q{i}', split='dev' if i < 15 else 'test', question=f'Fixture question {i}?',
                      expected_answer=str(i), gold_source_id='generated-fixture', gold_page=f'u{i}',
                      evidence_quote=f'Evidence {i}.', evidence_start=0, evidence_end=len(f'Evidence {i}.'))
                 for i in range(20)]
    for index in (0, 1, 15):
        questions[index].update(filter={'chapter': str(index % 2)}, filter_context='Preset test context')
    corpus, benchmark, manifest, frozen = [tmp_path / name for name in ('pages.jsonl','questions.json','manifest.json','freeze.json')]
    corpus.write_text(''.join(json.dumps(p)+'\n' for p in pages))
    benchmark.write_text(json.dumps(questions))
    manifest.write_text(json.dumps({'corpus_sha256': sha256(corpus), 'normalization_version': NORMALIZATION_VERSION}))
    coherence = tmp_path / 'benchmark/coherence_positions.json'
    coherence.parent.mkdir()
    coherence.write_text('{"generated_fixture":true}')
    frozen.write_text(json.dumps({'corpus_sha256': sha256(corpus), 'benchmark_sha256': sha256(benchmark),
                                 'manifest_sha256': sha256(manifest), 'coherence_positions_sha256': sha256(coherence),
                                 'normalization_version': NORMALIZATION_VERSION, 'selection_rule': SELECTION_RULE}))
    config = dict(corpus='pages.jsonl', benchmark='questions.json', manifest='manifest.json', freeze='freeze.json',
                  selection_rule=SELECTION_RULE)
    return config, questions, benchmark


def test_frozen_benchmark_rejects_edits(frozen_fixture):
    config, questions, path = frozen_fixture
    assert validate(config)['source_units'] == 30
    questions[0]['question'] = 'Changed after freeze'
    path.write_text(json.dumps(questions))
    with pytest.raises(ValueError, match='Frozen corpus/benchmark'):
        validate(config)


def test_wrong_offsets_are_rejected_even_when_quote_occurs(frozen_fixture):
    config, questions, path = frozen_fixture
    questions[0]['evidence_start'] = 1
    path.write_text(json.dumps(questions))
    config = {key: value for key, value in config.items() if key != 'freeze'}
    with pytest.raises(ValueError, match='offsets'):
        validate(config)
