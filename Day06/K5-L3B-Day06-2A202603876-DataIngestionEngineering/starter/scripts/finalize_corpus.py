"""Verify source provenance and authored evidence before publishing frozen inputs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from src.ingestion import NORMALIZATION_VERSION, load_pages
from src.runtime import atomic_json, atomic_write, exclusive_run, lab_path, require_python
from src.run import sha256, validate

STARTER = Path(__file__).resolve().parents[1]


def digest_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def assert_pre_retrieval(root):
    for record_path in (root / 'results').rglob('run.json'):
        record = json.loads(record_path.read_text())
        if record.get('command') in {'ingest', 'evaluate'}:
            raise ValueError('A model/retrieval experiment has already started; cannot amend this holdout in place')


def source_key(document_id, unit):
    return document_id, str(unit)


def find_page(record, by_id, by_unit):
    unit = record['unit']
    document_id = record.get('document_id')
    if document_id is not None:
        key = source_key(document_id, unit)
        if key not in by_id:
            raise ValueError(f'Authored source unit does not exist: {key}')
        return by_id[key]
    matches = by_unit.get(str(unit), [])
    if len(matches) != 1:
        raise ValueError(f'Authored unit {unit!r} is missing or ambiguous; provide document_id')
    return matches[0]


def evidence_record(page, quote):
    start = page.text.find(quote)
    if not quote or start < 0:
        raise ValueError(f'Evidence missing from normalized source: {source_key(page.document_id, page.page)}')
    return {'gold_source_id': page.document_id, 'gold_page': page.page,
            'evidence_quote': quote, 'evidence_start': start, 'evidence_end': start + len(quote),
            'gold_source_url': page.source, 'gold_text_sha256': digest_text(page.text)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-manifest', required=True)
    parser.add_argument('--corpus-spec', default='data/corpus-spec.json')
    parser.add_argument('--amend-before-retrieval', action='store_true',
                        help='Preserve the old freeze and amend only before any ingest/evaluate run')
    args = parser.parse_args()
    require_python()
    root = STARTER.parent.resolve()
    config = json.loads((STARTER / 'config/pipeline.json').read_text())
    with exclusive_run(lab_path(root, config['cache']) / 'pipeline.lock'):
        finalize(root, config, args)


def finalize(root, config, args):
    """Validate staged artifacts, then publish each atomically and the freeze last.

    A crash between publications is detectable through the freeze checksums.
    Validation and amendment refusals never overwrite the active artifacts.
    """
    root = root.resolve()
    corpus = lab_path(root, config['corpus'])
    benchmark = lab_path(root, config['benchmark'])
    manifest_path = lab_path(root, config.get('manifest', 'data/manifest.json'))
    lock_path = lab_path(root, config.get('freeze', 'benchmark/freeze.json'))
    authored_path = lab_path(root, 'benchmark/questions.authored.json')
    spec_path = lab_path(root, args.corpus_spec)
    fetch_path = lab_path(root, args.fetch_manifest)
    spec = json.loads(spec_path.read_text())
    for field in ('title', 'rights', 'counting_rule', 'extraction_limits', 'benchmark_split'):
        if not spec.get(field):
            raise ValueError(f'Missing corpus specification: {field}')
    for field in ('content_license_observed', 'license_url', 'ai_use_permission', 'basis'):
        if not spec['rights'].get(field):
            raise ValueError(f'Missing rights specification: {field}')
    split_spec = spec['benchmark_split']
    for field in ('dev_chapters', 'test_chapters', 'split_method', 'limitations'):
        if not split_spec.get(field):
            raise ValueError(f'Missing benchmark split specification: {field}')
    if set(split_spec['dev_chapters']) & set(split_spec['test_chapters']):
        raise ValueError('Declared development and test chapter scopes overlap')

    input_paths = {'corpus_sha256': corpus, 'authored_sha256': authored_path,
                   'corpus_spec_sha256': spec_path, 'fetch_manifest_sha256': fetch_path}
    input_hashes = {name: sha256(path) for name, path in input_paths.items()}
    fetched = json.loads(fetch_path.read_text())
    if fetched['corpus_sha256'] != input_hashes['corpus_sha256']:
        raise ValueError('Fetch manifest does not match the current corpus')
    previous_freeze_hash, previous = None, None
    if lock_path.exists():
        previous = json.loads(lock_path.read_text())
        if (all(previous.get(name) == value for name, value in input_hashes.items())
            and previous.get('selection_rule') == config['selection_rule']
            and previous.get('normalization_version') == NORMALIZATION_VERSION):
            absolute_config = {**config, 'corpus': str(corpus), 'benchmark': str(benchmark),
                               'manifest': str(manifest_path), 'freeze': str(lock_path)}
            validation = validate(absolute_config)
            print('Inputs already frozen; preserved original freeze record.')
            return validation
        if not args.amend_before_retrieval:
            raise ValueError('Frozen inputs changed; do not silently replace dev/test inputs')
        previous_freeze_hash = sha256(lock_path)
    assert_pre_retrieval(root)

    snapshots = {}
    for source in fetched['sources']:
        key = source_key(source['document_id'], source['unit_id'])
        if key in snapshots:
            raise ValueError(f'Duplicate fetch source unit: {key}')
        snapshots[key] = source
    pages = list(load_pages(corpus))
    by_id, by_unit, hashes, units = {}, {}, set(), []
    for page in pages:
        key = source_key(page.document_id, page.page)
        if key in by_id:
            raise ValueError(f'Duplicate source unit ID: {key}')
        by_id[key] = page
        by_unit.setdefault(str(page.page), []).append(page)
        digest = digest_text(page.text)
        if (type(page.page) not in {int, str} or (type(page.page) is int and page.page < 1)
            or len(page.text) < (200 if type(page.page) is int else 1500) or digest in hashes):
            raise ValueError(f'Unqualified or duplicate normalized content: {key}')
        hashes.add(digest)
        snapshot = snapshots.get(key)
        if snapshot is None or snapshot['url'] != page.source or snapshot['metadata'] != page.metadata:
            raise ValueError(f'Fetch provenance does not match source unit: {key}')
        source_format = snapshot.get('format', 'pdf' if type(page.page) is int else 'html')
        if (source_format == 'pdf') != (type(page.page) is int):
            raise ValueError('PDF sources require physical integer pages; HTML/text sources require string unit IDs')
        unit = {'source_id': snapshot['source_id'], 'document_id': page.document_id,
                'title': snapshot['title'], 'source_path_or_url': page.source,
                'license_or_permission': snapshot['license_or_permission'],
                'license_url': snapshot['license_url'], 'accessed_at': snapshot['fetched_at'],
                'unit_id': page.page, 'boundary': {'char_start': 0, 'char_end': len(page.text)},
                'normalized_characters': len(page.text), 'normalized_sha256': digest,
                'source_format': source_format, 'raw_sha256': snapshot['sha256'],
                'raw_bytes': snapshot['bytes'], 'metadata': page.metadata,
                'attribution': snapshot.get('attribution') or page.metadata.get('attribution')
                    or f"{snapshot['title']}. {page.source}. License: {snapshot['license_or_permission']}"}
        for field in ('book_id', 'book_content_version', 'archive_version', 'page_id'):
            if field in snapshot:
                unit[field] = snapshot[field]
        units.append(unit)
    if set(by_id) != set(snapshots):
        raise ValueError('Fetch manifest and corpus contain different source units')

    questions, audits = [], []
    for authored in json.loads(authored_path.read_text()):
        question = dict(authored)
        authored_alternatives = question.pop('alternative_evidence', [])
        page = find_page(question, by_id, by_unit)
        unit = question.pop('unit')
        question.pop('document_id', None)
        split = question['split']
        if split not in {'dev', 'test'} or page.metadata.get('chapter') not in split_spec[split + '_chapters']:
            raise ValueError(f'Question does not match the declared chapter split: {question["id"]}')
        primary = evidence_record(page, question['evidence_quote'])
        question.update(primary)
        alternatives, seen = [], {(page.document_id, str(page.page), primary['evidence_quote'])}
        for alternative in authored_alternatives:
            candidate = find_page(alternative, by_id, by_unit)
            record = evidence_record(candidate, alternative['evidence_quote'])
            key = (candidate.document_id, str(candidate.page), record['evidence_quote'])
            if key not in seen:
                record['verification_note'] = alternative.get('verification_note', '')
                alternatives.append(record)
                seen.add(key)
        for candidate in pages:
            key = (candidate.document_id, str(candidate.page), primary['evidence_quote'])
            if key not in seen and primary['evidence_quote'] in candidate.text:
                alternatives.append(evidence_record(candidate, primary['evidence_quote']))
                seen.add(key)
        if alternatives:
            question['gold_alternatives'] = alternatives
        questions.append(question)
        audits.append({'question_id': question['id'], 'document_id': page.document_id, 'unit_id': unit,
                       'evidence_matches_source': True, 'quote_words': len(primary['evidence_quote'].split()),
                       'alternative_exact_matches': sum(a['evidence_quote'] == primary['evidence_quote'] for a in alternatives),
                       'documented_alternatives_count': len(alternatives),
                       'source_text_sha256': digest_text(page.text),
                       'semantic_review': 'AI-assisted source reading; learner review pending. Not a retrieval result or human evaluation label.'})

    positions = []
    for index, page in enumerate(pages[:10], 1):
        cursor = 0
        for paragraph in page.text.split('\n\n'):
            start = page.text.find(paragraph, cursor)
            cursor = start + len(paragraph)
            if len(paragraph) >= 180 and not paragraph.startswith('By the end'):
                positions.append({'id': f'coherence-{index:02}', 'document_id': page.document_id,
                                  'unit_id': page.page, 'char_position': start + len(paragraph) // 2,
                                  'paragraph_start': start, 'paragraph_end': cursor,
                                  'source_text_sha256': digest_text(page.text)})
                break
        else:
            raise ValueError('No suitable coherence anchor paragraph')
    coherence = {'rule': 'First ten units in fixed source order; first prose paragraph >=180 characters in each; '
                         'anchor at midpoint. Selected before retrieval/coherence scores.', 'positions': positions}
    manifest = {'title': spec['title'], 'prepared_at': datetime.now(timezone.utc).isoformat(),
                'format': 'normalized JSONL', 'corpus_path': config['corpus'],
                'corpus_sha256': input_hashes['corpus_sha256'], 'normalization_version': NORMALIZATION_VERSION,
                'corpus_spec_path': str(spec_path.relative_to(root)),
                'corpus_spec_sha256': input_hashes['corpus_spec_sha256'],
                'counting_rule': spec['counting_rule'], 'eligible_unit_count': len(units),
                'total_normalized_characters': sum(len(p.text) for p in pages),
                'minimum_unit_characters': min((len(p.text) for p in pages), default=0),
                'rights': spec['rights'], 'extraction_limits': spec['extraction_limits'],
                'fetch_manifest': str(fetch_path.relative_to(root)), 'units': units}
    coherence_path = lab_path(root, 'benchmark/coherence_positions.json')
    audit_path = lab_path(root, 'benchmark/evidence_audit.json')
    cache = lab_path(root, config['cache'])
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.finalize-', dir=cache) as directory:
        staging = Path(directory)
        for name, value in (('questions.json', questions), ('manifest.json', manifest),
                            ('coherence.json', coherence), ('evidence-audit.json', audits)):
            atomic_json(staging / name, value)
        validation_config = {**config, 'corpus': str(corpus), 'benchmark': str(staging / 'questions.json'),
                             'manifest': str(staging / 'manifest.json')}
        validation_config.pop('freeze', None)
        validation = validate(validation_config)
        frozen = {'frozen_at': datetime.now(timezone.utc).isoformat(), 'retrieval_runs_before_freeze': 0,
                  **input_hashes, 'authored_path': str(authored_path.relative_to(root)),
                  'corpus_spec_path': str(spec_path.relative_to(root)),
                  'fetch_manifest_path': str(fetch_path.relative_to(root)),
                  'benchmark_sha256': sha256(staging / 'questions.json'),
                  'manifest_sha256': sha256(staging / 'manifest.json'),
                  'coherence_positions_sha256': sha256(staging / 'coherence.json'),
                  'normalization_version': NORMALIZATION_VERSION, 'selection_rule': config['selection_rule'],
                  'splits': validation['splits'], 'filter_splits': validation['filter_splits'],
                  **{field: split_spec[field] for field in ('dev_chapters', 'test_chapters', 'split_method', 'limitations')},
                  'previous_freeze_sha256': previous_freeze_hash,
                  'amendment_reason': 'Corpus specification or authored inputs changed before any ingest/evaluate run; '
                                      'no retrieval performance was used.' if previous_freeze_hash else None}
        atomic_json(staging / 'freeze.json', frozen)
        if any(sha256(path) != input_hashes[name] for name, path in input_paths.items()):
            raise ValueError('Source inputs changed during finalization; no artifacts published')
        if previous_freeze_hash and sha256(lock_path) != previous_freeze_hash:
            raise ValueError('Existing freeze changed during finalization; no artifacts published')
        if previous is not None:
            atomic_json(root / 'benchmark/freeze-history' / (previous_freeze_hash + '.json'), previous)
        for name, target in (('questions.json', benchmark), ('manifest.json', manifest_path),
                             ('coherence.json', coherence_path), ('evidence-audit.json', audit_path),
                             ('freeze.json', lock_path)):
            atomic_write(target, (staging / name).read_bytes())
    atomic_json(root / 'results/corpus-validation.json', validation)
    print(json.dumps({'validation': validation, 'manifest': str(manifest_path.relative_to(root)),
                      'benchmark': config['benchmark'], 'freeze': str(lock_path.relative_to(root))}, indent=2))
    return validation


if __name__ == '__main__':
    main()
