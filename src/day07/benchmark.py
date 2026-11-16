"""Evidence-only measurements, split isolation, and real-agent experiment artifacts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import time

from .agent import pack_context, run_agent
from .context import NeighborContext
from .day06 import ROOT, DAY06
from .retrieval import BM25, Hybrid


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def compact(text):
    return ' '.join(text.split())


def matches(row, gold):
    return row['source_id'] == gold['source_id'] and str(row['page']) == str(gold['page'])


def evidence_hit(rows, gold):
    return any(matches(row, g) and compact(g['evidence']) in compact(row['text']) for row in rows for g in gold)


def context_hit(rows, gold):
    # Join only contiguous/overlapping source intervals; never fill unseen gaps.
    for g in gold:
        candidates = sorted([row for row in rows if matches(row, g)],
                            key=lambda r: r['metadata']['char_start'])
        text, end = '', -1
        for row in candidates:
            start, stop = row['metadata']['char_start'], row['metadata']['char_end']
            if start > end:
                text, end = row['text'], stop
            elif stop > end:
                text += row['text'][end-start:]
                end = stop
            if compact(g['evidence']) in compact(text):
                return True
    return False


def score(case, trace):
    searches = [e for e in trace.get('events', []) if e['event'] == 'search']
    first = searches[0]['results'] if searches else trace.get('results', [])
    gold = case.get('gold', [])
    return {'query_id': case['id'], 'answerable': case['answerable'],
            'hit1': evidence_hit(first[:1], gold) if gold else None,
            'hit3': evidence_hit(first[:3], gold) if gold else None,
            'context_evidence': context_hit(trace['context_chunks'], gold) if gold else None,
            'ranking_query': searches[0]['query'] if searches else case['question'],
            'ranking_note': 'first tool query; original-query retrieval is reported separately for agents'}


def fraction(values):
    values = [value for value in values if value is not None]
    n, N = sum(values), len(values)
    return {'n': n, 'N': N, 'rate': n/N if N else None}


def load_cases(split):
    directory = ROOT / 'data/day07'
    frozen = json.loads((directory / 'freeze.json').read_text())
    path = directory / f'{split}.json'
    if digest(path) != frozen[f'{split}_sha256'] or digest(DAY06 / 'data/pages.jsonl') != frozen['corpus_sha256']:
        raise ValueError('Benchmark or corpus differs from the frozen inputs')
    cases = json.loads(path.read_text())
    if len({case['id'] for case in cases}) != len(cases):
        raise ValueError('Duplicate query IDs')
    pages = {(r['document_id'], str(r['page'])): r['text'] for r in
             map(json.loads, (DAY06 / 'data/pages.jsonl').read_text().splitlines())}
    for case in cases:
        if case['split'] != split or type(case.get('answerable')) is not bool:
            raise ValueError('Invalid split or answerable label')
        if case['answerable']:
            if not case.get('gold') or not case.get('expected_answer'):
                raise ValueError('Missing gold/expected answer')
            for gold in case['gold']:
                page = pages[(gold['source_id'], str(gold['page']))]
                if page[gold['start']:gold['end']] != gold['evidence']:
                    raise ValueError('Gold offsets do not match corpus')
        elif not case.get('absence_reason'):
            raise ValueError('Unanswerable case requires an absence audit')
    minimum = {'dev': (15, 2), 'test': (5, 2)}[split]
    if sum(c['answerable'] for c in cases) < minimum[0] or sum(not c['answerable'] for c in cases) < minimum[1]:
        raise ValueError('Split below assignment minimum')
    return cases


def run_benchmark(store, *, split='dev', suite='retrieval', trials_path=None, output=None, client=None, selection=None, workers=1, resume=False):
    trials_path = Path(trials_path or ROOT / 'config/day07_trials.json')
    configuration = json.loads(trials_path.read_text())
    trials = configuration['trials']
    if split == 'test':
        if not selection:
            raise ValueError('Test requires a frozen selection file; choose using dev first')
        frozen = json.loads(Path(selection).read_text())
        from .review import code_fingerprint
        if frozen['code_fingerprint'] != code_fingerprint() or suite == 'agent' and client.model != frozen['model']:
            raise ValueError('Agent code or model changed after selection; do not tune on test')
        if frozen['trials_sha256'] != digest(trials_path):
            raise ValueError('Configuration changed after selection')
        if frozen['corpus_sha256'] != store.identity['corpus_sha256']:
            raise ValueError('Corpus changed after selection')
        if frozen['benchmark_freeze_sha256'] != digest(ROOT / 'data/day07/freeze.json'):
            raise ValueError('Benchmark changed after selection')
        trials = [t for t in trials if t['name'] in {'dense_baseline', frozen['selected_trial']}]
        if len(trials) != len({'dense_baseline', frozen['selected_trial']}):
            raise ValueError('Selection does not identify a valid trial')
    if any(t['index'] != store.strategy for t in trials):
        raise ValueError('All trials must use the connected physical index')
    if suite == 'agent' and client is None:
        raise ValueError('Real agent benchmark requires an LLM client')
    cases = load_cases(split)
    if type(workers) is not int or not 1 <= workers <= 3:
        raise ValueError('workers must be 1..3')
    output = Path(output or ROOT / 'results/day07' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + f'-{suite}-{split}'))
    if output.exists() and any(output.iterdir()) and not resume:
        raise ValueError('Use a new output directory; old experiments are preserved')
    output.mkdir(parents=True, exist_ok=True)
    metadata = {'split': split, 'suite': suite, 'trials': trials,
        'selection_rule': configuration['selection_rule'], 'model': client.model if client else None,
        'trials_sha256': digest(trials_path), 'benchmark_freeze_sha256': digest(ROOT / 'data/day07/freeze.json'),
        'index_identity': store.identity, 'context_metric': 'complete normalized gold alternative in union of contiguous source intervals',
        'ranking_metric': 'one original chunk contains a complete gold alternative; same cutoff for all methods',
        'annotation': 'answer quality/citation support require review; no automatic semantic grading',
        'workers': workers, 'timing_note': 'per-query latency may include contention; total_seconds sums latencies, not wall clock'}
    if resume:
        previous = json.loads((output / 'run.json').read_text())
        for key in ['split', 'suite', 'trials_sha256', 'benchmark_freeze_sha256', 'model', 'index_identity']:
            if previous[key] != metadata[key]:
                raise ValueError('Cannot resume with changed experiment inputs')
        metadata['resume_note'] = 'Preserved every saved trace, including errors; an interrupted in-flight request may have unknown billed usage. Costs sum recorded responses only.'
        metadata['initial_workers'] = previous.get('workers', 1)
    write_json(output / 'run.json', metadata)
    lexical = BM25(store.chunks)
    retrievers = {'dense': store, 'bm25': lexical, 'hybrid': Hybrid(store, lexical)}
    native_lock = Lock()
    class SerializedRetriever:
        def __init__(self, inner): self.inner = inner
        def search(self, query, **kwargs):
            # Serialize shared database/embedding/cache access; only HTTP overlaps.
            with native_lock:
                return self.inner.search(query, **kwargs)
    summaries = []
    for trial in trials:
        retriever = SerializedRetriever(retrievers[trial['method']])
        builder = NeighborContext(store.chunks, trial['neighbors'])
        directory = output / trial['name']
        existing_path = directory / 'traces.json'
        traces = json.loads(existing_path.read_text()) if resume and existing_path.exists() else []
        saved = {t['query_id']: t for t in traces}
        if len(saved) != len(traces) or not set(saved) <= {c['id'] for c in cases}:
            raise ValueError('Invalid saved case IDs')
        def execute_case(case):
            started = time.perf_counter()
            filters = case.get('filter', {})
            # Retrieval gets only question/scope; gold is used strictly after execution.
            try:
                original = retriever.search(case['question'], top_k=trial['top_k'], filters=filters)
                original_seconds = time.perf_counter() - started
                if suite == 'agent':
                    trace = run_agent(case['question'], client, retriever, filters=filters, top_k=trial['top_k'],
                                      budget=trial['budget'], max_searches=trial['max_searches'], context_builder=builder)
                    trace['original_query_results'] = original
                    trace['original_query_seconds'] = original_seconds
                else:
                    context, selected = pack_context(builder.expand(original, filters), trial['budget'])
                    trace = {'status': 'retrieved', 'results': original, 'context': context,
                             'context_chunks': selected, 'context_ids': [r['id'] for r in selected],
                             'elapsed_seconds': time.perf_counter() - started, 'events': []}
            except Exception as exc:
                trace = {'status': 'error', 'error_type': type(exc).__name__, 'context': '', 'context_chunks': [],
                         'events': [], 'elapsed_seconds': time.perf_counter() - started}
            trace.update(query_id=case['id'], question=case['question'], trial=trial['name'], split=split)
            return trace
        missing = [case for case in cases if case['id'] not in saved]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(execute_case, case) for case in missing]
            for future in as_completed(futures):
                trace = future.result()
                saved[trace['query_id']] = trace
                traces = [saved[c['id']] for c in cases if c['id'] in saved]
                write_json(directory / 'traces.json', traces)
                print(f"{trial['name']} {trace['query_id']}: {trace['status']}", flush=True)
        traces = [saved[c['id']] for c in cases]
        labels, reviews = [], []
        for case, trace in zip(cases, traces):
            metric = score(case, trace)
            if suite == 'agent':
                metric['original_hit1'] = evidence_hit(trace.get('original_query_results', [])[:1], case.get('gold', [])) if case['answerable'] else None
                metric['original_hit3'] = evidence_hit(trace.get('original_query_results', [])[:3], case.get('gold', [])) if case['answerable'] else None
            labels.append(metric)
            reviews.append({'query_id': case['id'], 'answerable': case['answerable'], 'context_grade': None,
                            'answer_grade': None, 'citation_support': None, 'abstention_correct': None,
                            'reason': '', 'reviewer': ''})
        write_json(directory / 'evidence-metrics.json', labels)
        write_json(directory / 'reviews.template.json', reviews)
        costs = [t.get('usage', {}).get('api_cost_usd') for t in traces]
        summary = {'trial': trial['name'], 'split': split, 'cases': len(cases),
            'hit1': fraction([m['hit1'] for m in labels]), 'hit3': fraction([m['hit3'] for m in labels]),
            'context_evidence': fraction([m['context_evidence'] for m in labels]),
            'errors': sum(t['status'] == 'error' for t in traces),
            'total_seconds': sum(t['elapsed_seconds'] for t in traces),
            'api_cost_usd': 0 if suite == 'retrieval' else (sum(costs) if all(type(c) in (int, float) for c in costs) else None)}
        if suite == 'agent':
            summary.update(original_hit1=fraction([m['original_hit1'] for m in labels]),
                           original_hit3=fraction([m['original_hit3'] for m in labels]))
        summaries.append(summary)
        write_json(output / 'summary.json', summaries)
    return {'artifacts': str(output), 'summary': summaries}
