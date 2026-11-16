"""Evidence metrics; human coherence/grounding labels are never invented."""
from collections import defaultdict
from typing import Any
from .ingestion import normalize_text


def _compact(text):
    return ' '.join(normalize_text(text).split())


def gold_evidence(question):
    primary = {field: question[field] for field in ('gold_source_id', 'gold_page', 'evidence_quote')}
    for field in ('evidence_start', 'evidence_end', 'gold_text_sha256'):
        if field in question:
            primary[field] = question[field]
    return [primary, *question.get('gold_alternatives', [])]


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check source/page and enough gold evidence; keep hit@1 and hit@3 trace.

    Accept any documented alternative gold evidence. Do not infer human grounding
    or chunk coherence labels from exact string match.
    """
    alternatives = gold_evidence(question)
    labels = []
    for hit in hits[:3]:
        metadata = hit['metadata']
        labels.append(any(metadata['document_id'] == gold['gold_source_id']
                          and str(metadata['page']) == str(gold['gold_page'])
                          and _compact(gold['evidence_quote']) in _compact(hit['text'])
                          for gold in alternatives))
    return {'question_id': question['id'], 'split': question['split'], 'question': question['question'],
            'gold': alternatives, 'expected_answer': question['expected_answer'], 'hits': hits[:3],
            'evidence_match': labels, 'hit1': bool(labels and labels[0]), 'hit3': any(labels),
            'label_method': 'normalized evidence substring + source/page; equivalents need human review'}


def summarize(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate Hit@1 and Evidence Hit@3 by strategy and split."""
    groups = defaultdict(list)
    for trace in traces:
        groups[(trace['strategy'], trace['split'])].append(trace)
    return [{'strategy': strategy, 'split': split, 'n': len(rows),
             'hit1_count': sum(row['hit1'] for row in rows), 'hit3_count': sum(row['hit3'] for row in rows),
             'hit1': sum(row['hit1'] for row in rows)/len(rows),
             'hit3': sum(row['hit3'] for row in rows)/len(rows)}
            for (strategy, split), rows in sorted(groups.items())]
