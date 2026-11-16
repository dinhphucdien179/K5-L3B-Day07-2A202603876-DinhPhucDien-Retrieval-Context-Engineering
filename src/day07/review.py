"""Validate explicitly supplied review labels and freeze a dev-based selection."""
import json
from pathlib import Path

from .benchmark import ROOT, digest, fraction, write_json


def code_fingerprint():
    return {name: digest(ROOT / 'src/day07' / name) for name in
            ['agent.py', 'context.py', 'retrieval.py', 'day06.py', 'llm.py']}


def aggregate_reviews(directory):
    directory = Path(directory)
    traces = json.loads((directory / 'traces.json').read_text())
    reviews = json.loads((directory / 'reviews.json').read_text())
    by_id = {r['query_id']: r for r in reviews}
    if len(by_id) != len(reviews) or set(by_id) != {t['query_id'] for t in traces}:
        raise ValueError('Review IDs must match every trace exactly once')
    grounded, context, support, abstentions, false_abstentions, tool_use, citation_coverage = [], [], [], [], [], [], []
    call_counts = []
    for trace in traces:
        review = by_id[trace['query_id']]
        if not review.get('reason') or not review.get('reviewer'):
            raise ValueError('Every review needs a reason and reviewer identity')
        if trace['status'] == 'error':
            continue
        if type(review.get('answerable')) is not bool:
            raise ValueError('Missing answerable boolean')
        labels = review.get('citation_support')
        if not isinstance(labels, list) or len(labels) != len(trace.get('citations', [])) or any(type(v) is not bool for v in labels):
            raise ValueError('One boolean support label is required per citation')
        support.extend(labels)
        if trace['status'] == 'answered':
            citation_coverage.append(bool(trace.get('citations')))
        searches = sum(e['event'] == 'search' for e in trace['events'])
        tool_use.append(searches > 0)
        call_counts.append(searches)
        if review['answerable']:
            grade, cg = review.get('answer_grade'), review.get('context_grade')
            if type(grade) is not int or grade not in (0, 1, 2) or type(cg) is not int or cg not in (0, 1, 2):
                raise ValueError('Answer/context grades must be 0..2')
            if trace['status'] == 'abstain' and grade != 0:
                raise ValueError('Abstaining on an answerable case must score 0')
            grounded.append(grade)
            context.append(cg)
            false_abstentions.append(trace['status'] == 'abstain')
        else:
            value = review.get('abstention_correct')
            if type(value) is not bool or value and trace['status'] != 'abstain':
                raise ValueError('Unanswerable cases require a consistent abstention label')
            abstentions.append(value)
    summary = {'annotation': 'Explicit review labels; inspect reviewer identity and reasons. AI-assisted review is not independent human grading.',
        'cases': len(traces), 'errors': sum(t['status'] == 'error' for t in traces),
        'grounded_answer': {'counts': {str(i): grounded.count(i) for i in range(3)}, 'N': len(grounded),
                            'mean_out_of_2': sum(grounded)/len(grounded) if grounded else None},
        'context_grade': {'counts': {str(i): context.count(i) for i in range(3)}, 'N': len(context)},
        'citation_validity': fraction(support), 'answer_citation_coverage': fraction(citation_coverage),
        'abstention': fraction(abstentions), 'false_abstention': fraction(false_abstentions),
        'tool_use': fraction(tool_use), 'search_call_distribution': {str(i): call_counts.count(i) for i in sorted(set(call_counts))}}
    write_json(directory / 'review-summary.json', summary)
    return summary


def freeze_selection(dev_run, selected_trial, reason, output):
    dev_run, output = Path(dev_run), Path(output)
    if output.exists():
        raise ValueError('Selection already exists; do not overwrite a frozen decision')
    run = json.loads((dev_run / 'run.json').read_text())
    summaries = json.loads((dev_run / 'summary.json').read_text())
    if run['split'] != 'dev' or run['suite'] != 'agent':
        raise ValueError('Selection requires a completed dev agent experiment')
    if {t['name'] for t in run['trials']} != {t['trial'] for t in summaries}:
        raise ValueError('Dev experiment is incomplete')
    if selected_trial not in {t['trial'] for t in summaries} or not reason.strip():
        raise ValueError('Choose a measured trial and provide a reason')
    if run['trials_sha256'] != digest(ROOT / 'config/day07_trials.json'):
        raise ValueError('Trial configuration changed since dev')
    for name in ['dense_baseline', selected_trial]:
        aggregate_reviews(dev_run / name)
    decision = {'selected_trial': selected_trial, 'baseline': 'dense_baseline', 'reason': reason,
                'dev_run': str(dev_run), 'dev_run_sha256': digest(dev_run / 'run.json'),
                'trials_sha256': run['trials_sha256'], 'corpus_sha256': run['index_identity']['corpus_sha256'],
                'benchmark_freeze_sha256': run['benchmark_freeze_sha256'],
                'code_fingerprint': code_fingerprint(), 'model': run['model'],
                'selection_rule': run['selection_rule']}
    write_json(output, decision)
    return decision
