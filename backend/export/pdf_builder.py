"""
יצירת PDF מתוך הבנק המרוכז.

מסלול ראשי (לפי החלטת הצוות בפרק 05/10): המרה מ-docx באמצעות LibreOffice
headless, כדי לא לכפול מימוש בין Word ל-PDF. אומת ידנית ש-RTL נשמר נכון
בהמרה זו (ראו docs/rtl_poc_notes.md).

מסלול חלופי (fallback): אם בעתיד יתגלו בעיות RTL בהמרה (למשל עם תוכן מורכב
יותר מה-PoC), יש לעבור ל-WeasyPrint (HTML/CSS עם dir="rtl") -- ראו
build_pdf_via_weasyprint() למטה כשלד לא-מיושם, שיש להשלים אם המסלול הראשי
נכשל בפועל.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from backend.export.docx_builder import build_docx
from backend.schemas import MergedBank


class PdfConversionError(RuntimeError):
    pass


# ב-Railway (nixpacks.toml) LibreOffice נמצא ב-PATH. בפיתוח מקומי על Windows
# הוא בדרך כלל לא, ולכן נבדקת גם התקנת ברירת המחדל.
_WINDOWS_SOFFICE = Path(r"C:\Program Files\LibreOffice\program\soffice.exe")


def _soffice_path() -> str:
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return found
    if _WINDOWS_SOFFICE.exists():
        return str(_WINDOWS_SOFFICE)
    raise PdfConversionError(
        "LibreOffice (soffice) לא נמצא. התקינו אותו, או ייצאו ל-docx במקום ל-PDF."
    )


def build_pdf_via_libreoffice(
    bank: MergedBank,
    output_path: Path,
    font_name: str = "Arial",
    font_size_pt: int = 11,
) -> Path:
    """
    בונה docx זמני ואז ממיר ל-PDF דרך `soffice --headless --convert-to pdf`.
    זהו המסלול הראשי -- אומת ב-PoC שכיווניות RTL נשמרת נכון בהמרה זו.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_docx = output_path.with_suffix(".tmp.docx")
    build_docx(bank, tmp_docx, font_name=font_name, font_size_pt=font_size_pt)

    result = subprocess.run(
        [
            _soffice_path(),
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(output_path.parent),
            str(tmp_docx),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    generated_pdf = tmp_docx.with_suffix(".pdf")

    if result.returncode != 0 or not generated_pdf.exists():
        tmp_docx.unlink(missing_ok=True)
        raise PdfConversionError(
            f"המרת LibreOffice נכשלה (code={result.returncode}): {result.stderr}\n"
            "שקלו מעבר למסלול WeasyPrint (build_pdf_via_weasyprint)."
        )

    generated_pdf.rename(output_path)
    tmp_docx.unlink(missing_ok=True)
    return output_path


def build_pdf_via_weasyprint(bank: MergedBank, output_path: Path) -> Path:
    """
    מסלול חלופי (לא מיושם) -- לשימוש רק אם build_pdf_via_libreoffice נכשל
    בפועל על RTL בתוכן אמיתי (בשונה מה-PoC המצומצם).

    יישום מוצע: בניית HTML עם <html dir="rtl" lang="he">, CSS עם
    direction: rtl; unicode-bidi: embed; לפסקאות עברית, ו-direction: ltr
    מפורש לבלוקי קוד/נוסחה, ואז המרה עם weasyprint.HTML(string=html).write_pdf().
    נדרש `pip install weasyprint` (לא מותקן בסביבת הפיתוח הנוכחית).
    """

    raise NotImplementedError(
        "מסלול WeasyPrint לא מיושם -- נדרש רק אם התגלתה בעיית RTL בפועל "
        "במסלול הראשי (LibreOffice). ראו הערת התיעוד בראש הקובץ."
    )


def build_pdf(
    bank: MergedBank,
    output_path: Path,
    font_name: str = "Arial",
    font_size_pt: int = 11,
) -> Path:
    """נקודת הכניסה המומלצת: מנסה LibreOffice, לא נופל אוטומטית ל-WeasyPrint."""

    return build_pdf_via_libreoffice(
        bank, output_path, font_name=font_name, font_size_pt=font_size_pt
    )
