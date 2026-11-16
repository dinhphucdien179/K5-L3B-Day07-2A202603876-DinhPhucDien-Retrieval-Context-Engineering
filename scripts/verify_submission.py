"""Check submitted files offline with the active Python 3.12 environment."""
from datetime import datetime, timezone
import csv
import io
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from bonus.benchmark import fingerprint, summarize, validate_split
from bonus.corpus import digest
from day07.benchmark import evidence_hit, fraction, load_cases, score
from day07.review import aggregate_reviews, code_fingerprint


def read(path):
    return json.loads((ROOT / path).read_text())


def hashes_match(hashes, base=ROOT):
    return all((base / p).is_file() and digest(base / p) == sha
               for p, sha in hashes.items())


def main():
    out = ROOT / 'results/submission'
    out.mkdir(parents=True, exist_ok=True)
    checks = {}
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (out / 'unit-tests.log').write_text(stream.getvalue())
    checks['unit_tests_passed'] = outcome.wasSuccessful()

    basic = read('results/day07/selection.json')
    checks['basic_source_matches_selection'] = code_fingerprint() == basic['code_fingerprint']
    checks['basic_inputs_match_selection'] = (
        digest(ROOT / 'config/day07_trials.json') == basic['trials_sha256']
        and digest(ROOT / 'data/day07/freeze.json') == basic['benchmark_freeze_sha256']
        and digest(ROOT / basic['dev_run'] / 'run.json') == basic['dev_run_sha256'])
    basic_counts = {s: len(load_cases(s)) for s in ('dev', 'test')}
    checks['basic_split_counts'] = basic_counts == {'dev': 17, 'test': 7}
    basic_trials = 0
    # Aggregators write their output, so run them only on temporary copies.
    with tempfile.TemporaryDirectory(prefix='day07-review-') as folder:
        temp = Path(folder)
        for run_name in ('agent-dev-01', 'agent-test-01'):
            split = 'dev' if 'dev' in run_name else 'test'
            cases = {c['id']: c for c in load_cases(split)}
            for path in sorted((ROOT / 'results/day07' / run_name).glob('*/reviews.json')):
                target = temp / run_name / path.parent.name
                target.mkdir(parents=True)
                for name in ('traces.json', 'reviews.json'):
                    shutil.copyfile(path.parent / name, target / name)
                key = f'{run_name}/{path.parent.name}'
                checks[f'basic_review:{key}'] = aggregate_reviews(target) == read(path.parent / 'review-summary.json')
                traces = read(path.parent / 'traces.json')
                measured = []
                for trace in traces:
                    case = cases[trace['query_id']]
                    row = score(case, trace)
                    original = trace.get('original_query_results', [])
                    row['original_hit1'] = evidence_hit(original[:1], case.get('gold', [])) if case['answerable'] else None
                    row['original_hit3'] = evidence_hit(original[:3], case.get('gold', [])) if case['answerable'] else None
                    measured.append(row)
                checks[f'basic_evidence:{key}'] = measured == read(path.parent / 'evidence-metrics.json')
                basic_trials += 1

    for run_name in ('retrieval-dev-01', 'agent-dev-01', 'agent-test-01'):
        for summary in read(f'results/day07/{run_name}/summary.json'):
            directory = ROOT / 'results/day07' / run_name / summary['trial']
            traces = read(directory / 'traces.json')
            metrics = read(directory / 'evidence-metrics.json')
            costs = [t.get('usage', {}).get('api_cost_usd') for t in traces]
            cost = 0 if run_name.startswith('retrieval') else (
                sum(costs) if all(type(c) in (int, float) for c in costs) else None)
            checks[f'basic_totals:{run_name}/{summary["trial"]}'] = (
                all(fraction([m[k] for m in metrics]) == summary[k]
                    for k in ('hit1', 'hit3', 'context_evidence'))
                and len(traces) == summary['cases']
                and sum(t['status'] == 'error' for t in traces) == summary['errors']
                and math.isclose(sum(t['elapsed_seconds'] for t in traces), summary['total_seconds'])
                and (cost == summary['api_cost_usd'] or (
                    cost is not None and summary['api_cost_usd'] is not None
                    and math.isclose(cost, summary['api_cost_usd']))))

    old = read('results/bonus/selection.json')
    selected = read('results/bonus/selection-v2.json')
    checks['historical_runtime_intact'] = hashes_match(old['code_sha256'], ROOT / 'results/bonus/frozen-runtime-v1')
    checks['historical_dev_intact'] = hashes_match(old['dev_artifacts_sha256'])
    checks['bonus_source_matches_selection'] = fingerprint() == selected['code_sha256']
    checks['bonus_dev_intact'] = hashes_match(selected['dev_artifacts_sha256'])
    counts = {version: {s: len(validate_split(s, ROOT / 'data' / version))
                        for s in ('dev', 'test')}
              for version in ('bonus', 'bonus-v2')}
    checks['bonus_split_counts'] = all(v == {'dev': 18, 'test': 30} for v in counts.values())
    checks['bonus_freeze_matches_selection'] = digest(ROOT / 'data/bonus-v2/freeze.json') == selected['freeze_sha256']
    identity = read('results/bonus/test-gemini-02/run.json')
    checks['test_used_selected_pipeline'] = (
        identity['identity']['selection_sha256'] == digest(ROOT / 'results/bonus/selection-v2.json')
        and identity['identity']['code_sha256'] == selected['code_sha256']
        and identity['identity']['client_settings'] == selected['client_settings']
        and identity['identity']['workers'] == selected['workers']
        and identity['identity']['benchmark_dir'] == selected['benchmark_dir']
        and identity['identity']['freeze_sha256'] == selected['freeze_sha256']
        and selected['selected_utc'] < identity['created_utc'])

    summaries = {}
    runs = [('dev-gemini-05', 'layout_text', 'dev'),
            ('dev-gemini-06', 'layout_vision_image', 'dev'),
            ('test-gemini-01', 'layout_vision_image', 'test'),
            ('dev-gemini-07', 'layout_vision_image', 'dev'),
            ('test-gemini-02', 'layout_vision_image', 'test')]
    with tempfile.TemporaryDirectory(prefix='bonus-review-') as folder:
        for run_name, trial, split in runs:
            source = ROOT / 'results/bonus' / run_name
            target = Path(folder) / run_name
            shutil.copytree(source / trial, target / trial)
            shutil.copyfile(source / 'run.json', target / 'run.json')
            summary = summarize(target / trial, split)
            summaries[run_name] = summary
            checks[f'bonus_review:{run_name}'] = summary == read(source / trial / 'summary.json')
            checks[f'bonus_trace_hashes:{run_name}'] = all(
                row.get('trace_sha256') == digest(source / trial / f'{cid}.json')
                for cid, row in read(source / trial / 'reviews.json').items())
    checks['historical_test_score_preserved'] = summaries['test-gemini-01']['passed'] == 26
    checks['current_dev_score_preserved'] = (summaries['dev-gemini-07']['passed'], summaries['dev-gemini-07']['errors']) == (15, 2)
    checks['current_test_complete'] = (summaries['test-gemini-02']['passed'], summaries['test-gemini-02']['total'], summaries['test-gemini-02']['errors']) == (30, 30, 0)

    rows = list(csv.DictReader((ROOT / 'results/bonus/v2-case-metrics.csv').open()))
    expected_ids = {(s, c['id']) for s in ('dev', 'test') for c in validate_split(s, ROOT / 'data/bonus-v2')}
    checks['case_metrics_cover_all48'] = len(rows) == 48 and {(r['split'], r['case_id']) for r in rows} == expected_ids
    checks['case_metrics_match_summaries'] = all(
        sum(int(r['prompt_tokens']) for r in rows if r['split'] == split) == summaries[run]['prompt_tokens']
        and sum(int(r['completion_tokens']) for r in rows if r['split'] == split) == summaries[run]['completion_tokens']
        and sum(r['passed'] == 'True' for r in rows if r['split'] == split) == summaries[run]['passed']
        for split, run in [('dev', 'dev-gemini-07'), ('test', 'test-gemini-02')])

    report = ROOT / 'report/individual/2A202603876_DinhPhucDien.md'
    headings = lambda text: re.findall(r'^## .+$', text, re.M)
    checks['report_follows_template'] = headings(report.read_text()) == headings((ROOT / 'REPORT_TEMPLATE.md').read_text())
    checks['one_student_report'] = list((ROOT / 'report/individual').glob('2A202603876*.md')) == [report]
    docs = [*ROOT.glob('*.md'), * (ROOT / 'docs').glob('*.md'),
            * (ROOT / 'report').rglob('*.md'), * (ROOT / 'data').rglob('*.md'), ROOT / 'src/README.md']
    missing = []
    for path in docs:
        for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            link = link.strip().split('#', 1)[0]
            if not link or re.match(r'[a-zA-Z]+:', link):
                continue
            destination = (path.parent / unquote(link.strip('<>'))).resolve()
            if not destination.exists() and destination != out / 'verification.json':
                missing.append({'file': str(path.relative_to(ROOT)), 'link': link})
    checks['document_links_resolve'] = not missing

    # Check known local API keys without ever writing their values to output.
    from dotenv import dotenv_values
    keys = [v for k, v in dotenv_values(ROOT / '.env').items()
            if k.endswith('API_KEY') and v and len(v) > 12]
    leaked = []
    scan = [*docs]
    for directory in ('src', 'scripts', 'config', 'data', 'results', 'tests'):
        scan.extend(p for p in (ROOT / directory).rglob('*')
                    if p.suffix in ('.json', '.jsonl', '.csv', '.py', '.sh', '.log') and '__pycache__' not in p.parts)
    for path in scan:
        if any(key in path.read_text(errors='replace') for key in keys):
            leaked.append(str(path.relative_to(ROOT)))
    checks['no_current_api_key_in_submission_files'] = not leaked
    checks['api_key_files_ignored'] = '.env' in (ROOT / '.gitignore').read_text().splitlines()
    # Recheck immutable inputs after all offline review operations.
    checks['frozen_dev_unchanged_after_checks'] = hashes_match(old['dev_artifacts_sha256']) and hashes_match(selected['dev_artifacts_sha256'])

    result = {'verified_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'passed' if all(checks.values()) else 'failed',
              'checks': checks, 'passed': sum(checks.values()), 'total': len(checks),
              'unit_tests': outcome.testsRun, 'python_executable': sys.executable,
              'basic_trials_checked': basic_trials, 'bonus_runs_checked': len(runs),
              'missing_links': missing, 'credential_leak_files': sorted(set(leaked)),
              'report_sha256': digest(report),
              'selection_sha256': digest(ROOT / 'results/bonus/selection-v2.json'),
              'api_called': False, 'database_called': False,
              'note': 'Offline file and arithmetic checks. Source labels remain AI-assisted; this does not add independent human review or a new Docker verification.'}
    (out / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'passed', 'total', 'unit_tests', 'api_called')}, ensure_ascii=False, indent=2))
    for name, ok in checks.items():
        if not ok:
            print(f'FAILED: {name}')
    if missing:
        print(json.dumps(missing, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
