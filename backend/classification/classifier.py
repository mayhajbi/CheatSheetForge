"""
סיווג שאלות באמצעות Anthropic API (Claude).
לכל שאלה: סוג (closed/open_calc/code) + נושא מתוך הסילבוס שהועלה.

עיקרון קשיח (פרק 07 + פרק 11 ב-PRD): לעולם אין להמציא תוכן. אם המודל לא מצליח
לשייך שאלה לנושא מהסילבוס, או לא מוצא תשובה בטקסט -- זה מסומן במפורש
(has_answer=False) ולא מוזרם הלאה בשקט.

הרצה בפועל דורשת ANTHROPIC_API_KEY בסביבה (env). הקובץ הזה לא נבדק מול ה-API
האמיתי בסביבת הפיתוח הנוכחית (ראו הערה ב-README) -- יש להריץ מול fixture
ולוודא ידנית מול קריאה אמיתית ל-API לפני ההצגה.
"""

from __future__ import annotations

import json
import logging
import os
from typing import List

import anthropic

from backend.ingestion.pdf_extract import ExtractedFile
from backend.schemas import ClassificationBatch, ClassifiedQuestion, QuestionType

logger = logging.getLogger(__name__)

MODEL_NAME = os.environ.get("CLASSIFIER_MODEL", "claude-sonnet-4-5")

SYSTEM_PROMPT = """\
את/ה מנוע סיווג שאלות בחינה עבור דף נוסחאות אקדמי.
תפקידך: לחלץ מטקסט גולמי של מבחן פתור את כל השאלות (עם התשובות/פתרונות שלהן),
ולסווג כל שאלה.

כללים קשיחים:
1. סווג כל שאלה לאחד משלושת הסוגים בלבד: "closed" (רב-ברירה/נכון-לא נכון),
   "open_calc" (שאלה פתוחה מבוססת חישוב/ניתוח), "code" (מימוש קוד מלא).
2. שבץ כל שאלה תחת נושא אחד מתוך רשימת נושאי הסילבוס שתסופק לך -- אסור
   להמציא נושא שאינו ברשימה. אם באמת אין התאמה, בחר את הקרוב ביותר ברשימה.
3. אם לשאלה אין תשובה/פתרון בטקסט הנתון -- סמן has_answer=false ואל תמלא
   תשובה מהזיכרון הכללי שלך.
4. אל תוסיף שאלות שאינן קיימות בטקסט. אל תשלים תוכן חסר.
5. החזר אך ורק JSON תקין לפי הסכמה שתקבל, ללא טקסט נוסף לפני/אחרי.
"""

USER_PROMPT_TEMPLATE = """\
נושאי הסילבוס הזמינים (לבחירה בלבד, לא לחרוג מהם):
{topics}

תווית מקור לקובץ הזה (יש להוסיף לכל שאלה): {source_label}
שם הקובץ: {source_file}

טקסט המבחן שחולץ:
---
{raw_text}
---

החזר JSON במבנה הבא בדיוק (רשימת שאלות):
[
  {{
    "type": "closed | open_calc | code",
    "topic": "<אחד מנושאי הסילבוס לעיל>",
    "question_text": "...",
    "answer_text": "...",
    "has_answer": true
  }}
]
"""


def _build_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY לא מוגדר בסביבה. יש להגדיר משתנה סביבה לפני "
            "הרצת שלב הסיווג."
        )
    return anthropic.Anthropic(api_key=api_key)


def classify_file(
    client: anthropic.Anthropic,
    extracted: ExtractedFile,
    source_label: str,
    syllabus_topics: List[str],
    start_id: int,
) -> List[ClassifiedQuestion]:
    """שולח את הטקסט של קובץ בודד למודל ומחזיר רשימת שאלות מסווגות."""

    if not extracted.ok:
        logger.warning("Skipping classification for failed file %s", extracted.filename)
        return []

    prompt = USER_PROMPT_TEMPLATE.format(
        topics="\n".join(f"- {t}" for t in syllabus_topics),
        source_label=source_label,
        source_file=extracted.filename,
        raw_text=extracted.text,
    )

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = "".join(block.text for block in response.content if block.type == "text")
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"תגובת המודל עבור {extracted.filename} אינה JSON תקין: {exc}\nRaw: {raw[:500]}"
        ) from exc

    questions: List[ClassifiedQuestion] = []
    for i, item in enumerate(parsed):
        questions.append(
            ClassifiedQuestion(
                id=f"q_{start_id + i:04d}",
                source_file=extracted.filename,
                source_label=source_label,
                type=QuestionType(item["type"]),
                topic=item["topic"],
                question_text=item["question_text"],
                answer_text=item.get("answer_text", ""),
                has_answer=item.get("has_answer", True),
            )
        )
    return questions


def classify_batch(
    course: str,
    syllabus_topics: List[str],
    extracted_files: List[ExtractedFile],
    source_labels: dict[str, str],
) -> ClassificationBatch:
    """מסווג אצווה שלמה של קבצים ומחזיר ClassificationBatch תואם-חוזה."""

    client = _build_client()
    all_questions: List[ClassifiedQuestion] = []
    next_id = 1

    for extracted in extracted_files:
        label = source_labels.get(extracted.filename, extracted.filename)
        qs = classify_file(client, extracted, label, syllabus_topics, next_id)
        all_questions.extend(qs)
        next_id += len(qs)

    return ClassificationBatch(
        course=course, syllabus_topics=syllabus_topics, questions=all_questions
    )
