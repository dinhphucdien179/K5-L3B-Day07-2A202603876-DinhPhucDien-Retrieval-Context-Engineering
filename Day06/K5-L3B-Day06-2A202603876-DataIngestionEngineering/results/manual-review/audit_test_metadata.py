#!/usr/bin/env python3
"""Recheck persisted test-hit provenance against the pinned native PDF.

This is an artifact audit, not another retrieval run or a semantic grounding judge.
Only stdlib and pypdf are loaded; extraction is limited to 39 corpus pages and
the three copyright/contents authority pages. Run with Python 3.12.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import tempfile
import time
import unicodedata
from urllib.parse import urlsplit


DEFAULT_TRACE = "results/20261114T062008.998642Z-evaluate/test-traces.json"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_native(text):
    """Independent application of the documented NFC-paragraphs-code-v2 rule."""
    value = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines, code = [], False
    for line in value.split("\n"):
        if line.strip() == "```":
            code = not code
            lines.append("```")
        elif code:
            lines.append(line.rstrip())
        else:
            lines.append(re.sub(r"[^\S\n]+", " ", line).strip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def write_atomic(path, value):
    """Publish only a complete JSON object; never touch semantic review files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(actual, expected):
    return type(actual) is type(expected) and actual == expected


def resolve(root, value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", default="results/manual-review/test-metadata-audit.json")
    parser.add_argument("--native-evidence", default="results/manual-review/native-pdf-evidence.json")
    args = parser.parse_args()
    root = args.root.resolve()
    output, native_output = resolve(root, args.output), resolve(root, args.native_evidence)
    require(output != native_output, "Audit and native-evidence outputs must differ")
    # Prevent an accidental CLI typo from replacing frozen input or reviewed labels.
    allowed_names = {"test-metadata-audit.json", "native-pdf-evidence.json"}
    for path in (output, native_output):
        require(path.name in allowed_names, "Use an audit filename, not a reviewed-label/input filename")
    started = time.monotonic()
    config_path = root / "starter/config/pipeline.json"
    config = read_json(config_path)
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[key] = str(config["runtime"]["native_threads"])
    from pypdf import PdfReader, __version__ as pypdf_version

    input_paths = {
        "config": config_path,
        "corpus": resolve(root, config["corpus"]),
        "manifest": resolve(root, config["manifest"]),
        "sources": resolve(root, config["sources"]),
        "questions": resolve(root, config["benchmark"]),
        "freeze": resolve(root, config["freeze"]),
        "selection": root / "data/source-selection.json",
        "api": root / "data/worldbank-api.json",
        "trace": root / DEFAULT_TRACE,
        "auditor": Path(__file__).resolve(),
    }
    require(not {output, native_output}.intersection(input_paths.values()), "An output overlaps an input")
    identities = {name: {"path": str(path.relative_to(root)), "sha256": sha_file(path)}
                  for name, path in input_paths.items()}
    manifest = read_json(input_paths["manifest"])
    freeze = read_json(input_paths["freeze"])
    sources = read_json(input_paths["sources"])
    selection = read_json(input_paths["selection"])
    api_snapshot = read_json(input_paths["api"])
    questions = {item["id"]: item for item in read_json(input_paths["questions"]) if item["split"] == "test"}
    traces = read_json(input_paths["trace"])
    require(len(sources) == 1, "This audit expects the declared single-source report")
    source = sources[0]
    pages = [json.loads(line) for line in input_paths["corpus"].read_text(encoding="utf-8").splitlines()]
    by_page = {item["page"]: item for item in pages}
    units = {item["unit_id"]: item for item in manifest["units"]}
    source_pages = {item["page"]: item for item in source["pages"]}
    selected = {item["physical_page"]: item for item in selection["selected_pages"]}
    require(len(pages) == len(by_page) == len(units) == len(source_pages) == len(selected) == 39,
            "Expected 39 unique selected physical pages in all provenance files")
    require(by_page.keys() == units.keys() == source_pages.keys() == selected.keys(), "Selected page sets disagree")
    require(identities["corpus"]["sha256"] == manifest["corpus_sha256"] == freeze["corpus_sha256"], "Corpus checksum differs")
    require(identities["manifest"]["sha256"] == freeze["manifest_sha256"], "Manifest checksum differs")
    require(identities["questions"]["sha256"] == freeze["benchmark_sha256"], "Frozen questions differ")
    require(manifest["normalization_version"] == freeze["normalization_version"] == "NFC-paragraphs-code-v2", "Unknown normalization")
    require(identities["api"]["sha256"] == source["api_metadata_sha256"] == selection["api_snapshot"]["sha256"], "API snapshot checksum differs")
    documents = [value for key, value in api_snapshot["documents"].items() if key != "facets"]
    require(len(documents) == 1, "Expected one API document")
    api = documents[0]
    require(api["guid"] in source["url"], "API GUID does not identify PDF URL")
    require(urlsplit(api["pdfurl"]).path == urlsplit(source["url"]).path, "API PDF path differs")
    expected_pdf_sha = source["expected_sha256"]
    require(expected_pdf_sha == selection["pdf_snapshot"]["sha256"] == source["metadata"]["version"], "PDF version pins differ")
    pdf_path = resolve(root, config["cache"]) / "http" / f"{expected_pdf_sha}.pdf"
    require(pdf_path.stat().st_size == selection["pdf_snapshot"]["bytes"] <= config["runtime"]["max_response_bytes"], "PDF byte budget/size mismatch")
    require(sha_file(pdf_path) == expected_pdf_sha, "Native PDF checksum mismatch")
    reader = PdfReader(pdf_path)
    require(not reader.is_encrypted and len(reader.pages) == source["physical_pdf_pages"] == selection["physical_pdf_pages"] == 232, "Native page count/encryption mismatch")
    authority = {}
    for number, purpose in ((3, "copyright, citation and CC BY 3.0 IGO"), (9, "chapter 1/2 contents and printed starts"), (10, "chapter 3 printed start")):
        text = normalize_native(reader.pages[number - 1].extract_text() or "")
        authority[str(number)] = {"physical_page": number, "purpose": purpose, "text": text, "normalized_sha256": sha_text(text)}
    copyright_year = int(re.search(r"©\s*(\d{4})", authority["3"]["text"]).group(1))
    require("CC BY 3.0 IGO" in authority["3"]["text"], "Expected license missing from native PDF")
    chapter_entries = []
    for number in (9, 10):
        for chapter, title, printed in re.findall(r"^Chapter (\d+)\. (.+?) (\d+)$", authority[str(number)]["text"], re.M):
            chapter_entries.append({"chapter": chapter, "title": title, "printed_start": int(printed), "toc_physical_page": number})
    chapter_entries.sort(key=lambda item: item["printed_start"])
    require([item["chapter"] for item in chapter_entries[:3]] == ["1", "2", "3"], "Native contents chapter boundaries not found")
    require(copyright_year == source["metadata"]["year"] == 2022, "Report copyright year differs")
    require(source["metadata"]["api_document_date"] == api["docdt"] == "2023-04-10T04:00:00Z", "API date differs")
    require(source["metadata"]["language"] == api["lang"] and source["metadata"]["document_type"] == api["docty"]
            and source["metadata"]["report_number"] == api["repnb"] and source["metadata"]["country"] in api["count"].split(","), "API metadata fields differ")

    native_pages = []
    for number, page in by_page.items():
        peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        require(peak_mb <= config["runtime"]["rss_limit_mb"], "RSS batch-boundary guard exceeded")
        native = normalize_native(reader.pages[number - 1].extract_text() or "")
        require(native == page["text"], f"Native PDF/corpus text mismatch on page {number}")
        unit, declaration, chosen = units[number], source_pages[number], selected[number]
        headers = native.splitlines()[:3]
        printed_matches = [re.fullmatch(r"From the Last Mile to the Next Mile (\d+)", line)
                           or re.fullmatch(r"(\d+) 2022 Vietnam Poverty and Equity Assessment", line) for line in headers]
        printed_values = [int(match.group(1)) for match in printed_matches if match]
        require(len(printed_values) == 1, f"Ambiguous native printed header on page {number}")
        printed = printed_values[0]
        chapters = [item for item in chapter_entries if item["printed_start"] <= printed]
        require(chapters, f"No TOC chapter for printed page {printed}")
        chapter = chapters[-1]
        expected_metadata = {**source["metadata"], **declaration["metadata"]}
        require(type(number) is int and printed == number - 20, f"Physical/printed mapping differs on page {number}")
        require(expected_metadata["printed_page"] == printed == chosen["printed_page"], f"Printed metadata differs on page {number}")
        require(expected_metadata["chapter"] == chapter["chapter"] == chosen["chapter"], f"Chapter range differs on page {number}")
        require(expected_metadata["chapter_title"] == chapter["title"], f"Chapter title differs on page {number}")
        for key, expected in expected_metadata.items():
            require(exact(page["metadata"].get(key), expected) and exact(unit["metadata"].get(key), expected), f"Corpus/manifest metadata differs: {number}/{key}")
        require(page["document_id"] == unit["document_id"] == source["document_id"] and page["source"] == unit["source_path_or_url"] == source["url"], f"Source identity differs on page {number}")
        require(len(native) == chosen["normalized_characters"] == unit["normalized_characters"]
                and sha_text(native) == unit["normalized_sha256"], f"Source text length/hash differs on page {number}")
        require(unit["raw_sha256"] == expected_pdf_sha and unit["raw_bytes"] == pdf_path.stat().st_size, f"Manifest raw source differs on page {number}")
        require(unit["boundary"] == {"char_start": 0, "char_end": len(native)}, f"Manifest bounds differ on page {number}")
        native_pages.append({"physical_page": number, "printed_page_observed": printed, "header_lines": headers,
                             "text": native,
                             "chapter_from_toc": chapter["chapter"], "chapter_title_from_toc": chapter["title"],
                             "toc_physical_page": chapter["toc_physical_page"], "normalized_characters": len(native),
                             "normalized_sha256": sha_text(native), "corpus_manifest_selection_match": True})
    require(sum(len(page["text"]) for page in pages) == manifest["total_normalized_characters"] == 119228, "Total character count differs")
    require(len(questions) == 5 and len(traces) == 15, "Expected five test questions and 15 cases")
    pairs = [(item["question_id"], item["strategy"]) for item in traces]
    require(len(set(pairs)) == 15 and set(pairs) == {(qid, strategy) for qid in questions for strategy in "ABC"}, "Missing/duplicate question/strategy case")
    records, cases = [], []
    for trace in traces:
        qid, strategy, hits = trace["question_id"], trace["strategy"], trace["hits"]
        question = questions[qid]
        require(trace["split"] == "test" and trace["question"] == question["question"] and len(hits) == 3, "Trace question/split/top-3 differs")
        require(trace["physical_index"] == ("A" if strategy == "A" else "B"), "Physical index alias differs")
        expected_filter = question.get("filter", {}) if strategy == "C" else {}
        require(trace["applied_filter"] == expected_filter, "Applied filter differs from prior question input")
        case_rows = []
        for rank, hit in enumerate(hits, 1):
            actual, errors, checks = hit["metadata"], [], {}
            page = by_page.get(actual.get("page"))
            require(page is not None, "Hit refers to a page outside the frozen corpus")
            positions = [match.start() for match in re.finditer(re.escape(hit["text"]), page["text"])]
            require(len(positions) == 1, "Hit text must independently identify one exact source position")
            start, end = positions[0], positions[0] + len(hit["text"])
            expected = {**page["metadata"], "document_id": page["document_id"], "source": page["source"],
                        "page": page["page"], "char_start": start, "char_end": end}
            for key, value in expected.items():
                checks[key] = {"present": key in actual, "type_correct": type(actual.get(key)) is type(value), "value_correct": actual.get(key) == value}
                if not all(checks[key].values()):
                    errors.append(f"metadata:{key}")
            if set(actual) != set(expected):
                errors.append("unexpected/missing metadata keys")
            chunk_config = config["chunking"]
            method = f"fixed:{chunk_config['fixed_size']}:{chunk_config['overlap']}" if strategy == "A" else f"paragraph:{chunk_config['paragraph_max_size']}"
            stable_id = sha_text(f"{page['document_id']}\0{page['page']}\0{method}\0{start}\0{end}\0{hit['text']}")
            if stable_id != hit["chunk_id"]:
                errors.append("stable chunk ID")
            filter_match = all(exact(actual.get(key), value) for key, value in expected_filter.items()) if expected_filter else None
            if filter_match is False:
                errors.append("filter scope")
            row = {"audit_id": f"{qid}-{strategy}-{rank}", "question_id": qid, "strategy": strategy,
                   "record_id": f"{qid}-{strategy}-r{rank}",
                   "rank": rank, "chunk_id": hit["chunk_id"], "text": hit["text"],
                   "actual_metadata": actual, "expected_metadata": expected, "field_checks": checks,
                   "source_text_sha256": sha_text(page["text"]), "chunk_text_sha256": sha_text(hit["text"]),
                   "unique_source_text_positions": positions, "source_slice_exact": page["text"][start:end] == hit["text"],
                   "chunk_method": method, "stable_id_matches": stable_id == hit["chunk_id"],
                   "filter_compliant": filter_match, "metadata_correct": not errors, "errors": errors}
            records.append(row)
            case_rows.append(row)
        cases.append({"question_id": qid, "strategy": strategy, "metadata_correct_count": sum(row["metadata_correct"] for row in case_rows),
                      "record_count": 3, "checked_records": 3, "applied_filter": expected_filter, "filter_compliant": all(row["filter_compliant"] is True for row in case_rows) if expected_filter else None,
                      "top3_filter_compliant": all(row["filter_compliant"] is True for row in case_rows) if expected_filter else None,
                      "filter_status": "applicable" if expected_filter else "N/A: no filter applied by this strategy/question",
                      "audit_ids": [row["audit_id"] for row in case_rows]})
    require(len(records) == 45, "Expected 45 top-3 records")
    reviewed_at = datetime.now(timezone.utc).isoformat()
    native_evidence = {"schema_version": 1, "reviewed_at": reviewed_at, "method": "Native PDF checksum, bounded pypdf plain extraction, documented normalization, exact corpus comparison and native header/TOC/copyright checks",
                       "pdf": {"path": str(pdf_path.relative_to(root)), "sha256": expected_pdf_sha, "bytes": pdf_path.stat().st_size, "physical_pages": len(reader.pages)},
                       "pypdf_version": pypdf_version, "normalization_version": manifest["normalization_version"],
                       "authority_pages": authority, "chapter_entries_from_toc": chapter_entries,
                       "report_year_from_copyright": copyright_year, "api_document_date": api["docdt"],
                       "date_note": "Report/copyright year 2022 and API document date 2023-04-10 are separate fields; neither is inferred from the other.",
                       "corpus_page_count": len(native_pages), "extracted_page_count": len(native_pages) + len(authority), "pages": native_pages,
                       "all_source_checks_passed": True}
    summaries = {}
    for strategy in "ABC":
        subset = [row for row in records if row["strategy"] == strategy]
        filtered = [case for case in cases if case["strategy"] == strategy and case["applied_filter"]]
        summaries[strategy] = {"metadata_correct_count": sum(row["metadata_correct"] for row in subset), "record_count": len(subset),
                               "filter_compliant_case_count": sum(case["filter_compliant"] is True for case in filtered),
                               "filter_applicable_case_count": len(filtered), "filter_status": "measured" if filtered else "N/A"}
    audit = {"schema_version": 1, "reviewed_at": reviewed_at, "reviewer_type": "programmatic_source_audit", "human_confirmed": False,
             "status": "programmatic_audit_complete",
             "method": "Compare every actual field and exact type against source page, manifest, source declaration, selection, raw API snapshot and newly extracted checksum-pinned native PDF. Locate each chunk text independently before checking offsets/stable ID. This does not assess semantic grounding.",
             "inputs": identities, "native_evidence_path": str(native_output.relative_to(root)) if native_output.is_relative_to(root) else str(native_output),
             "record_count": len(records), "case_count": len(cases), "unique_chunk_count": len({row["chunk_id"] for row in records}),
             "unique_physical_page_count": len({row["actual_metadata"]["page"] for row in records}),
             "metadata_correct_count": sum(row["metadata_correct"] for row in records), "errors": [row["audit_id"] for row in records if row["errors"]],
             "denominator_note": "45 retrieval records include repeated B/C chunks and repeated question hits; they are not 45 independent chunks.",
             "strategy_summary": summaries, "cases": cases, "records": records,
             "resources": {"wall_seconds": time.monotonic() - started, "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                           "rss_guard_mb": config["runtime"]["rss_limit_mb"], "rss_guard_scope": "boundary check; not an OS hard memory limit", "native_threads": config["runtime"]["native_threads"]}}
    audit["summary"] = {
        "records_checked": len(records), "metadata_sufficient_and_correct": audit["metadata_correct_count"],
        "unique_chunk_ids": audit["unique_chunk_count"], "unique_source_pages": audit["unique_physical_page_count"],
        "per_strategy": {
            strategy: {"records_checked": item["record_count"], "metadata_sufficient_and_correct": item["metadata_correct_count"],
                       "filtered_questions": item["filter_applicable_case_count"],
                       "filter_compliant_questions": item["filter_compliant_case_count"] if item["filter_applicable_case_count"] else None,
                       "filter_result": f"{item['filter_compliant_case_count']}/{item['filter_applicable_case_count']}" if item["filter_applicable_case_count"] else "N/A"}
            for strategy, item in summaries.items()}}
    # Full checks finish before either artifact is published. Each publication is atomic.
    for name, item in identities.items():
        require(sha_file(input_paths[name]) == item["sha256"], f"Input changed during audit: {name}")
    write_atomic(native_output, native_evidence)
    audit["native_evidence_sha256"] = sha_file(native_output)
    write_atomic(output, audit)
    print(json.dumps({key: audit[key] for key in ("record_count", "case_count", "unique_chunk_count", "unique_physical_page_count", "metadata_correct_count", "errors", "strategy_summary", "resources")}, ensure_ascii=False))
    return 0 if not audit["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
