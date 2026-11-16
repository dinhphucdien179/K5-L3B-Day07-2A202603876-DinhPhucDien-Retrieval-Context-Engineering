"""Streaming readers; preserve paragraphs and physical PDF page numbers."""
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Iterator
from .models import DocumentPage

NORMALIZATION_VERSION = 'NFC-paragraphs-code-v2'


def iter_selected_pdf_pages(path: Path, source: dict, guard=None) -> Iterator[DocumentPage]:
    """Extract explicit physical pages in declared order, never all-page text.

    Source selection excludes covers, contents and references before this reader.
    Each page's metadata is supplied from verified document headings/publication data.
    """
    from pypdf import PdfReader
    selected = source.get('pages')
    if not isinstance(selected, list) or not selected:
        raise ValueError('PDF source requires a nonempty explicit pages list')
    numbers = []
    for item in selected:
        if (not isinstance(item, dict) or type(item.get('page')) is not int
            or item['page'] < 1 or not isinstance(item.get('metadata'), dict)):
            raise ValueError('Each PDF selection requires a positive physical page and metadata object')
        numbers.append(item['page'])
    if len(numbers) != len(set(numbers)):
        raise ValueError('Duplicate selected physical PDF page')
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF sources are not supported')
    if max(numbers) > len(reader.pages):
        raise ValueError('Selected physical page exceeds PDF page count')
    for item in selected:
        if guard:
            guard('parse-pdf-page:before')
        number = item['page']
        try:
            text = normalize_text(reader.pages[number - 1].extract_text() or '')
        except Exception:
            logging.exception('Cannot read selected PDF document=%s page=%s', source['document_id'], number)
            raise
        if len(text) < 200:
            raise ValueError(f'Selected PDF page {number} contains fewer than 200 normalized characters; '
                             'select a useful extractable page or record an OCR workflow')
        if guard:
            guard('parse-pdf-page:after')
        metadata = {**source.get('metadata', {}), **item['metadata']}
        yield DocumentPage(source['document_id'], source['url'], number, text, metadata)


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract each physical page; keep its page number and source.

    Detect and record pages with no text. OCR, when needed, is a separate step.
    """
    from pypdf import PdfReader
    result = []
    for number, page in enumerate(PdfReader(path).pages, 1):
        try:
            text = normalize_text(page.extract_text() or '')
        except Exception:
            logging.exception('Cannot read PDF document=%s page=%s', document_id, number)
            raise
        if not text:
            logging.warning('Empty PDF page document=%s page=%s', document_id, number)
        result.append(DocumentPage(document_id, source, number, text))
    return result


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while preserving paragraph boundaries."""
    text = unicodedata.normalize('NFC', text).replace('\r\n', '\n').replace('\r', '\n')
    lines = []
    code = False
    for line in text.split('\n'):
        if line.strip() == '```':
            code = not code
            lines.append('```')
        elif code:
            lines.append(line.rstrip())
        else:
            lines.append(re.sub(r'[^\S\n]+', ' ', line).strip())
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


class OpenStaxHTML:
    """libxml2 parser; only walk element boundaries in Python, never HTML characters."""
    def __init__(self):
        self.parts = []

    def feed(self, html):
        self.parts.append(html)

    def text(self):
        from lxml import html
        tree = html.fromstring(''.join(self.parts))
        roots = tree.xpath('//*[@data-type="page"]')
        if len(roots) != 1:
            raise ValueError('Expected one OpenStax content container; challenge or changed page structure')
        root = roots[0]
        for element in root.xpath('.//script | .//style | .//nav | .//*[@hidden] | .//*[@aria-hidden="true"]'):
            element.drop_tree()
        for element in root.xpath('.//pre'):
            code = element.text_content()
            for child in list(element):
                element.remove(child)
            element.text = '```\n' + code.strip('\n') + '\n```'
        for element in root.xpath('.//p | .//div | .//section | .//li | .//pre | .//h1 | .//h2 | .//h3 | .//h4 | .//tr | .//br'):
            element.text = '\n\n' + (element.text or '')
            element.tail = '\n\n' + (element.tail or '')
        result = normalize_text(root.text_content())
        if len(result) < 200:
            raise ValueError('OpenStax page contains too little text')
        return result


def load_pages(path: Path, max_line_bytes: int = 2 * 1024 * 1024) -> Iterator[DocumentPage]:
    """Read normalized corpus JSONL without loading the whole corpus into RAM."""
    with path.open('rb') as stream:
        number = 0
        while raw := stream.readline(max_line_bytes + 1):
            number += 1
            if len(raw) > max_line_bytes:
                raise ValueError(f'Corpus line {number} exceeds size budget')
            value = json.loads(raw)
            page = DocumentPage(**value)
            if (not isinstance(page.document_id, str) or not page.document_id.strip()
                or not isinstance(page.source, str) or not page.source.strip()
                or type(page.page) not in {int, str}
                or (isinstance(page.page, int) and page.page < 1)
                or (isinstance(page.page, str) and not page.page.strip())
                or not isinstance(page.text, str) or not isinstance(page.metadata, dict)):
                raise ValueError(f'Invalid provenance on line {number}')
            page.text = normalize_text(page.text)
            if not page.text:
                raise ValueError(f'Empty content on line {number}')
            yield page
