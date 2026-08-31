"""
נקודת הכניסה הראשית -- FastAPI. מחבר את שלושת הזרמים (ingestion+classification,
dedup, export) לזרימת משתמש אחת, לפי פרק 11/12 ב-PRD.

זרימה (session-based בלבד -- ללא DB, ראו פרק 06/07):
1. POST /api/upload -- PDFs + סילבוס + max_pages -> חילוץ + סיווג.
2. POST /api/merge/{session_id} -- מנוע האיחוד על הסיווג שנשמר.
3. GET  /api/preview/{session_id} -- הבנק המרוכז לתצוגה מקדימה.
4. POST /api/preview/{session_id}/remove -- הסרת פריטים (MVP: הסרה בלבד).
5. POST /api/export/{session_id} -- ייצוא docx/pdf להורדה.
6. DELETE /api/session/{session_id} -- מחיקת כל הנתונים הזמניים (פרק 07).

אחסון ה-session הוא in-memory (dict) לפשטות MVP.
# ponytail: dict גלובלי -- מספיק למופע יחיד בדמו; ל-production מרובה מופעים
# יש להחליף ב-Redis עם TTL.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.classification.classifier import classify_exams
from backend.dedup.merge_engine import merge_batch, merge_batch_offline
from backend.export.docx_builder import build_docx
from backend.export.pdf_builder import build_pdf
from backend.ingestion.pdf_extract import extract_many, extract_pdf
from backend.schemas import ExportFormat, MergedBank, UploadLimits

# מפתחות ה-API נטענים מקובץ .env מקומי (לא נכנס ל-git). ב-Railway הם מוגדרים
# כמשתני סביבה של השירות ואז אין .env והקריאה הזו פשוט לא עושה כלום.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="CheatSheetForge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # לצמצם ל-domain הפרונט בפריסת production
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_LIMITS = UploadLimits()  # 15 קבצים / 5MB -- ברירת מחדל לכיול, ראו פרק 06/10

_sessions: Dict[str, dict] = {}


def _session_dir(session_id: str) -> Path:
    d = Path(tempfile.gettempdir()) / "cheatsheet-forge" / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_session(session_id: str) -> dict:
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session לא נמצא")
    return session


def _get_merged(session_id: str) -> MergedBank:
    session = _get_session(session_id)
    if not session.get("merged"):
        raise HTTPException(status_code=404, detail="אין בנק מאוחד ל-session זה")
    return session["merged"]


@app.post("/api/upload")
async def upload(
    course: str = Form(...),
    max_pages: int = Form(...),
    exam_files: List[UploadFile] = File(...),
    syllabus_file: UploadFile = File(...),
):
    if len(exam_files) > UPLOAD_LIMITS.max_files:
        raise HTTPException(
            status_code=400,
            detail=f"עד {UPLOAD_LIMITS.max_files} קבצים בהעלאה בודדת. "
            "להעלאת קבצים נוספים -- ראו תרחיש 'המשך פרויקט קיים'.",
        )

    session_id = str(uuid.uuid4())
    session_dir = _session_dir(session_id)

    total_bytes = 0
    saved_paths: list[Path] = []

    for uf in exam_files:
        content = await uf.read()
        total_bytes += len(content)
        if total_bytes > UPLOAD_LIMITS.max_total_mb * 1024 * 1024:
            shutil.rmtree(session_dir, ignore_errors=True)
            raise HTTPException(
                status_code=400,
                detail=f"חריגה ממגבלת הגודל הכוללת ({UPLOAD_LIMITS.max_total_mb}MB).",
            )
        dest = session_dir / Path(uf.filename).name
        dest.write_bytes(content)
        saved_paths.append(dest)

    syllabus_path = session_dir / Path(syllabus_file.filename).name
    syllabus_path.write_bytes(await syllabus_file.read())

    exam_docs = extract_many(saved_paths)
    syllabus_doc = extract_pdf(syllabus_path)

    # כשל חילוץ אינו שקט (פרק 07): הקובץ מדווח למשתמש, השאר ממשיכים.
    # קובץ ללא שכבת טקסט עדיין נשלח למודל כ-PDF (fallback סריקה) ולכן אינו "כשל".
    failed_files = [d.source_file for d in exam_docs if not d.extraction_ok and not d.path]

    batch = classify_exams(exam_docs, syllabus_doc)
    batch.course = course

    _sessions[session_id] = {
        "course": course,
        "max_pages": max_pages,
        "classification": batch,
        "failed_files": failed_files,
        "merged": None,
    }

    return {
        "session_id": session_id,
        "questions_found": len(batch.questions),
        "syllabus_topics": batch.syllabus_topics,
        "failed_files": failed_files,
    }


@app.post("/api/merge/{session_id}")
def merge(session_id: str):
    session = _get_session(session_id)

    # מנוע האיחוד האמיתי דורש מפתח API. בלעדיו לא נכשלים בשקט ולא מתחזים
    # לאיחוד סמנטי -- נופלים למיזוג offline ומדווחים על כך במפורש ב-dedup_mode.
    if os.environ.get("ANTHROPIC_API_KEY"):
        merged = merge_batch(session["classification"], max_pages=session["max_pages"])
        session["dedup_mode"] = "llm"
    else:
        merged = merge_batch_offline(
            session["classification"], max_pages=session["max_pages"]
        )
        session["dedup_mode"] = "offline"

    session["merged"] = merged
    return {"dedup_mode": session["dedup_mode"], **merged.model_dump()}


@app.get("/api/preview/{session_id}")
def preview(session_id: str):
    return _get_merged(session_id)


@app.post("/api/preview/{session_id}/remove")
def remove_items(session_id: str, item_indices: List[int]):
    """MVP: הסרת פריטים בלבד (לא עריכת תוכן -- ראו פרק 3.4 ב-PRD)."""

    merged = _get_merged(session_id)
    drop = set(item_indices)
    merged.items = [item for i, item in enumerate(merged.items) if i not in drop]
    return merged


@app.post("/api/export/{session_id}")
def export(
    session_id: str,
    format: ExportFormat,
    font_name: str = "Arial",
    font_size_pt: int = 11,
):
    merged = _get_merged(session_id)
    output_path = _session_dir(session_id) / f"cheatsheet.{format.value}"

    builder = build_docx if format == ExportFormat.DOCX else build_pdf
    builder(merged, output_path, font_name=font_name, font_size_pt=font_size_pt)

    return FileResponse(
        path=output_path,
        filename=output_path.name,
        media_type="application/octet-stream",
    )


@app.delete("/api/session/{session_id}")
def delete_session(session_id: str):
    """מחיקה מלאה בסיום הסשן -- ללא אחסון קבוע (פרק 07, החלטה סופית)."""

    _sessions.pop(session_id, None)
    shutil.rmtree(_session_dir(session_id), ignore_errors=True)
    return {"deleted": True}


@app.get("/health")
def health():
    return {"status": "ok"}
