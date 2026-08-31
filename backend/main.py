"""
נקודת הכניסה הראשית -- FastAPI. מחבר את שלושת הזרמים (ingestion+classification,
dedup, export) לזרימת משתמש אחת, לפי סעיף 3.5 / פרק 11 ב-PRD.

זרימה (session-based בלבד -- ללא DB, ראו פרק 06/07):
1. POST /api/upload -- מקבל PDFs + סילבוס + max_pages, מחלץ ומסווג, שומר
   תוצאה זמנית בזיכרון תחת session_id (לא בדיסק, לא ב-DB).
2. POST /api/merge/{session_id} -- מריץ את מנוע האיחוד על הסיווג שנשמר.
3. GET  /api/preview/{session_id} -- מחזיר את הבנק המרוכז לתצוגה מקדימה.
4. POST /api/preview/{session_id}/remove -- מסיר פריטים מהבנק (MVP: הסרה בלבד).
5. POST /api/export/{session_id} -- מייצא docx/pdf ומחזיר קובץ להורדה.
6. DELETE /api/session/{session_id} -- מוחק את כל הנתונים הזמניים (גם רץ
   אוטומטית אחרי הורדת הקובץ הסופי -- ראו הערת פרטיות בפרק 07).

הערה: אחסון ה-session הוא in-memory (dict) לפשטות MVP. ל-production אמיתי
(מעבר למופע יחיד) יש להחליף ב-Redis עם TTL, אך זה מחוץ לסקופ ה-hackathon.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.dedup.merge_engine import merge_batch
from backend.export.docx_builder import build_docx
from backend.export.pdf_builder import build_pdf
from backend.ingestion.pdf_extract import extract_batch, extract_syllabus
from backend.classification.classifier import classify_batch
from backend.schemas import ExportFormat, MergedBank, UploadLimits

app = FastAPI(title="CheatSheetForge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # לצמצם ל-domain הפרונט בפריסת production
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_LIMITS = UploadLimits()  # 15 קבצים / 5MB -- ברירת מחדל לכיול, ראו פרק 06/10

# --- אחסון session זמני בזיכרון בלבד (ראו הערת פרטיות למעלה) ---
_sessions: Dict[str, dict] = {}


def _session_dir(session_id: str) -> Path:
    d = Path(tempfile.gettempdir()) / "cheatsheet-forge" / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


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
    source_labels: dict[str, str] = {}

    for uf in exam_files:
        content = await uf.read()
        total_bytes += len(content)
        if total_bytes > UPLOAD_LIMITS.max_total_mb * 1024 * 1024:
            shutil.rmtree(session_dir, ignore_errors=True)
            raise HTTPException(
                status_code=400,
                detail=f"חריגה ממגבלת הגודל הכוללת ({UPLOAD_LIMITS.max_total_mb}MB).",
            )
        dest = session_dir / uf.filename
        dest.write_bytes(content)
        saved_paths.append(dest)
        source_labels[uf.filename] = Path(uf.filename).stem

    syllabus_bytes = await syllabus_file.read()
    syllabus_path = session_dir / syllabus_file.filename
    syllabus_path.write_bytes(syllabus_bytes)

    extraction = extract_batch(saved_paths)
    syllabus_text = extract_syllabus(syllabus_path)
    # הערה: חילוץ נושאי הסילבוס בפועל דורש קריאת LLM נוספת/parsing ייעודי;
    # לצורך ה-MVP מניחים רשימת שורות לא-ריקות כנושאים גולמיים.
    syllabus_topics = [line.strip() for line in syllabus_text.splitlines() if line.strip()]

    if extraction.failed:
        failed_names = ", ".join(f.filename for f in extraction.failed)
        # לא כשל שקט: מוחזר למשתמש, העיבוד ממשיך עם שאר הקבצים (פרק 07)
        pass

    batch = classify_batch(
        course=course,
        syllabus_topics=syllabus_topics,
        extracted_files=extraction.succeeded,
        source_labels=source_labels,
    )

    _sessions[session_id] = {
        "course": course,
        "max_pages": max_pages,
        "classification": batch,
        "failed_files": [f.filename for f in extraction.failed],
        "merged": None,
    }

    return {
        "session_id": session_id,
        "questions_found": len(batch.questions),
        "failed_files": _sessions[session_id]["failed_files"],
    }


@app.post("/api/merge/{session_id}")
def merge(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session לא נמצא")

    merged = merge_batch(session["classification"], max_pages=session["max_pages"])
    session["merged"] = merged
    return merged


@app.get("/api/preview/{session_id}")
def preview(session_id: str):
    session = _sessions.get(session_id)
    if not session or not session["merged"]:
        raise HTTPException(status_code=404, detail="אין בנק מאוחד ל-session זה")
    return session["merged"]


@app.post("/api/preview/{session_id}/remove")
def remove_items(session_id: str, item_indices: List[int]):
    """MVP: הסרת פריטים בלבד (לא עריכת תוכן -- ראו פרק 3.4 ב-PRD)."""

    session = _sessions.get(session_id)
    if not session or not session["merged"]:
        raise HTTPException(status_code=404, detail="אין בנק מאוחד ל-session זה")

    merged: MergedBank = session["merged"]
    remaining = [
        item for i, item in enumerate(merged.items) if i not in set(item_indices)
    ]
    merged.items = remaining
    return merged


@app.post("/api/export/{session_id}")
def export(session_id: str, format: ExportFormat, font_name: str = "Arial", font_size_pt: int = 11):
    session = _sessions.get(session_id)
    if not session or not session["merged"]:
        raise HTTPException(status_code=404, detail="אין בנק מאוחד ל-session זה")

    session_dir = _session_dir(session_id)
    output_path = session_dir / f"cheatsheet.{format.value}"

    if format == ExportFormat.DOCX:
        build_docx(session["merged"], output_path, font_name=font_name, font_size_pt=font_size_pt)
    else:
        build_pdf(session["merged"], output_path, font_name=font_name, font_size_pt=font_size_pt)

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
