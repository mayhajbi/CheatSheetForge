"""PDF text extraction for exams and syllabus files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber


@dataclass
class ExtractedDocument:
    """Raw text extracted from one PDF."""

    source_file: str
    source_label: str
    text: str
    page_count: int
    char_count: int
    extraction_ok: bool
    warning: str | None = None
    path: str | None = None  # original path — needed for scanned-PDF Gemini fallback


_MOED_PATTERNS = [
    # מועד א 2023 / מועד ב' תשפ"ג
    (re.compile(r"מועד\s*([אבג])['׳]?\s*(\d{4}|תש[א-ת]{0,3}[\"״']?[א-ת]?)", re.I), "מועד {moed} {year}"),
    (re.compile(r"moed[_\s-]*([abc])[_\s-]*(\d{4})", re.I), "מועד {moed} {year}"),
    (re.compile(r"exam[_\s-]*(\d{4})[_\s-]*([ab])", re.I), "מועד {moed} {year}"),
    (re.compile(r"(\d{4})[_\s-]*([אב])", re.I), "מועד {moed} {year}"),
]

_HEB_MOED = {"a": "א", "b": "ב", "c": "ג", "א": "א", "ב": "ב", "ג": "ג"}


def label_from_filename(filename: str) -> str:
    """Derive a human-readable source label from a PDF filename."""
    stem = Path(filename).stem
    stem_norm = stem.replace("-", " ").replace("_", " ")

    for pattern, _ in _MOED_PATTERNS:
        m = pattern.search(stem) or pattern.search(stem_norm)
        if not m:
            continue
        g1, g2 = m.group(1), m.group(2)
        # Heuristic: if g1 looks like a year, swap
        if g1.isdigit() and len(g1) == 4:
            year, moed_raw = g1, g2
        elif g2.isdigit() and len(g2) == 4:
            moed_raw, year = g1, g2
        else:
            moed_raw, year = g1, g2
        moed = _HEB_MOED.get(moed_raw.lower(), moed_raw)
        return f"מועד {moed} {year}"

    # Fallback: readable stem
    return re.sub(r"\s+", " ", stem_norm).strip() or stem


_FINAL_LETTERS = "םןךףץ"
_LATIN_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.,:'\"()\-/]*[A-Za-z0-9]|[A-Za-z0-9]")


def _looks_reversed(text: str) -> bool:
    """Hebrew extracted in visual order puts final letters at the START of words.

    In real Hebrew, ם/ן/ך/ף/ץ only ever end a word, so counting which end they
    land on tells us whether pdfplumber handed us the line back-to-front.
    """
    starts = ends = 0
    for token in text.split():
        if token[0] in _FINAL_LETTERS:
            starts += 1
        if token[-1] in _FINAL_LETTERS:
            ends += 1
    return starts > ends


def fix_rtl_visual_order(text: str) -> str:
    """Restore logical order for Hebrew PDFs extracted in visual (RTL) order.

    Reverses each line, then flips Latin/digit runs back, so "SSD יננוכ"
    becomes "כונני SSD" instead of "DSS כונני". Text that already reads
    correctly is returned untouched.
    """
    if not _looks_reversed(text):
        return text

    fixed_lines = []
    for line in text.splitlines():
        flipped = line[::-1]
        flipped = _LATIN_RUN.sub(lambda m: m.group(0)[::-1], flipped)
        fixed_lines.append(flipped.strip())
    return "\n".join(fixed_lines)


def extract_pdf(
    path: str | Path,
    *,
    source_label: str | None = None,
) -> ExtractedDocument:
    """Extract text from a PDF using pdfplumber.

    Does not invent content: empty/failed extraction is reported via
    extraction_ok=False and an explicit warning.
    """
    path = Path(path)
    resolved = str(path.resolve()) if path.exists() else str(path)
    if not path.exists():
        return ExtractedDocument(
            source_file=path.name,
            source_label=source_label or label_from_filename(path.name),
            text="",
            page_count=0,
            char_count=0,
            extraction_ok=False,
            warning=f"file not found: {path}",
            path=resolved,
        )

    pages: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.append(page_text)
    except Exception as exc:  # noqa: BLE001 — surface extraction failure to caller
        return ExtractedDocument(
            source_file=path.name,
            source_label=source_label or label_from_filename(path.name),
            text="",
            page_count=0,
            char_count=0,
            extraction_ok=False,
            warning=f"pdf extraction failed: {exc}",
            path=resolved,
        )

    text = "\n\n".join(pages).strip()
    ok = bool(text)
    warning = None
    if not ok:
        warning = (
            "no extractable text layer (scanned PDF) — "
            "will fall back to Gemini multimodal PDF reading."
        )

    return ExtractedDocument(
        source_file=path.name,
        source_label=source_label or label_from_filename(path.name),
        text=text,
        page_count=page_count,
        char_count=len(text),
        extraction_ok=ok,
        warning=warning,
        path=resolved,
    )


def extract_many(
    paths: list[str | Path],
    *,
    labels: dict[str, str] | None = None,
) -> list[ExtractedDocument]:
    """Extract multiple PDFs; one failure does not stop the rest."""
    labels = labels or {}
    results: list[ExtractedDocument] = []
    for p in paths:
        name = Path(p).name
        results.append(extract_pdf(p, source_label=labels.get(name)))
    return results


_TOPIC_LINE = re.compile(
    r"^\s*(?:[-*•]|\d+[\.)]|[א-ת][\.)])\s*(.+?)\s*$",
)


def parse_syllabus_topics(syllabus_text: str) -> list[str]:
    """Best-effort topic list from syllabus text (before LLM refinement).

    Keeps short non-empty lines that look like syllabus entries.
    The classifier may further normalize against this list.
    """
    topics: list[str] = []
    seen: set[str] = set()
    for raw in syllabus_text.splitlines():
        line = raw.strip()
        if not line or len(line) < 3 or len(line) > 120:
            continue
        m = _TOPIC_LINE.match(line)
        candidate = (m.group(1) if m else line).strip()
        # Skip obvious headers / boilerplate
        if candidate.lower().startswith(("http", "www.")):
            continue
        key = candidate.casefold()
        if key in seen:
            continue
        seen.add(key)
        topics.append(candidate)
    return topics
