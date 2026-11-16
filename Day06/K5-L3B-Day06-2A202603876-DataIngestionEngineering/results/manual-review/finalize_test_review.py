"""Validate the saved readings and metadata audit, then publish the test review.

Run with Python 3.12. No model, database, or network call is made. Existing scored
audits are protected; --check validates the completed pack without overwriting it.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results/manual-review'
TRACE = ROOT / 'results/20261114T062008.998642Z-evaluate/test-traces.json'
AUDIT = TRACE.with_name('test-manual-audit.json')

def require(condition, message):
    if not condition:
        raise ValueError(message)

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def publish(path, data):
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)

def save(path, value):
    publish(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())

def verify_baseline():
    files = read(OUT/'test-review-baseline.json')['sha256']
    for name, checksum in files.items():
        require(sha(ROOT/name) == checksum, f'Original benchmark artifact changed: {name}')
    return len(files)

def assemble(unscored):
    traces = read(TRACE)
    metadata = read(OUT/'test-metadata-audit.json')
    for item in metadata['inputs'].values():
        require(sha(ROOT/item['path']) == item['sha256'],
                f'Metadata audit input changed: {item["path"]}')
    require(sha(ROOT/metadata['native_evidence_path']) == metadata['native_evidence_sha256'],
            'Native PDF evidence checksum differs')
    primary = read(OUT/'test-grounding-primary.json')
    review_input = read(OUT/'test-grounding-input.json')
    independent = read(OUT/'test-grounding-independent.json')
    require(independent['input_sha256'] == sha(OUT/'test-grounding-input.json'),
            'Independent reading input checksum differs')
    require(len(traces) == len(unscored) == 15, 'Expected 15 cases')
    require(metadata['status'] == 'programmatic_audit_complete', 'Metadata audit failed')
    require(metadata['summary']['records_checked'] == metadata['summary']['metadata_sufficient_and_correct'] == 45,
            'Expected 45 verified metadata records')
    require(all(r['grounding_0_2'] is None and r['metadata_correct_count'] is None
                and r['filter_compliant'] is None and not r['reason'] for r in unscored),
            'Backup must contain original unscored records')
    ids = {(r['question_id'], tuple(h['chunk_id'] for h in r['hits'])):r['case_id'] for r in review_input['cases']}
    second = {r['case_id']:r for r in independent['cases']}
    first = {(r['question_id'],r['strategy']):r for r in primary['cases']}
    meta_cases = {(r['question_id'],r['strategy']):r for r in metadata['cases']}
    originals = {(r['question_id'],r['strategy']):r for r in unscored}
    trace_map = {(r['question_id'],r['strategy']):r for r in traces}
    require(len(ids) == len(second) == len(first) == 11 and len(trace_map) == len(originals) == 15,
            'Duplicate or missing review cases')
    pages = {(p['document_id'],p['page']):p for p in
             (json.loads(line) for line in (ROOT/'data/pages.jsonl').read_text().splitlines())}
    records, rows = [], []
    for trace in traces:
        key = trace['question_id'],trace['strategy']
        chunks = [h['chunk_id'] for h in trace['hits']]
        require(len(chunks) == 3 and chunks == originals[key]['chunk_ids'], 'Trace/audit chunks differ')
        first_key = key if key in first else (key[0],'B')
        judgement = first[first_key]
        require(type(judgement['score']) is int and judgement['score'] in (0,1,2),
                'Grounding score must follow rubric 0/1/2')
        if first_key != key:
            require(trace['hits'] == trace_map[first_key]['hits'] and not trace['applied_filter'],
                    'Can only reuse reading when B/C return identical unfiltered hits')
        case_id = ids[(key[0],tuple(chunks))]
        other = second[case_id]
        require(other['question_id'] == key[0] and other['score'] == judgement['score'],
                f'Unresolved reading difference: {key}')
        require([s['chunk_id'] for s in other['support_by_rank']] == chunks,
                'Independent reading must cover all three returned chunks')
        for s,h in zip(other['support_by_rank'],trace['hits']):
            require(s['excerpt'] == h['text'], 'Independent reading text identity mismatch')
        support = []
        for item in judgement['support']:
            hit = trace['hits'][item['rank']-1]
            position = hit['text'].index(item['quote'])
            meta = hit['metadata']
            start = meta['char_start'] + position
            end = start + len(item['quote'])
            require(pages[(meta['document_id'],meta['page'])]['text'][start:end] == item['quote'],
                    'Supporting quote does not match exact source offsets')
            support.append({**item,'chunk_id':hit['chunk_id'],'document_id':meta['document_id'],
                            'source':meta['source'],'page':meta['page'],'printed_page':meta['printed_page'],
                            'source_char_start':start,'source_char_end':end})
        reason = judgement['reason']
        if key != first_key:
            reason += ' C không nhận filter ở câu này nên trả cùng top-3 với B.'
        m = meta_cases[key]
        records.append({'question_id':key[0],'strategy':key[1],'question':trace['question'],
                        'review_case_id':case_id,'grounding_0_2':judgement['score'],'reason':reason,
                        'support':support,'missing_information':judgement['missing_information'],
                        'chunk_ids':chunks,'independent_review_score':other['score'],
                        'reviewer_type':'ai','human_confirmed':False})
        rows.append({**originals[key],'grounding_0_2':judgement['score'],'reason':reason,
                     'metadata_correct_count':m['metadata_correct_count'],'metadata_checked_count':m['checked_records'],
                     'metadata_check_method':'programmatic comparison with corpus, native PDF and API snapshot',
                     'metadata_audit':'results/manual-review/test-metadata-audit.json',
                     'metadata_record_ids':[f'{key[0]}-{key[1]}-r{rank}' for rank in (1,2,3)],
                     'filter_compliant':m['top3_filter_compliant'],
                     'filter_scope_note':'Only C applies pre-supplied filters; A/B and unfiltered C cases are N/A.',
                     'review_case_id':case_id,'reviewer_type':'ai','human_confirmed':False})
    per_strategy = {}
    for strategy in ('A','B','C'):
        subset = [r for r in records if r['strategy'] == strategy]
        counts = Counter(r['grounding_0_2'] for r in subset)
        per_strategy[strategy] = {'cases':len(subset),'grounding_count_0_1_2':{str(s):counts[s] for s in (0,1,2)},
                                 'grounding_sum':sum(r['grounding_0_2'] for r in subset),
                                 'grounding_mean_0_2':sum(r['grounding_0_2'] for r in subset)/len(subset),
                                 **metadata['summary']['per_strategy'][strategy]}
    return records, rows, per_strategy, metadata, review_input['rubric']

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args = parser.parse_args()
    require(sys.version_info[:2] == (3,12), 'Use Python 3.12 in a venv or Conda environment')
    protected = verify_baseline()
    backup = OUT/'test-audit-unscored.json'
    if args.check:
        original_bytes = backup.read_bytes()
    else:
        require(not backup.exists(), 'Review already published; use --check')
        original_bytes = AUDIT.read_bytes()
    records,rows,per_strategy,metadata,rubric = assemble(json.loads(original_bytes))
    if args.check:
        require(read(AUDIT) == rows, 'Scored audit does not match saved readings/checks')
        pack = read(OUT/'test-grounding.json')
        require(pack['records'] == records, 'Grounding pack does not match saved readings')
        summary = read(OUT/'test-review-summary.json')
        require(summary['grounding']['per_strategy'] == per_strategy, 'Summary score mismatch')
    else:
        now = datetime.now(timezone.utc).isoformat()
        limitations = ['Five test questions only: 15 case occurrences, 11 unique ordered top-3 sets.',
                      'B/C share the physical B index; q16-q19 return identical chunks.',
                      'Two AI readings; human confirmation pending, not human inter-rater reliability.',
                      'Primary reader knew strategy labels and prior results; independent reader only received opaque input cases.',
                      'Expected answers are targets, not proof; no outside text fills missing evidence.',
                      'Grounding measures retrieved evidence sufficiency, not LLM answer accuracy.',
                      'Original corpus, model, benchmark, gold, retrieval metrics and dev selection remain unchanged.']
        pack = {'status':'review_completed_human_confirmation_pending','reviewed_at':now,
                'reviewer_type':'ai','human_confirmed':False,'rubric':rubric,'limitations':limitations,
                'input_sha256':sha(OUT/'test-grounding-input.json'),'records':records}
        summary = {'status':pack['status'],'reviewed_at':now,'metadata':metadata['summary'],
                   'grounding':{'case_occurrences':15,'unique_ordered_top3_cases':11,
                                'per_strategy':per_strategy,'matching_reading_scores':11,
                                'compared_unique_cases':11,'reviewer_type':'ai','human_confirmed':False},
                   'limitations':limitations,'protected_benchmark_files':read(OUT/'test-review-baseline.json')['sha256']}
        publish(backup,original_bytes)
        save(OUT/'test-grounding.json',pack)
        save(OUT/'test-review-summary.json',summary)
        save(AUDIT,rows)
        summary_path = ROOT/'results/benchmark-summary.json'
        benchmark_summary = read(summary_path)
        benchmark_summary['manual_labels'] = 'Coherence/test grounding reviewed with disclosed method; test metadata verified against source artifacts. Human confirmation pending.'
        benchmark_summary['test_review'] = {'artifact':'results/manual-review/test-grounding.json',
            'metadata_audit':'results/manual-review/test-metadata-audit.json','summary':'results/manual-review/test-review-summary.json',
            'metadata_records_checked':45,'metadata_correct':45,'grounding_cases':15,
            'grounding_mean_0_2':{s:p['grounding_mean_0_2'] for s,p in per_strategy.items()},
            'grounding_reviewer_type':'ai','human_confirmation':'pending'}
        save(summary_path,benchmark_summary)
    require(protected == verify_baseline(), 'Protected identities changed')
    print(json.dumps({'mode':'check' if args.check else 'publish','cases':len(records),
                      'metadata':metadata['summary']['metadata_sufficient_and_correct'],
                      'grounding_means':{s:p['grounding_mean_0_2'] for s,p in per_strategy.items()},
                      'protected_files_unchanged':protected},ensure_ascii=False))

if __name__ == '__main__':
    main()
