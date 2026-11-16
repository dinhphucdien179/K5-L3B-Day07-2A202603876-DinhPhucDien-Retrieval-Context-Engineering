"""Synthetic PDF-page fixtures verify finalization; they are never retrieval results."""
from argparse import Namespace
import json

import pytest

from scripts.finalize_corpus import digest_text, finalize
from src.run import SELECTION_RULE, sha256


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def pdf_inputs(tmp_path, monkeypatch):
    import src.run as run
    monkeypatch.setattr(run, 'resolve', lambda value: tmp_path / value)
    pages, snapshots, questions = [], [], []
    for document, chapter in (('fixture-a', '1'), ('fixture-b', '2')):
        for physical_page in range(1, 16):
            marker = f'{document}-{physical_page:02}'
            quote = f'Verified synthetic evidence for {marker}.'
            text = quote + ' Generated fixture prose is used only to test source provenance and publication failures.' * 4
            source = f'https://example.org/{document}.pdf'
            metadata = {'chapter': chapter, 'printed_page': physical_page + 10}
            pages.append(dict(document_id=document, source=source, page=physical_page, text=text, metadata=metadata))
            snapshots.append(dict(source_id=document, document_id=document, title=f'Synthetic {document}',
                                  url=source, unit_id=physical_page, format='pdf',
                                  license_or_permission='Generated test fixture', license_url='https://example.org/license',
                                  sha256=digest_text(document), bytes=1234, fetched_at='2026-01-01T00:00:00Z',
                                  metadata=metadata))
            if document == 'fixture-a' or physical_page <= 5:
                index = len(questions)
                question = dict(id=f'q{index:02}', split='dev' if document == 'fixture-a' else 'test',
                                question=f'Which synthetic statement identifies {marker}?', expected_answer=marker,
                                document_id=document, unit=physical_page, evidence_quote=quote)
                if index in {0, 1, 15}:
                    question.update(filter={'chapter': chapter}, filter_context=f'Preset chapter {chapter} context')
                questions.append(question)
    corpus = tmp_path / 'data/pages.jsonl'
    corpus.parent.mkdir()
    corpus.write_text(''.join(json.dumps(p) + '\n' for p in pages), encoding='utf-8')
    write_json(tmp_path / 'results/fetch/fetch-manifest.json', {'corpus_sha256': sha256(corpus), 'sources': snapshots})
    write_json(tmp_path / 'benchmark/questions.authored.json', questions)
    spec = dict(title='Generated two-document PDF corpus',
                rights=dict(content_license_observed='Generated fixture', license_url='https://example.org/license',
                            ai_use_permission='established', basis='All text is an explicit generated test fixture.'),
                counting_rule='Thirty physical pages of generated fixture prose.',
                extraction_limits=['No real PDF is processed by this fixture.'],
                benchmark_split=dict(dev_chapters=['1'], test_chapters=['2'],
                                     split_method='Synthetic question groups use separate chapter metadata.',
                                     limitations=['Generated fixtures have no benchmark interpretation.']))
    write_json(tmp_path / 'data/corpus-spec.json', spec)
    config = dict(corpus='data/pages.jsonl', benchmark='benchmark/questions.json', manifest='data/manifest.json',
                  freeze='benchmark/freeze.json', cache='.cache/day6', selection_rule=SELECTION_RULE)
    args = Namespace(fetch_manifest='results/fetch/fetch-manifest.json', corpus_spec='data/corpus-spec.json',
                     amend_before_retrieval=False)
    return tmp_path, config, args, pages, questions


def active_artifacts(root):
    names = ('benchmark/questions.json', 'data/manifest.json', 'benchmark/freeze.json',
             'benchmark/coherence_positions.json', 'benchmark/evidence_audit.json')
    return {name: (root / name).read_bytes() for name in names if (root / name).exists()}


