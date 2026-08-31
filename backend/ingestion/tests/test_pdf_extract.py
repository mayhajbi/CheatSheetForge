"""
בדיקת קבלה לאדם A (פרק 12): "PDF אמיתי אחד -> JSON תקין מול schemas.py".

כאן נבדקת רק שכבת החילוץ (ללא קריאת LLM, שדורשת API key). הבדיקה מוודאת
עמידות לכשל חלקי (פרק 07): קובץ לא-תקין לא מרים חריגה, אלא מסומן error
ומאפשר לשאר הקבצים באצווה להמשיך.
"""

from pathlib import Path

from backend.ingestion.pdf_extract import extract_batch, extract_text_from_pdf


def test_extract_missing_file_reports_error(tmp_path):
    fake_path = tmp_path / "does_not_exist.pdf"
    result = extract_text_from_pdf(fake_path)

    assert not result.ok
    assert result.error is not None


def test_extract_batch_continues_after_single_failure(tmp_path):
    valid_marker = tmp_path / "not_really_a_pdf.pdf"
    valid_marker.write_text("this is not a valid pdf")  # יגרום לכשל חילוץ, לא לחריגה
    missing = tmp_path / "missing.pdf"

    result = extract_batch([valid_marker, missing])

    assert len(result.files) == 2
    assert len(result.failed) == 2  # שני הקבצים לא-תקינים -- אך הריצה לא נופלת
