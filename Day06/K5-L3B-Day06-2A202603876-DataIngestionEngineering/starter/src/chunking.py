"""Deterministic chunks with exact offsets into the normalized source."""
import hashlib
import re
from .models import Chunk, DocumentPage


def _chunk(page, start, end, method):
    while start < end and page.text[start].isspace():
        start += 1
    while end > start and page.text[end-1].isspace():
        end -= 1
    text = page.text[start:end]
    identity = f'{page.document_id}\0{page.page}\0{method}\0{start}\0{end}\0{text}'
    return Chunk(hashlib.sha256(identity.encode()).hexdigest(), page.document_id,
                 page.source, page.page, text, {**page.metadata, 'char_start': start, 'char_end': end})


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split into overlapping windows and retain provenance."""
    if size < 1 or not 0 <= overlap < size:
        raise ValueError('Require size > overlap >= 0')
    result = []
    for start in range(0, len(page.text), size - overlap):
        end = min(start + size, len(page.text))
        if page.text[start:end].strip():
            result.append(_chunk(page, start, end, f'fixed:{size}:{overlap}'))
        if end == len(page.text):
            break
    return result


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group paragraphs, split oversized paragraphs and retain provenance."""
    if max_size < 1:
        raise ValueError('max_size must be positive')
    spans = [m.span() for m in re.finditer(r'\S(?:.*?\S)?(?=\n\s*\n|\Z)', page.text, re.S)]
    result = []
    pending = None
    for start, end in spans:
        if pending and end - pending[0] <= max_size:
            pending = (pending[0], end)
            continue
        if pending:
            result.append(_chunk(page, *pending, f'paragraph:{max_size}'))
            pending = None
        while end - start > max_size:
            # Prefer a word boundary; oversized unbroken strings still make progress.
            cut = page.text.rfind(' ', start + max_size // 2, start + max_size + 1)
            if cut <= start:
                cut = start + max_size
            result.append(_chunk(page, start, cut, f'paragraph:{max_size}'))
            start = cut
            while start < end and page.text[start].isspace():
                start += 1
        if start < end:
            pending = (start, end)
    if pending:
        result.append(_chunk(page, *pending, f'paragraph:{max_size}'))
    return result