def test_pdf_pages_with_shared_numbers_keep_all_provenance(pdf_inputs):
    root, config, args, pages, questions = pdf_inputs
    questions[0]['alternative_evidence'] = [dict(document_id='fixture-b', unit=1,
                                                evidence_quote='Verified synthetic evidence for fixture-b-01.',
                                                verification_note='Explicit alternative only for the synthetic test.')]
    write_json(root / 'benchmark/questions.authored.json', questions)
    result = finalize(root, config, args)
    assert result['source_units'] == 30
    manifest = json.loads((root / config['manifest']).read_text())
    assert manifest['title'] == 'Generated two-document PDF corpus'
    assert manifest['rights']['ai_use_permission'] == 'established'
    assert {(u['document_id'], u['unit_id']) for u in manifest['units']} == {
        (p['document_id'], p['page']) for p in pages}
    assert all(type(u['unit_id']) is int and u['source_format'] == 'pdf' and 'raw_html_sha256' not in u
               for u in manifest['units'])
    prepared = json.loads((root / config['benchmark']).read_text())
    alternative = prepared[0]['gold_alternatives'][0]
    assert alternative['gold_source_id'] == 'fixture-b' and alternative['gold_page'] == 1
    assert alternative['gold_source_url'] == pages[15]['source']
    assert alternative['gold_text_sha256'] == digest_text(pages[15]['text'])
    start, end = alternative['evidence_start'], alternative['evidence_end']
    assert pages[15]['text'][start:end] == alternative['evidence_quote']
    frozen = json.loads((root / config['freeze']).read_text())
    assert frozen['corpus_spec_sha256'] == sha256(root / 'data/corpus-spec.json')
    assert frozen['authored_sha256'] == sha256(root / 'benchmark/questions.authored.json')
    assert frozen['dev_chapters'] == ['1'] and frozen['test_chapters'] == ['2']
    anchors = json.loads((root / 'benchmark/coherence_positions.json').read_text())
    assert len(anchors['positions']) == 10
    before = active_artifacts(root)
    finalize(root, config, args)
    assert active_artifacts(root) == before


def test_ambiguous_authored_page_is_rejected_without_publication(pdf_inputs):
    root, config, args, _, questions = pdf_inputs
    questions[0].pop('document_id')
    write_json(root / 'benchmark/questions.authored.json', questions)
    with pytest.raises(ValueError, match='ambiguous'):
        finalize(root, config, args)
    assert active_artifacts(root) == {}


def test_late_benchmark_validation_failure_preserves_active_outputs(pdf_inputs):
    root, config, args, _, questions = pdf_inputs
    # All evidence remains valid, but the final validator must reject only one filter question.
    for question in questions[1:]:
        question.pop('filter', None)
        question.pop('filter_context', None)
    write_json(root / 'benchmark/questions.authored.json', questions)
    write_json(root / config['benchmark'], [{'sentinel': 'existing benchmark'}])
    write_json(root / config['manifest'], {'sentinel': 'existing manifest'})
    before = active_artifacts(root)
    with pytest.raises(ValueError, match='filter questions'):
        finalize(root, config, args)
    assert active_artifacts(root) == before
    assert not (root / 'benchmark/freeze-history').exists()


def test_spec_change_requires_amendment_then_archives_previous_freeze(pdf_inputs):
    root, config, args, _, _ = pdf_inputs
    finalize(root, config, args)
    before = active_artifacts(root)
    old_hash = sha256(root / config['freeze'])
    spec_path = root / 'data/corpus-spec.json'
    spec = json.loads(spec_path.read_text())
    spec['title'] += ' revised before retrieval'
    write_json(spec_path, spec)
    with pytest.raises(ValueError, match='Frozen inputs changed'):
        finalize(root, config, args)
    assert active_artifacts(root) == before
    args.amend_before_retrieval = True
    finalize(root, config, args)
    frozen = json.loads((root / config['freeze']).read_text())
    assert frozen['previous_freeze_sha256'] == old_hash
    assert (root / f'benchmark/freeze-history/{old_hash}.json').read_bytes() == before['benchmark/freeze.json']


def test_started_retrieval_refuses_amendment_before_changing_any_artifact(pdf_inputs):
    root, config, args, _, questions = pdf_inputs
    finalize(root, config, args)
    before = active_artifacts(root)
    questions[0]['question'] += ' Revised?'
    write_json(root / 'benchmark/questions.authored.json', questions)
    # Explicit synthetic run marker tests refusal; this is not an experiment log.
    write_json(root / 'results/generated-run/run.json', {'command': 'ingest', 'generated_fixture': True})
    args.amend_before_retrieval = True
    with pytest.raises(ValueError, match='already started'):
        finalize(root, config, args)
    assert active_artifacts(root) == before
    assert not (root / 'benchmark/freeze-history').exists()
