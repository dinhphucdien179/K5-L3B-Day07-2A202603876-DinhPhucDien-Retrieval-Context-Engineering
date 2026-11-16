"""Prepare deterministic coherence review records without assigning human labels."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from src.runtime import RuntimeConfig, atomic_json, atomic_write, exclusive_run, lab_path, require_python

ROOT = Path(__file__).resolve().parents[2]
SELECTION = 'Among chunks covering the frozen anchor [char_start, char_end), choose the smallest char_start; ties use char_end then chunk_id.'


def choose_covering(chunks, position):
    """Use half-open source offsets; make overlap selection independent of order."""
    covering = sorted((chunk for chunk in chunks
                       if chunk.metadata['char_start'] <= position < chunk.metadata['char_end']),
                      key=lambda chunk: (chunk.metadata['char_start'], chunk.metadata['char_end'], chunk.chunk_id))
    if not covering:
        raise ValueError(f'No chunk covers frozen anchor at character {position}')
    return covering[0], [chunk.chunk_id for chunk in covering[1:]]


def prepare(config, runtime, config_path, output):
    # Numerical libraries and embedding/database modules are not needed here.
    from src.ingestion import load_pages
    from src.run import chunks_for, fingerprint, resolve, sha256, validate

    runtime.guard('manual-review:before-validation')
    validation = validate(config)
    anchors_path = resolve('benchmark/coherence_positions.json')
    freeze_path = resolve(config['freeze'])
    frozen = json.loads(freeze_path.read_text())
    anchors_file = json.loads(anchors_path.read_text())
    anchors = anchors_file['positions']
    if len(anchors) != 10 or len({anchor['id'] for anchor in anchors}) != 10:
        raise ValueError('Need exactly ten distinct frozen coherence anchors')
    anchors_checksum = sha256(anchors_path)
    if frozen['coherence_positions_sha256'] != anchors_checksum:
        raise ValueError('Frozen coherence anchor checksum changed')
    identity = {'pipeline': fingerprint(config), 'config_path': str(config_path.relative_to(ROOT)),
                'config_sha256': sha256(config_path), 'freeze_sha256': sha256(freeze_path),
                'coherence_positions_sha256': anchors_checksum,
                'generator_sha256': sha256(Path(__file__).resolve())}
    by_page = {}
    for anchor in anchors:
        if type(anchor['char_position']) is not int:
            raise ValueError('Coherence anchor positions must be integer source offsets')
        by_page.setdefault((anchor['document_id'], str(anchor['unit_id'])), []).append(anchor)
    source_pages = {}
    for page in load_pages(resolve(config['corpus'])):
        key = (page.document_id, str(page.page))
        if key not in by_page:
            continue
        checksum = hashlib.sha256(page.text.encode()).hexdigest()
        for anchor in by_page[key]:
            if anchor['source_text_sha256'] != checksum or not 0 <= anchor['char_position'] < len(page.text):
                raise ValueError(f'Source checksum or position changed for anchor {anchor["id"]}')
        source_pages[key] = page
    if set(source_pages) != set(by_page):
        raise ValueError('An anchored source page is missing from the current corpus')

    covering, chunk_counts = {}, {}
    for physical in ('A', 'B'):
        candidates = {anchor['id']: [] for anchor in anchors}
        count = 0
        for chunk in chunks_for(config, physical):
            if count % runtime.batch_size == 0:
                runtime.guard('manual-review:chunk-batch')
            count += 1
            key = (chunk.document_id, str(chunk.page))
            for anchor in by_page.get(key, []):
                start, end = chunk.metadata['char_start'], chunk.metadata['char_end']
                if start <= anchor['char_position'] < end:
                    if source_pages[key].text[start:end] != chunk.text:
                        raise ValueError('Chunk text does not match its normalized source offsets')
                    candidates[anchor['id']].append(chunk)
        chunk_counts[physical] = count
        for anchor in anchors:
            covering[(physical, anchor['id'])] = choose_covering(candidates[anchor['id']], anchor['char_position'])

    records = []
    for anchor in anchors:
        page = source_pages[(anchor['document_id'], str(anchor['unit_id']))]
        for strategy in ('A', 'B', 'C'):
            physical = 'A' if strategy == 'A' else 'B'
            chunk, other_ids = covering[(physical, anchor['id'])]
            records.append({'review_id': f'{anchor["id"]}-{strategy}', 'anchor_id': anchor['id'],
                            'strategy': strategy, 'physical_index': physical,
                            'chunk_id': chunk.chunk_id, 'document_id': chunk.document_id,
                            'source': chunk.source, 'page': chunk.page,
                            'printed_page': chunk.metadata.get('printed_page'), 'text': chunk.text,
                            'metadata': {**chunk.metadata, 'document_id': chunk.document_id,
                                         'source': chunk.source, 'page': chunk.page},
                            'char_position': anchor['char_position'],
                            'char_position_in_chunk': anchor['char_position'] - chunk.metadata['char_start'],
                            'source_text_sha256': anchor['source_text_sha256'],
                            'source_paragraph_start': anchor['paragraph_start'],
                            'source_paragraph_end': anchor['paragraph_end'],
                            'other_covering_chunk_ids': other_ids,
                            'source_anchor_context': page.text[max(0, anchor['char_position'] - 160):anchor['char_position'] + 160],
                            'coherence_0_2': None, 'reason': ''})
    runtime.guard('manual-review:before-publication')
    if (fingerprint(config) != identity['pipeline'] or sha256(config_path) != identity['config_sha256']
        or sha256(freeze_path) != identity['freeze_sha256'] or sha256(anchors_path) != anchors_checksum):
        raise ValueError('Frozen inputs changed during review preparation; no artifact published')
    if output.exists():
        existing = json.loads(output.read_text())
        if (not isinstance(existing, dict) or existing.get('format_version') != 1
            or not isinstance(existing.get('records'), list)
            or existing.get('status') != 'pending_human_review'):
            raise ValueError('Existing output is not an untouched coherence review pack; choose a different --output')
        if any(record.get('coherence_0_2') is not None or record.get('reason', '')
               for record in existing.get('records', [])):
            raise ValueError('Existing review contains manual work; use a different --output path to preserve it')
        if existing.get('identity') == identity and existing.get('records') == records:
            return {'artifact': str(output.relative_to(ROOT)), 'records': len(records),
                    'status': 'unchanged_pending_review', 'labels_assigned': 0}
    pack = {'format_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'status': 'pending_human_review', 'identity': identity, 'validation': validation,
            'selection_rule': SELECTION, 'frozen_anchor_rule': anchors_file['rule'],
            'physical_chunk_counts': chunk_counts,
            'rubric': {'0': 'Cut in the middle of an idea or missing its subject; not understandable.',
                       '1': 'Partly understandable, with missing context.',
                       '2': 'Understandable on its own and preserves a complete idea.'},
            'limitations': ['The frozen PDF anchors can cover extracted figure/table text; positions are preserved rather than reselected after seeing chunks.',
                            'C uses the same physical chunks as B; no separate chunking or embedding is performed.',
                            'The generator assigns no coherence, metadata or grounding labels.'],
            'records': records}
    atomic_json(output, pack)
    readme = output.parent / 'README.md'
    if not readme.exists():
        atomic_write(readme, (
            '# Phiếu chấm coherence thủ công\n\n'
            f'`{output.name}` chứa 30 bản ghi: cùng 10 vị trí nguồn đã freeze × A/B/C. '
            'Mọi `coherence_0_2` đang là `null`; `reason` để trống. Chưa có nhãn do người học chấm.\n\n'
            'Đọc `text` của chunk và chấm: 0 = cắt giữa ý/thiếu chủ thể nên không hiểu; '
            '1 = hiểu một phần, thiếu ngữ cảnh; 2 = tự hiểu được, giữ trọn ý. '
            'Điền điểm và lý do bằng chính việc đọc của người chấm; không suy điểm từ Hit@3. '
            '`source_anchor_context` và URL giúp đối chiếu nguồn; điểm đánh giá tính tự đủ của chunk.\n\n'
            'Nếu nhiều chunk phủ cùng anchor, chọn chunk có `char_start` nhỏ nhất, tiếp theo `char_end` '
            'và `chunk_id`; `other_covering_chunk_ids` công bố các lựa chọn còn lại. '
            'Offsets là khoảng nửa mở [start, end); `page` là trang PDF vật lý, `printed_page` là số trang in. '
            'C dùng chung chunk với B. Không chọn lại anchor chỉ vì nó rơi vào bảng, hình hay đoạn bị cắt.\n\n'
            'Tạo lại từ thư mục `starter/`:\n\n'
            '```bash\npython -m scripts.prepare_manual_review\n```\n\n'
            'Script kiểm tra freeze, checksum, offsets và coverage; không gọi model hay database. '
            'Nếu file đã có điểm hoặc lý do, script từ chối ghi đè; dùng `--output` khác để giữ bản chấm. '
            'Coherence không thay cho bảng chấm metadata và grounding trên các trace test.\n'
        ).encode())
    return {'artifact': str(output.relative_to(ROOT)), 'records': len(records),
            'status': 'pending_human_review', 'labels_assigned': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='starter/config/pipeline.json')
    parser.add_argument('--output', default='results/manual-review/coherence.json')
    args = parser.parse_args()
    require_python()
    config_path = lab_path(ROOT, args.config)
    config = json.loads(config_path.read_text())
    runtime = RuntimeConfig(**config['runtime'])
    runtime.apply_threads()
    runtime.guard('manual-review:start')
    from src.run import resolve
    output = resolve(args.output)
    if not output.is_relative_to(resolve(config['results'])) or output.suffix != '.json':
        parser.error('Review output must be a JSON file inside the configured results directory')
    with exclusive_run(resolve(config['cache']) / 'manual-review.lock'):
        result = prepare(config, runtime, config_path, output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
