"""
חוזה הנתונים המשותף בין שלושת מודולי הליבה (ingestion/classification -> dedup -> export).
כל שלושת המודולים מייבאים מכאן ולא מגדירים מבנים משלהם.
ראו docs/PRD.md פרק 12 להסבר המלא.

שינוי שדה כאן משפיע על כל השרשרת -- לתאם עם שני חברי הצוות האחרים לפני עריכה.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    """שלושת סוגי השאלות הנתמכים -- אין ערך רביעי."""

    CLOSED = "closed"
    OPEN_CALC = "open_calc"
    CODE = "code"


# ---------------------------------------------------------------------------
# שלב 1 -> 2: פלט הסיווג (מיוצר ע"י ingestion+classification, נצרך ע"י dedup)
# ---------------------------------------------------------------------------


class ClassifiedQuestion(BaseModel):
    """שאלה בודדת, אחרי חילוץ מ-PDF וסיווג ע"י המודל."""

    id: str = Field(..., description="מזהה ייחודי, לדוגמה q_0001")
    source_file: str = Field(..., description="שם קובץ המקור, לדוגמה exam_2023_A.pdf")
    source_label: str = Field(..., description="תווית מקור קריאה לאדם, לדוגמה 'מועד א 2023'")
    type: QuestionType
    topic: str = Field(..., description="נושא מתוך קובץ הסילבוס שהועלה -- לא ערך חופשי")
    question_text: str
    answer_text: str
    has_answer: bool = Field(
        default=True,
        description=(
            "נשמר לצורך שקיפות. אמור להיות True תמיד ב-MVP כי הקלט חייב לכלול "
            "פתרונות. אם False בפועל (כשל חילוץ) -- הפריט מסומן ולא מוזרם לאיחוד."
        ),
    )


class ClassificationBatch(BaseModel):
    """הפלט המלא של שלב הסיווג עבור אצוות קבצים אחת."""

    course: str
    syllabus_topics: List[str] = Field(default_factory=list)
    questions: List[ClassifiedQuestion]


# ---------------------------------------------------------------------------
# שלב 2 -> 3: פלט האיחוד (מיוצר ע"י dedup, נצרך ע"י export)
# ---------------------------------------------------------------------------


class ClosedItem(BaseModel):
    type: QuestionType = QuestionType.CLOSED
    topic: str
    question_text: str
    correct_answer: str
    distractors: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


class OpenCalcVariant(BaseModel):
    question_text: str
    answer_text: str
    source_label: str


class OpenCalcItem(BaseModel):
    type: QuestionType = QuestionType.OPEN_CALC
    topic: str
    representative: OpenCalcVariant
    variants: List[OpenCalcVariant] = Field(default_factory=list)


class CodeItem(BaseModel):
    type: QuestionType = QuestionType.CODE
    topic: str
    reference_only: bool = True
    code_snippet: Optional[str] = None
    sources: List[str] = Field(default_factory=list)


MergedItem = ClosedItem | OpenCalcItem | CodeItem


class MergedBank(BaseModel):
    """הבנק המרוכז -- הקלט למודול הייצוא."""

    course: str
    max_pages: int
    items: List[dict] = Field(
        ...,
        description=(
            "כל איבר הוא ClosedItem / OpenCalcItem / CodeItem לפי שדה type. "
            "נשמר כ-dict גנרי כדי לאפשר union פשוט ב-JSON; ראו dedup/merge_engine.py "
            "לפענוח בפועל לפי type."
        ),
    )


# ---------------------------------------------------------------------------
# בקשות/תגובות API (main.py)
# ---------------------------------------------------------------------------


class UploadLimits(BaseModel):
    max_files: int = 15
    max_total_mb: int = 5


class ExportFormat(str, Enum):
    DOCX = "docx"
    PDF = "pdf"


class ExportRequest(BaseModel):
    format: ExportFormat
    max_pages: int
    font_name: str = "Arial"
    font_size_pt: int = 11
