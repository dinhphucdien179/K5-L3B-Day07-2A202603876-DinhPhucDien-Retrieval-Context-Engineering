"""Author/freeze Day07 questions from the bundled corpus, before experimentation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAY06 = ROOT / 'Day06/K5-L3B-Day06-2A202603876-DataIngestionEngineering'
OUT = ROOT / 'data/day07'


def write(name, obj):
    path = OUT / name
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists() and any(OUT.iterdir()):
        raise SystemExit('Benchmark already exists; refusing to overwrite a frozen split')
    OUT.mkdir(parents=True, exist_ok=True)
    pages = {row['page']: row for row in map(json.loads, (DAY06 / 'data/pages.jsonl').read_text().splitlines())}
    source_id = pages[61]['document_id']
    old = json.loads((DAY06 / 'benchmark/questions.json').read_text())
    dev = []
    for row in old:
        if row['split'] != 'dev':
            continue
        alternatives = [row, *row.get('gold_alternatives', [])]
        gold = [{'source_id': g['gold_source_id'], 'source': pages[g['gold_page']]['source'],
                 'page': g['gold_page'], 'evidence': g['evidence_quote'],
                 'start': g['evidence_start'], 'end': g['evidence_end']} for g in alternatives]
        item = {'id': 'd' + row['id'][1:], 'split': 'dev', 'answerable': True,
                'question': row['question'], 'expected_answer': row['expected_answer'],
                'gold': gold, 'origin': 'Day06 dev; primary and alternative evidence preserved'}
        if row.get('filter'):
            item.update(filter=row['filter'], filter_context=row['filter_context'])
        dev.append(item)

    def answerable(cid, page, question, answer, quote):
        start = pages[page]['text'].index(quote)
        return {'id': cid, 'split': 'test', 'answerable': True, 'question': question, 'expected_answer': answer,
                'gold': [{'source_id': source_id, 'source': pages[page]['source'], 'page': page,
                          'evidence': quote, 'start': start, 'end': start+len(quote)}],
                'origin': 'New Day07 holdout; not a paraphrase of Day06 test q16-q20'}

    test = [
        answerable('t01', 76, 'How did the share of households whose most educated member had lower-secondary education or less change between 2010 and 2020?',
                   'It fell from half of all households in 2010 to about 44 percent in 2020.',
                   'In 2010, in half of all households, the\nmaximum level of education of any member was lower-\nsecondary level or less (Figure 2.3). By 2020, this share fell\nto about 44 percent of all households.'),
        answerable('t02', 78, 'How do wages paid by foreign companies compare with wages paid by domestic firms in the report?',
                   'Foreign companies pay double the wages of domestic firms.',
                   'Foreign companies also\npay double the wages that domestic firms do.'),
        answerable('t03', 84, 'Approximately what share of households received any pension income in 2020?',
                   'About 10 percent of households received any form of pension in 2020.',
                   'Pension income increased over the last decade, but only about\n10 percent of households received any form of pension in\n2020.'),
        answerable('t04', 86, 'How did the share of households with at least one member receiving wages or salaries change from 2010 to 2020?',
                   'It rose from 53.3 percent in 2010 to 64.7 percent in 2020.',
                   'From 2010 to 2020, the\nshare of households that have at least one member receiving\nwages or salaries has increased from 53.3 percent to 64.7\npercent (Figure 2.15).'),
        answerable('t05', 93, 'What rural and urban poverty rates does the report give for 2010 and 2020?',
                   'Rural and urban rates were 22 percent and 4.5 percent in 2010, versus 7 percent and 1.5 percent in 2020, respectively.',
                   'In 2010, rural and urban poverty rates were 22 and 4.5\npercent respectively, compared to 7 and 1.5 percent in 2020.')
    ]

    def absent(cid, split, question, reason):
        return {'id': cid, 'split': split, 'answerable': False, 'question': question,
                'expected_behavior': 'search_and_abstain', 'absence_reason': reason,
                'absence_audit': 'Scope: all 39 indexed pages, not the complete 232-page PDF. Corpus read/keyword inspection before agent runs; check again when grading.'}

    dev += [
        absent('du01', 'dev', 'What was the observed national poverty rate measured by a household survey actually conducted in calendar year 2025?',
               'The indexed 2022 report discusses earlier surveys and some projections. Mentions of 2025 are not observations from a survey conducted in 2025; no such observed result is in this corpus.'),
        absent('du02', 'dev', 'What is the exact 2020 VHLSS income and sampling weight of household ID VN2020-000001?',
               'The corpus contains published aggregates and methodological explanations, not respondent-level microdata. That household ID and its income/weight record are absent from every indexed page.')
    ]
    test += [
        absent('tu01', 'test', 'What share of Vietnamese households actually received pension income during calendar year 2026?',
               'The indexed report predates 2026 and contains no 2026 observed pension-coverage result; the string 2026 does not occur in the corpus. Historical 2020 pension coverage cannot answer this question.'),
        absent('tu02', 'test', 'What are the lower and upper limits of the 95 percent confidence interval for the 2020 pension-income household share?',
               'The text gives an approximate 2020 pension share, but no 95 percent confidence interval bounds for that estimate. Page 84 and all other indexed pages lack the requested interval; do not infer it from the sample size or invent bounds.')
    ]
    frozen = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'dev_sha256': write('dev.json', dev), 'test_sha256': write('test.json', test),
              'corpus_sha256': hashlib.sha256((DAY06 / 'data/pages.jsonl').read_bytes()).hexdigest(),
              'split_rationale': 'Reuse Day06 dev, replace already exposed Day06 test with five distinct new questions; freeze before Day07 experiments.',
              'gold_policy': 'Gold/expected answers are evaluator-only. Agent receives question and optional user-provided filter.',
              'review_policy': 'AI-assisted authored labels require source inspection; substring/offset checks do not replace semantic review.'}
    write('freeze.json', frozen)
    print(f'Frozen {len(dev)} dev and {len(test)} test questions')


if __name__ == '__main__': main()
