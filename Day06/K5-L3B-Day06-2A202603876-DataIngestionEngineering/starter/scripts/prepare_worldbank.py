"""Verify the pinned World Bank report and prepare explicit physical-page sources."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from src.fetching import SnapshotFetcher
from src.ingestion import normalize_text
from src.runtime import RuntimeConfig, Telemetry, atomic_json, atomic_write, exclusive_run

ROOT = Path(__file__).resolve().parents[2]
GUID = '099115004242216918'
PDF_SHA256 = '6b2e5b40b08a3454f2265564e781bbf7bc0038ba37cb87ca32e1446b8f6b4e00'
API_URL = f'https://search.worldbank.org/api/v3/wds?format=json&rows=5&guid={GUID}'
PDF_URL = (f'https://documents1.worldbank.org/curated/en/{GUID}/pdf/'
           'P176261155e1805e1bd6e14287197d61965ce02eb562.pdf')
LICENSE_URL = 'https://creativecommons.org/licenses/by/3.0/igo/'
TITLE = 'From the Last Mile to the Next Mile — 2022 Vietnam Poverty and Equity Assessment'
CHAPTERS = {
    '1': ('Taking stock of welfare trends over a dynamic decade',
          [page for page in range(45, 66) if page not in {48, 53}]),
    '2': ('A review of the drivers of poverty reduction',
          [page for page in range(75, 98) if page not in {88, 90, 97}]),
}


def prepare(root, runtime, output, cache, refresh=False):
    from pypdf import PdfReader
    with SnapshotFetcher(cache / 'http', runtime) as fetcher:
        api = fetcher.fetch(API_URL, refresh=refresh, content_type='application/json')
        payload = json.loads(Path(api['body_path']).read_bytes())
        documents = [value for key, value in payload.get('documents', {}).items()
                     if key != 'facets' and isinstance(value, dict) and value.get('guid') == GUID]
        if len(documents) != 1:
            raise ValueError('World Bank API must return the exact pinned report GUID')
        document = documents[0]
        if document.get('lang') != 'English' or document.get('repnb') != '170511':
            raise ValueError('World Bank report language/number changed')
        advertised = urlsplit(document['pdfurl'])
        if advertised.path != urlsplit(PDF_URL).path or advertised.hostname not in {
            'documents.worldbank.org', 'documents1.worldbank.org'
        }:
            raise ValueError('API PDF identity differs from the selected canonical PDF')
        pdf = fetcher.fetch(PDF_URL, refresh=refresh, content_type='application/pdf')
    if pdf['sha256'] != PDF_SHA256:
        raise ValueError('Report PDF changed; review source and benchmark before repinning')
    reader = PdfReader(pdf['body_path'])
    if len(reader.pages) != 232:
        raise ValueError('Pinned report physical page count changed')
    rights = normalize_text(reader.pages[2].extract_text() or '')
    if 'Creative Commons Attribution 3.0 IGO license (CC BY 3.0 IGO)' not in rights:
        raise ValueError('Expected CC BY license notice absent from physical PDF page 3')
    toc = normalize_text(reader.pages[8].extract_text() or '')
    if 'Chapter 1. Taking stock of welfare trends over a dynamic decade 24' not in toc:
        raise ValueError('Expected chapter identity absent from physical PDF page 9')
    if 'Chapter 2. A review of the drivers of poverty reduction 54' not in toc:
        raise ValueError('Expected second chapter identity absent from contents')
    selections, inspection = [], []
    for chapter, (chapter_title, numbers) in CHAPTERS.items():
        for number in numbers:
            runtime.guard('verify-worldbank-page')
            text = normalize_text(reader.pages[number - 1].extract_text() or '')
            printed = number - 20
            if not re.search(rf'(?:Next Mile\s+{printed}\b|\b{printed}\s+2022 Vietnam)', text[:300]):
                raise ValueError(f'Printed/physical page mapping not verified: {number}')
            if len(text) < 1500:
                raise ValueError(f'Selected page unexpectedly short: {number}')
            metadata = {'chapter': chapter, 'chapter_title': chapter_title, 'printed_page': printed}
            selections.append({'page': number, 'metadata': metadata})
            inspection.append({'physical_page': number, 'printed_page': printed,
                               'chapter': chapter, 'normalized_characters': len(text),
                               'review': 'Main-text page; excluded cover/contents/references and selected figure-only pages.'})
    source = {
        'source_id': 'worldbank-report-170511',
        'document_id': 'worldbank-vietnam-poverty-equity-2022',
        'title': TITLE, 'format': 'pdf', 'url': PDF_URL,
        'api_url': API_URL, 'api_metadata_sha256': api['sha256'],
        'expected_sha256': PDF_SHA256, 'physical_pdf_pages': 232,
        'license_or_permission': 'Creative Commons Attribution 3.0 IGO (CC BY 3.0 IGO), report physical page 3',
        'license_url': LICENSE_URL,
        'metadata': {'year': 2022, 'language': 'English', 'document_type': 'Poverty Assessment',
                     'country': 'Viet Nam', 'report_number': '170511',
                     'api_document_date': document['docdt'], 'version': PDF_SHA256},
        'pages': selections,
    }
    spec = {
        'title': TITLE + ' — selected main-text pages of chapters 1–2',
        'rights': {
            'content_license_observed': 'CC BY 3.0 IGO', 'license_url': LICENSE_URL,
            'ai_use_permission': 'covered_by_published_license',
            'basis': 'The report physical page 3 expressly permits copying, transmission and adaptation under CC BY 3.0 IGO. This records reliance on that published license, not bespoke World Bank approval.',
            'permission_notice_url': PDF_URL + '#page=3',
        },
        'counting_rule': 'One selected physical PDF page per source unit, with verified printed-page metadata. Select main narrative pages from chapters 1–2; exclude covers, contents, references, annexes and figure/table-only pages 48,53,88,90,97. No duplication or artificial padding.',
        'extraction_limits': [
            'pypdf plain extraction preserves reading order better than layout mode in this two-column report; geometric paragraph boundaries are not reconstructed.',
            'Headers, figure captions and some table/axis text remain in extraction; no bitmap figures, photographs or logos are redistributed. Benchmark evidence is from explanatory prose.',
            'Some PDF kerning produces spaces inside words and line breaks/hyphenation remain; offsets refer to the exact normalized corpus, not guessed corrected wording.',
            'The World Bank TXT is labelled uncorrected OCR and was used only for an independent feasibility check, not as the primary corpus or physical-page mapping.',
        ],
        'benchmark_split': {
            'dev_chapters': ['1'], 'test_chapters': ['2'],
            'split_method': '15 dev questions about chapter 1 and 5 test questions about chapter 2; all selected pages remain searchable for A/B/C.',
            'limitations': ['Same report and related poverty concepts can overlap across chapters.',
                           'Five test questions are illustrative and do not establish a general ranking.',
                           'Questions prepared with AI-assisted source reading and exact-span checks; learner review and human audit remain distinct.'],
        },
    }
    # Publish only after API identity, raw checksum, license, TOC and page checks pass.
    atomic_write(root / 'data/worldbank-api.json', Path(api['body_path']).read_bytes())
    atomic_write(root / 'data/source-rights.txt', (rights + '\n').encode())
    atomic_json(root / 'data/sources.json', [source])
    atomic_json(root / 'data/source-selection.json', {
        'selected_at': datetime.now(timezone.utc).isoformat(),
        'api_snapshot': {key: value for key, value in api.items() if key != 'body_path'},
        'pdf_snapshot': {key: value for key, value in pdf.items() if key != 'body_path'},
        'physical_pdf_pages': len(reader.pages), 'selected_pages': inspection,
        'excluded_in_main_ranges': {'48': 'Table-only page', '53': 'Map/figure-dominated page',
                                    '88': 'Figure-dominated page', '90': 'Figure-dominated page',
                                    '97': 'Formula-dominated methodological continuation'},
        'date_note': 'Citation/copyright report year is 2022; API document date is retained separately and is not overwritten.',
    })
    atomic_json(root / 'data/corpus-spec.json', spec)
    snapshots = {name: {**record, 'body_path': str(Path(record['body_path']).relative_to(root))}
                 for name, record in (('pdf', pdf), ('api', api))}
    atomic_json(output / 'preparation.json', {'selected_pages': len(selections), **snapshots,
                                            'rights_basis': spec['rights']})
    return {'selected_pages': len(selections), 'pdf_bytes': pdf['bytes'], 'pdf_sha256': pdf['sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    from src.runtime import require_python
    require_python()
    config = json.loads((ROOT / 'starter/config/pipeline.json').read_text())
    runtime = RuntimeConfig(**config['runtime'])
    hardware = runtime.apply_threads()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    output = ROOT / 'results' / (stamp + '-prepare-worldbank')
    with exclusive_run(ROOT / config['cache'] / 'pipeline.lock'):
        atomic_json(output / 'run.json', {'command': 'prepare-worldbank', 'hardware': hardware})
        telemetry = Telemetry(output / 'telemetry.jsonl', runtime)
        try:
            with telemetry.stage('prepare-worldbank'):
                result = prepare(ROOT, runtime, output, ROOT / config['cache'], args.refresh)
            atomic_json(output / 'status.json', {'status': 'ok', 'result': result})
            print(json.dumps({'artifacts': str(output.relative_to(ROOT)), **result}, indent=2))
        finally:
            telemetry.close()


if __name__ == '__main__':
    main()
