"""
חילוץ טקסט מקובצי PDF -- מבחנים/תרגילים פתורים, וקובץ סילבוס.
משתמש ב-pdfplumber (ספרייה בוגרת, לא מימוש עצמי -- לפי עקרון פרק 06 ב-PRD).

עמידות לכשל חלקי (פרק 07): כשלון בקובץ בודד לא מפיל את כל האצווה --
מוחזרת שגיאה מפורשת לאותו קובץ, והשאר ממשיכים.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pdfplumber

logger = logging.getLogger(__name__)


@dataclass
class ExtractedFile:
    """טקסט גולמי שחולץ מקובץ PDF בודד, לפני סיווג."""

    filename: str
    text: str
    page_count: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class ExtractionResult:
    files: List[ExtractedFile] = field(default_factory=list)

    @property
    def failed(self) -> List[ExtractedFile]:
        return [f for f in self.files if not f.ok]

    @property
    def succeeded(self) -> List[ExtractedFile]:
        return [f for f in self.files if f.ok]


def extract_text_from_pdf(path: Path) -> ExtractedFile:
    """מחלץ טקסט מקובץ PDF בודד. לא מרים חריגה -- כשל מוחזר בשדה error."""

    try:
        with pdfplumber.open(path) as pdf:
            pages_text = []
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                pages_text.append(page_text)
            full_text = "\n\n".join(pages_text).strip()

            if not full_text:
                return ExtractedFile(
                    filename=path.name,
                    text="",
                    page_count=len(pdf.pages),
                    error=(
                        "לא נמצא טקסט בקובץ -- ייתכן שמדובר בסריקה ללא שכבת טקסט "
                        "(נדרש OCR, שאינו נתמך ב-MVP). ראו הודעת איכות קלט בפרק 03."
                    ),
                )

            return ExtractedFile(
                filename=path.name, text=full_text, page_count=len(pdf.pages)
            )
    except Exception as exc:  # noqa: BLE001 -- כוונה: לתפוס כל כשל חילוץ ולדווח עליו
        logger.warning("PDF extraction failed for %s: %s", path.name, exc)
        return ExtractedFile(filename=path.name, text="", page_count=0, error=str(exc))


def extract_batch(paths: List[Path]) -> ExtractionResult:
    """מחלץ טקסט מרשימת קבצי PDF. כל קובץ מטופל בנפרד (עמידות לכשל חלקי)."""

    result = ExtractionResult()
    for path in paths:
        result.files.append(extract_text_from_pdf(path))
    return result


def extract_syllabus(path: Path) -> str:
    """חילוץ טקסט מקובץ הסילבוס (אותו מנגנון, ללא לוגיקת סיווג)."""

    extracted = extract_text_from_pdf(path)
    if not extracted.ok:
        raise ValueError(f"כשל בחילוץ קובץ הסילבוס '{path.name}': {extracted.error}")
    return extracted.text
