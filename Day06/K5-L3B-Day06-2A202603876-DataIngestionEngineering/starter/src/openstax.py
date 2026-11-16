"""Read public book metadata embedded in HTML; never execute website JavaScript."""
import json
import re
from lxml import html

BOOK_SLUG = 'introduction-python-programming'
BASE_URL = f'https://openstax.org/books/{BOOK_SLUG}/pages/'
DOCUMENT_ID = 'openstax-introduction-python-programming'


def public_state(raw):
    tree = html.fromstring(raw)
    scripts = tree.xpath('//script/text()')
    script = next((s for s in scripts if s.strip().startswith('window.__PRELOADED_STATE__ =')), None)
    if script is None:
        raise ValueError('OpenStax public page state missing; inspect page structure')
    state = json.JSONDecoder().raw_decode(script.split('=', 1)[1].lstrip())[0]
    return state['content']


def plain_title(value):
    return ' '.join(html.fromstring('<div>' + value + '</div>').text_content().split())


def select_sources(raw):
    """Numbered instructional sections from chapters 1–6; omit intro/summary/career material."""
    content = public_state(raw)
    book = content['book']
    excluded = {'1-1-background', '1-8-why-python', '2-8-python-careers'}
    result = []
    for chapter in book['tree']['contents']:
        if chapter.get('toc_type') != 'chapter':
            continue
        number = chapter['slug'].split('-', 1)[0]
        if not number.isdigit() or not 1 <= int(number) <= 6:
            continue
        for section in chapter['contents']:
            slug = section['slug']
            if not re.match(r'^\d+-\d+-', slug) or slug.endswith('chapter-summary') or slug in excluded:
                continue
            title = plain_title(section['title'])
            section_number = re.match(r'\d+\.\d+', title).group()
            result.append({
                'source_id': 'openstax-python-' + section_number.replace('.', '-'),
                'document_id': DOCUMENT_ID, 'title': book['title'] + ' — ' + title,
                'url': BASE_URL + slug, 'unit_id': slug,
                'license_or_permission': 'CC BY-NC-SA 4.0; website additionally lists an AI-use permission notice. Embedding/retrieval permission not established.',
                'license_url': book['license']['url'].replace('http:', 'https:'),
                'book_id': book['id'], 'book_content_version': book['contentVersion'],
                'archive_version': book['archiveVersion'], 'page_id': section['id'].rstrip('@'),
                'metadata': {'chapter': number, 'chapter_title': plain_title(chapter['title']),
                             'section': section_number, 'section_title': title, 'language': book['language'],
                             'content_license': 'CC BY-NC-SA 4.0',
                             'attribution': 'Access for free at ' + BASE_URL + slug}
            })
    if len(result) < 30:
        raise ValueError('Selected table of contents contains fewer than 30 candidate units')
    return result, {'title': book['title'], 'book_id': book['id'],
                    'content_version': book['contentVersion'], 'archive_version': book['archiveVersion'],
                    'revised_at': book.get('revised'), 'excluded_section_slugs': sorted(excluded)}


def verify_source(raw, source):
    """Reject metadata drift across page fetches from a mutable web edition."""
    content = public_state(raw)
    book, page = content['book'], content['page']
    if book['id'] != source['book_id'] or book['contentVersion'] != source['book_content_version']:
        raise ValueError('OpenStax book version changed during corpus acquisition')
    if page['id'].split('@')[0] != source['page_id']:
        raise ValueError('Fetched page does not match the selected TOC page ID')
