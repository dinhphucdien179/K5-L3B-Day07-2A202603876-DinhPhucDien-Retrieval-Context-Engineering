"""Budgeted document pipeline. Every path resolves from this lab's root."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
from itertools import islice
import json
import os
from pathlib import Path

from .runtime import RuntimeConfig, Telemetry, atomic_json, exclusive_run, lab_path, require_python

ROOT = Path(__file__).resolve().parents[2]
SELECTION_RULE = 'Highest dev Evidence Hit@3, then dev Hit@1, then fewer stored chunks. Stable tie: A, B, C.'


def resolve(value):
    return lab_path(ROOT, value)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def chunks_for(config, strategy):
    from .chunking import fixed_size, by_paragraph
    from .ingestion import load_pages
    settings = config['chunking']
    for page in load_pages(resolve(config['corpus'])):
        if strategy == 'A':
            yield from fixed_size(page, settings['fixed_size'], settings['overlap'])
        else:
            yield from by_paragraph(page, settings['paragraph_max_size'])


def validate(config):
    """Verify corpus provenance, split and evidence before any model load or retrieval."""
    from .ingestion import load_pages, normalize_text, NORMALIZATION_VERSION
    from .evaluation import gold_evidence
    if config['selection_rule'] != SELECTION_RULE:
        raise ValueError('Selection rule is implemented as Hit@3, Hit@1, chunk count, A/B/C; update code and rule together')
    corpus_path = resolve(config['corpus'])
    if config.get('manifest'):
        manifest = json.loads(resolve(config['manifest']).read_text())
        if manifest['corpus_sha256'] != sha256(corpus_path) or manifest['normalization_version'] != NORMALIZATION_VERSION:
            raise ValueError('Corpus does not match its manifest or normalization version')
    if config.get('freeze'):
        frozen = json.loads(resolve(config['freeze']).read_text())
        if (frozen['corpus_sha256'] != sha256(corpus_path)
            or frozen['benchmark_sha256'] != sha256(resolve(config['benchmark']))
            or frozen['normalization_version'] != NORMALIZATION_VERSION
            or frozen['selection_rule'] != config['selection_rule']):
            raise ValueError('Frozen corpus/benchmark inputs changed; do not silently reuse the holdout')
        if config.get('manifest') and frozen['manifest_sha256'] != sha256(resolve(config['manifest'])):
            raise ValueError('Frozen manifest changed')
        if frozen.get('coherence_positions_sha256') != sha256(resolve('benchmark/coherence_positions.json')):
            raise ValueError('Frozen coherence positions changed')
        for digest_key, path_key, default in (
            ('authored_sha256', 'authored_path', 'benchmark/questions.authored.json'),
            ('corpus_spec_sha256', 'corpus_spec_path', config.get('corpus_spec', 'data/corpus-spec.json')),
            ('fetch_manifest_sha256', 'fetch_manifest_path', None),
        ):
            if digest_key in frozen:
                frozen_path = frozen.get(path_key, default)
                if not frozen_path or frozen[digest_key] != sha256(resolve(frozen_path)):
                    raise ValueError(f'Frozen input changed: {path_key}')
    questions = json.loads(resolve(config['benchmark']).read_text())
    evidence = {}
    remaining = set()
    for q in questions:
        for index, gold in enumerate(gold_evidence(q)):
            key = (gold['gold_source_id'], str(gold['gold_page']))
            quote = ' '.join(normalize_text(gold['evidence_quote']).split())
            evidence.setdefault(key, []).append((q['id'], index, quote, gold))
            remaining.add((q['id'], index))
    pages, characters, text_hashes = {}, 0, set()
    for page in load_pages(resolve(config['corpus'])):
        key = (page.document_id, str(page.page))
        if key in pages:
            raise ValueError(f'Duplicate source unit: {key}')
        text_hash = hashlib.sha256(page.text.encode()).hexdigest()
        if text_hash in text_hashes:
            raise ValueError(f'Duplicate normalized source content: {key}')
        text_hashes.add(text_hash)
        if len(page.text) < 1500 and isinstance(page.page, str):
            raise ValueError(f'Conservative HTML/text unit rule requires >=1500 characters: {key}')
        if not set(page.metadata) & {'chapter', 'section', 'year', 'version', 'category', 'audience', 'language', 'document_type'}:
            raise ValueError(f'No useful filter metadata: {key}')
        for qid, index, quote, gold in evidence.get(key, []):
            if not quote or quote not in ' '.join(page.text.split()):
                raise ValueError(f'Evidence does not exist in corpus: {qid}')
            if 'evidence_start' in gold or 'evidence_end' in gold:
                start, end = gold.get('evidence_start'), gold.get('evidence_end')
                if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(page.text)
                    or page.text[start:end] != gold['evidence_quote']):
                    raise ValueError(f'Evidence offsets do not match source: {qid}')
            if gold.get('gold_text_sha256', text_hash) != text_hash:
                raise ValueError(f'Evidence source checksum mismatch: {qid}')
            remaining.discard((qid, index))
        pages[key] = page.metadata  # Retain provenance only, never the entire corpus text.
        characters += len(page.text)
    if len(pages) < 30:
        raise ValueError(f'Need >=30 eligible source units, found {len(pages)}')
    if remaining:
        raise ValueError(f'Gold source units missing for questions: {sorted(remaining)}')
    ids, question_texts, splits, filter_splits = set(), set(), Counter(), Counter()
    for q in questions:
        for field in ('id', 'split', 'question', 'expected_answer', 'gold_source_id', 'gold_page', 'evidence_quote'):
            if field not in q or q[field] in (None, ''):
                raise ValueError(f'Missing benchmark field: {field}')
        if q['id'] in ids or q['split'] not in {'dev', 'test'}:
            raise ValueError('Duplicate question ID or invalid split')
        ids.add(q['id'])
        question_text = ' '.join(q['question'].casefold().split())
        if question_text in question_texts:
            raise ValueError('Duplicate question text across benchmark')
        question_texts.add(question_text)
        splits[q['split']] += 1
        filters = q.get('filter', {})
        if filters:
            allowed = {'chapter', 'section', 'year', 'version', 'category', 'audience', 'language', 'document_type'}
            if set(filters) - allowed:
                raise ValueError('Gold source/page is forbidden in filters')
            if any(type(v) not in {str, int, bool} for v in filters.values()):
                raise ValueError('Metadata filters require scalar values')
            if not q.get('filter_context'):
                raise ValueError('Filter questions need filter_context supplied before retrieval')
            if not any(all(p.get(k) == v for k, v in filters.items()) for p in pages.values()):
                raise ValueError('Filter values do not occur in corpus')
            if not any(all(pages[(g['gold_source_id'], str(g['gold_page']))].get(k) == v for k,v in filters.items())
                       for g in gold_evidence(q)):
                raise ValueError('Question filter excludes all documented gold evidence')
            filter_splits[q['split']] += 1
    if splits['dev'] < 15 or splits['test'] < 5 or sum(filter_splits.values()) < 3 or filter_splits['test'] < 1:
        raise ValueError('Need >=15 dev/5 test and >=3 filter questions including >=1 test')
    for field in set().union(*(q.get('filter', {}) for q in questions)):
        values = {json.dumps(p[field], sort_keys=True) for p in pages.values() if field in p}
        if len(values) < 2:
            raise ValueError(f'Filter field {field} must distinguish at least two real scopes')
    return {'source_units': len(pages), 'characters': characters,
            'splits': dict(splits), 'filter_splits': dict(filter_splits)}


def fingerprint(config):
    from .ingestion import NORMALIZATION_VERSION
    return {'corpus_sha256': sha256(resolve(config['corpus'])),
            'benchmark_sha256': sha256(resolve(config['benchmark'])),
            'embedding': config['embedding'], 'chunking': config['chunking'],
            'selection_rule': config['selection_rule'], 'normalization': NORMALIZATION_VERSION}


def require_processing_rights(config):
    """Respect an explicitly unresolved AI-use notice before loading a model."""
    if config.get('manifest'):
        manifest = json.loads(resolve(config['manifest']).read_text())
        if manifest.get('rights', {}).get('ai_use_permission') == 'not_established':
            raise ValueError('Corpus manifest explicitly marks AI-use permission as not_established. '
                             'Resolve the source notice and record its basis before embedding/retrieval; '
                             'see RULES.md and data/manifest.json. Model smoke uses authored text separately.')


def fetch_sources(config, runtime, output, refresh):
    """Materialize explicit HTML units or selected PDF pages, without model calls."""
    from .fetching import SnapshotFetcher, bounded_map
    from .ingestion import OpenStaxHTML, iter_selected_pdf_pages
    from .openstax import verify_source
    sources = json.loads(resolve(config['sources']).read_text())
    urls = [source['url'] for source in sources]
    if not urls or len(urls) != len(set(urls)):
        raise ValueError('Source list must be nonempty and have unique URLs')
    if any(source.get('format', 'html') not in {'html', 'pdf'} for source in sources):
        raise ValueError('Corpus source format must be explicit html or pdf')
    target = resolve(config['corpus'])
    target.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.pages.')
    manifest = []
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream, SnapshotFetcher(resolve(config['cache']) / 'http', runtime) as fetcher:
            snapshots = bounded_map(lambda source: fetcher.fetch(source['url'], refresh=refresh,
                                    content_type='application/pdf' if source.get('format') == 'pdf' else 'text/html'), sources,
                                    runtime.fetch_workers, runtime.max_inflight)
            try:
                for source, snapshot in zip(sources, snapshots):
                    expected_sha256 = source.get('expected_sha256')
                    if expected_sha256 is not None and expected_sha256 != snapshot['sha256']:
                        raise ValueError('Source snapshot differs from its pinned expected_sha256; '
                                         'do not overwrite the frozen corpus with a changed source')
                    if source.get('format') == 'pdf':
                        source_provenance = {key: value for key, value in source.items() if key != 'pages'}
                        for page in iter_selected_pdf_pages(Path(snapshot['body_path']), source, runtime.guard):
                            record = {'document_id': page.document_id, 'source': page.source,
                                      'page': page.page, 'text': page.text, 'metadata': page.metadata}
                            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                            manifest.append({**source_provenance, **snapshot,
                                             'body_path': str(Path(snapshot['body_path']).relative_to(ROOT)),
                                             'unit_id': page.page,
                                             'metadata': page.metadata, 'normalized_characters': len(page.text)})
                        continue
                    runtime.guard('parse-html')
                    parser = OpenStaxHTML()
                    raw = Path(snapshot['body_path']).read_bytes()
                    if source.get('book_id'):
                        verify_source(raw, source)
                    parser.feed(raw.decode('utf-8'))
                    text = parser.text()
                    record = {'document_id': source['document_id'], 'source': source['url'],
                              'page': source['unit_id'], 'text': text, 'metadata': source['metadata']}
                    stream.write(json.dumps(record, ensure_ascii=False) + '\n')
                    manifest.append({**source, **snapshot,
                                     'body_path': str(Path(snapshot['body_path']).relative_to(ROOT)),
                                     'normalized_characters': len(text)})
            finally:
                snapshots.close()
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        # Hash binds manifest to the published corpus. A crash between files is detectable.
        atomic_json(output / 'fetch-manifest.json', {'corpus_sha256': sha256(target), 'sources': manifest})
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ingest(config, runtime, telemetry, output, embedder, store):
    stats = {}
    for strategy in ('A', 'B'):
        lengths = Counter()
        count = 0
        def batches():
            nonlocal count
            iterator = chunks_for(config, strategy)
            while batch := list(islice(iterator, runtime.batch_size)):
                with telemetry.stage('embed_batch', strategy=strategy, items=len(batch)):
                    vectors = embedder.embed_documents([chunk.text for chunk in batch])
                lengths.update(len(chunk.text) for chunk in batch)
                count += len(batch)
                yield batch, vectors
                runtime.guard('write_batch:after')
            if fingerprint(config) != {key: value for key, value in store.identity.items() if key != 'resolved_embedding'}:
                raise RuntimeError('Corpus or benchmark changed during ingestion; transaction will roll back')
        with telemetry.stage('ingest_strategy', strategy=strategy):
            stored = store.replace_batches(strategy, batches())
        stats[strategy] = {'chunk_count': stored, 'characters': sum(k*v for k,v in lengths.items()),
                           'length_histogram': dict(sorted(lengths.items()))}
    stats['C'] = {**stats['B'], 'physical_index': 'B', 'additional_embedding_calls': 0}
    stats['cache'] = {'hits': embedder.cached.hits, 'misses': embedder.cached.misses}
    atomic_json(output / 'ingestion.json', stats)
    return stats


def evaluate(config, runtime, telemetry, output, embedder, store, split, identity):
    from .evaluation import evaluate_query, summarize
    selection_path = resolve(config['results']) / 'dev-selection.json'
    if split == 'test':
        selection = json.loads(selection_path.read_text())
        if selection['identity'] != identity:
            raise ValueError('Corpus/model/benchmark changed since dev selection; rerun dev before test')
    questions = [q for q in json.loads(resolve(config['benchmark']).read_text()) if q['split'] == split]
    traces = []
    with store.read_snapshot():
        for strategy in ('A', 'B'):
            store.check_identity(strategy)
        for q in questions:
            vector = embedder.embed_query(q['question'])
            for strategy in ('A', 'B', 'C'):
                filters = q.get('filter', {}) if strategy == 'C' else {}
                with telemetry.stage('search', strategy=strategy, question_id=q['id']):
                    hits = store.search(strategy, vector, filters=filters)
                trace = {**evaluate_query(q, hits), 'strategy': strategy,
                         'physical_index': store.physical(strategy), 'applied_filter': filters}
                traces.append(trace)
        summary = summarize(traces)
        counts = dict(store.connection.execute('SELECT strategy,chunk_count FROM day6_indexes').fetchall())
    atomic_json(output / f'{split}-traces.json', traces)
    atomic_json(output / f'{split}-summary.json', summary)
    if split == 'dev':
        chosen = min(summary, key=lambda row: (-row['hit3_count'], -row['hit1_count'],
                                               counts[store.physical(row['strategy'])], row['strategy']))
        atomic_json(selection_path, {'strategy': chosen['strategy'], 'identity': identity,
                                     'rule': config['selection_rule'], 'dev_artifacts': str(output.relative_to(ROOT))})
    # Empty fields request a human decision; never derive them from retrieval metrics.
    atomic_json(output / f'{split}-manual-audit.json', [
        {'question_id': t['question_id'], 'strategy': t['strategy'], 'grounding_0_2': None,
         'metadata_correct_count': None, 'filter_compliant': None, 'reason': '',
         'chunk_ids': [h['chunk_id'] for h in t['hits']]} for t in traces])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preflight', 'fetch', 'validate', 'ingest', 'evaluate'), nargs='?', default='preflight')
    parser.add_argument('--config', default='starter/config/pipeline.json')
    parser.add_argument('--split', choices=('dev', 'test'), default='dev')
    parser.add_argument('--refresh', action='store_true', help='Revalidate HTTP snapshots with ETag/Last-Modified')
    args = parser.parse_args()
    require_python()
    config = json.loads(resolve(args.config).read_text())
    runtime = RuntimeConfig(**config['runtime'])
    hardware = runtime.apply_threads()
    results = resolve(config['results'])
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    output = results / f'{stamp}-{args.command}'
    with exclusive_run(resolve(config['cache']) / 'pipeline.lock'):
        telemetry = Telemetry(output / 'telemetry.jsonl', runtime)
        store = None
        try:
            packages = {}
            for name in ('numpy', 'requests', 'pypdf', 'psycopg', 'pgvector', 'torch', 'sentence-transformers'):
                try:
                    packages[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    packages[name] = None
            atomic_json(output / 'run.json', {'command': args.command, 'config': config, 'hardware': hardware,
                                             'packages': packages, 'status': 'started'})
            with telemetry.stage(args.command):
                if args.command == 'preflight':
                    result = {'hardware': hardware, 'packages': packages, 'model_revision_pinned': bool(config['embedding']['revision'])}
                elif args.command == 'fetch':
                    fetch_sources(config, runtime, output, args.refresh)
                    result = {'fetch_manifest': str((output / 'fetch-manifest.json').relative_to(ROOT))}
                else:
                    result = validate(config)
                    if args.command != 'validate':
                        require_processing_rights(config)
                        from .embeddings import MyEmbedder
                        from .store import PgVectorStore
                        from dotenv import load_dotenv
                        load_dotenv(ROOT / 'starter' / '.env')
                        database_url = os.getenv('DATABASE_URL')
                        if not database_url:
                            raise ValueError('DATABASE_URL missing; configure starter/.env')
                        model = MyEmbedder(**config['embedding'], runtime=runtime, cache=resolve(config['cache']))
                        identity = {**fingerprint(config), 'resolved_embedding': model.identity}
                        store = PgVectorStore(database_url, model.dimensions, identity)
                        store.create_schema()
                        if args.command == 'ingest':
                            result = ingest(config, runtime, telemetry, output, model, store)
                        else:
                            result = evaluate(config, runtime, telemetry, output, model, store, args.split, identity)
            atomic_json(output / 'status.json', {'status': 'complete', 'result': result})
            print(json.dumps({'artifacts': str(output.relative_to(ROOT)), 'result': result}, ensure_ascii=False, indent=2))
        except BaseException as exc:
            # Avoid writing provider/connection exception strings that might include credentials.
            atomic_json(output / 'status.json', {'status': 'failed', 'error_type': type(exc).__name__})
            raise
        finally:
            if store:
                store.close()
            telemetry.close()


if __name__ == '__main__':
    main()
