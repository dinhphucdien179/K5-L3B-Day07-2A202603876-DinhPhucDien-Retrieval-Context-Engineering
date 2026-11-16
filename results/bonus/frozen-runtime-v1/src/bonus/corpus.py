"""Whole-document text/layout index and reproducible, source-linked page images."""
import hashlib
import fcntl
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DAY06 = ROOT / 'Day06/K5-L3B-Day06-2A202603876-DataIngestionEngineering'
DATA = ROOT / 'data/bonus'
CACHE = ROOT / '.cache/bonus'
SOURCE = json.loads((DAY06 / 'data/sources.json').read_text())[0]
SHA = SOURCE['expected_sha256']
URL = SOURCE['url']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def source_pdf():
    original = DAY06 / f'.cache/day6/http/{SHA}.pdf'
    path = original if original.exists() else CACHE / 'source.pdf'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=120) as r:
            raw = r.read()
        if hashlib.sha256(raw).hexdigest() != SHA:
            raise ValueError('Downloaded PDF checksum does not match pinned source')
        path.write_bytes(raw)
    if digest(path) != SHA:
        raise ValueError('PDF checksum mismatch')
    return path


def page_image(page, width=1600):
    if type(page) is not int or not 1 <= page <= 232:
        raise ValueError('Invalid physical page')
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f'p{page:03d}-w{width}.jpg'
    with target.with_suffix('.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not target.exists():
            subprocess.run(['pdftoppm', '-f', str(page), '-l', str(page), '-singlefile',
                            '-scale-to-x', str(width), '-scale-to-y', '-1', '-jpeg',
                            '-jpegopt', 'quality=90', str(source_pdf()), str(target.with_suffix(''))],
                           check=True, capture_output=True)
    return target


def prepare(reextract=False, amend_catalog=False):
    """Index all 232 pages, including sparse pages; exclude no body pages."""
    CACHE.mkdir(parents=True, exist_ok=True)
    pdf = source_pdf()
    if (DATA/'manifest.json').exists() and not reextract:
        manifest=json.loads((DATA/'manifest.json').read_text())
        if digest(DATA/'corpus.jsonl')!=manifest['corpus_sha256']:
            raise ValueError('Prepared index checksum mismatch')
        return manifest
    layout_path, bbox_path = CACHE / 'layout.txt', CACHE / 'bbox.html'
    subprocess.run(['pdftotext', '-layout', str(pdf), str(layout_path)], check=True)
    subprocess.run(['pdftotext', '-bbox-layout', str(pdf), str(bbox_path)], check=True)
    layouts = layout_path.read_text().split('\f')[:232]
    ns = {'x': 'http://www.w3.org/1999/xhtml'}
    # PDF glyphs can yield XML-forbidden control characters in Poppler output.
    xml = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', bbox_path.read_text())
    xml_pages = ET.fromstring(xml).findall('.//x:page', ns)
    if len(layouts) != 232 or len(xml_pages) != 232:
        raise ValueError('Unexpected source page count')
    # The publication's lists cover all numbered tables/figures, not benchmark pages.
    entries = []
    toc = '\n'.join(layouts[10:16])
    lines = toc.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r'\s*(Figure|Table)\s+([ABO\d][\d.]*\d)\.?\s+(.*)', line)
        if not match:
            continue
        kind, label, tail = match.groups()
        j = i + 1
        while not re.search(r'\s\d+\s*$', tail) and j < len(lines):
            if re.match(r'\s*(Figure|Table|Chapter|List)\b', lines[j]):
                break
            tail += ' ' + lines[j].strip()
            j += 1
        pm = re.search(r'\s(\d+)\s*$', tail)
        if pm:
            printed = int(pm.group(1))
            entries.append({'kind': kind.lower(), 'label': label,
                            'caption': re.sub(r'[\x00-\x1f]', '', tail[:pm.start()]).strip(),
                            'page': printed + 20, 'printed_page': printed})
    if len(entries) != 205 or len({(e['kind'], e['label']) for e in entries}) != 205:
        raise ValueError(f'Expected 171 figure and 34 table TOC entries, got {len(entries)}')
    # The original TOC has a few stale box numbers/page numbers. The source-page
    # caption, not a silently assumed TOC offset, is the canonical object locator.
    body_captions=[]
    for page,xp in enumerate(xml_pages,1):
        if page<21:continue
        for line in xp.findall('.//x:line',ns):
            s=' '.join(w.text or '' for w in line.findall('x:word',ns))
            m=re.match(r'^(Figure|Table)\s+([ABO\d][\d.]*\d)\.?\s+(.*)',s)
            if m:
                body_captions.append({'kind':m[1].lower(),'label':m[2],'caption_line':m[3],
                    'page':page,'caption_bbox':[float(line.attrib[a]) for a in ('xMin','yMin','xMax','yMax')]})
    corrections=[]
    compact=lambda s:re.sub(r'[^a-z0-9]','',s.lower())
    for entry in entries:
        exact=[c for c in body_captions if c['kind']==entry['kind'] and c['label']==entry['label'] and c['page']==entry['page']]
        if exact:continue
        candidates=[c for c in body_captions if c['kind']==entry['kind'] and
                    compact(c['caption_line'])[:22]==compact(entry['caption'])[:22]]
        if len(candidates)==1:
            c=candidates[0]
            corrections.append({'kind':entry['kind'],'caption':entry['caption'],
                'toc_label':entry['label'],'toc_page':entry['page'],
                'actual_label':c['label'],'actual_page':c['page']})
            entry.update(toc_label=entry['label'],toc_page=entry['page'],
                         label=c['label'],page=c['page'],printed_page=c['page']-20)
    records, page_audit = [], []
    for n, (text, xp) in enumerate(zip(layouts, xml_pages), 1):
        width, height = float(xp.attrib['width']), float(xp.attrib['height'])
        page_audit.append({'page': n, 'layout_characters': len(text.strip()),
                           'indexed': True, 'bbox': [0, 0, width, height],
                           'sparse_text': len(text.strip()) < 100,
                           'policy': 'Retain text when present; original page image remains retrievable'})
        captions = [e for e in entries if e['page'] == n]
        # Full-page context avoids cutting table headers, formulae and conditions.
        records.append({'id': f'p{n:03d}', 'kind': 'page', 'page': n,
                        'printed_page': n-20 if n >= 21 else None,
                        'source': URL, 'source_sha256': SHA, 'text': text,
                        'metadata': {}, 'bbox': [0, 0, width, height],
                        'references': [f"{e['kind'].title()} {e['label']} {e['caption']}" for e in captions]})
        for entry in captions:
            marker = f"{entry['kind'].title()} {entry['label']}"
            caption_box = None
            for line in xp.findall('.//x:line', ns):
                s = ' '.join(w.text or '' for w in line.findall('x:word', ns))
                if s.startswith(marker + '.') or s.startswith(marker + ' '):
                    caption_box = [float(line.attrib[a]) for a in ('xMin','yMin','xMax','yMax')]
                    break
            records.append({'id': f"p{n:03d}-{entry['kind']}-{entry['label']}", **entry,
                            'source': URL, 'source_sha256': SHA, 'metadata': {},
                            'text': f"{marker}. {entry['caption']}\n{text}",
                            'caption_bbox': caption_box, 'bbox': [0, 0, width, height],
                            'bbox_scope': 'Full page; caption_bbox locates named object. No inferred crop boundary.'})
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / 'corpus.jsonl'
    raw = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records)
    old_freeze=None
    if path.exists() and path.read_text() != raw and (DATA/'freeze.json').exists():
        runs=list((ROOT/'results/bonus').glob('*/run.json'))
        if not amend_catalog or runs:
            raise ValueError('Corpus changed: use a versioned dataset instead of overwriting; catalog fixes allowed only before benchmark runs')
        old_freeze=json.loads((DATA/'freeze.json').read_text())
        for split in ['dev','test']:
            for case in json.loads((DATA/f'{split}.json').read_text()):
                for gold in case.get('gold',[]):
                    if not any(r['id']==gold['id'] and r['page']==gold['page'] for r in records):
                        raise ValueError('Catalog correction would invalidate existing gold')
    path.write_text(raw)
    version = subprocess.run(['pdftotext','-v'],capture_output=True,text=True).stderr.splitlines()[0]
    manifest = {'source': {k: SOURCE[k] for k in ('title','url','expected_sha256','physical_pdf_pages','license_or_permission')},
                'pages': page_audit, 'indexed_pages': 232, 'omitted_pages': [],
                'page_records': 232, 'figure_records': sum(e['kind']=='figure' for e in entries),
                'table_records': sum(e['kind']=='table' for e in entries),
                'corpus_sha256': digest(path), 'extraction': version,
                'source_catalog_corrections':corrections,
                'method': 'Poppler layout text + word coordinates + whole-page rendering, vision at query time; no generated captions indexed',
                'limitations': ['No cell-structured table export; layout rows and original image are both supplied.',
                               'No automatic diagram interpretation during indexing; vision reads retrieved source pages.',
                               'Unnumbered visuals remain available through their full page; no separate object IDs.',
                               'Full-page bounds are conservative; precise caption boxes are recorded when detected.',
                               'Text-only sparse pages retained; extraction counts do not measure semantic fidelity.']}
    write(DATA / 'manifest.json', manifest)
    if old_freeze:
        from datetime import datetime,timezone
        amendment={'amended_utc':datetime.now(timezone.utc).isoformat(),
            'reason':'Source TOC contains stale table numbers/page locators; canonical locators verified against actual page captions before any benchmark execution.',
            'previous_freeze':old_freeze,'new_corpus_sha256':digest(path),
            'dev_test_questions_and_gold_unchanged':True,'corrections':corrections,
            'prior_smokes':'smoke-01/02 used the earlier source catalog; retained unchanged and not benchmark evidence.'}
        write(DATA/'catalog-amendment.json',amendment)
        old_freeze.update(corpus_sha256=digest(path),catalog_amendment_sha256=digest(DATA/'catalog-amendment.json'))
        write(DATA/'freeze.json',old_freeze)
    return manifest


def load_corpus():
    path = DATA / 'corpus.jsonl'
    manifest = json.loads((DATA / 'manifest.json').read_text())
    if digest(path) != manifest['corpus_sha256']:
        raise ValueError('Corpus checksum mismatch')
    return [json.loads(l) for l in path.read_text().splitlines()]
