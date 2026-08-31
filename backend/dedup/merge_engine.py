"""
מנוע איחוד כפילויות -- עובד מול fixtures/sample_classified.json מהיום הראשון,
לא תלוי במודול הסיווג האמיתי.

לפי החלטת הצוות (פרק 03 ב-PRD): סף הדמיון הקובע "כפילות" הוא שיפוט סמנטי
חופשי של המודל (LLM), ללא סף מספרי קשיח. הפונקציות כאן שולחות למודל קבוצות
שאלות מאותו נושא+סוג, ומבקשות ממנו להחזיר איחוד ישירות במבנה חוזה שלב 2.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from typing import Dict, List

import anthropic

from backend.schemas import ClassificationBatch, ClassifiedQuestion, MergedBank, QuestionType

logger = logging.getLogger(__name__)

MODEL_NAME = os.environ.get("DEDUP_MODEL", "claude-sonnet-4-5")

SYSTEM_PROMPT = """\
את/ה מנוע איחוד כפילויות עבור בנק שאלות אקדמי (דף נוסחאות).
תקבל/י קבוצת שאלות מאותו נושא ומאותו סוג (closed / open_calc / code).
החלטה על "כפילות" היא שיפוט סמנטי שלך -- אין סף מספרי, השתמש/י בהבנה
של המשמעות (שתי שאלות עם ניסוח שונה אך אותו רעיון/פתרון = כפילות).

כללים לפי סוג:
- closed: אחד כפילויות זהות/דומות מאוד לפריט אחד עם correct_answer ו-distractors
  (תשובות מטעות סבירות אם ניתן להסיק, אחרת רשימה ריקה), ו-sources = כל התוויות
  שהופיעו.
- open_calc: קבץ שאלות דומות (אותו נושא/סוג חישוב) ל"משפחה" אחת: בחר/י representative
  אחד עם הנתונים המלאים ביותר, והשאר כ-variants.
- code: אל תשכפל/י את הקוד המלא -- reference_only=true, code_snippet=null,
  אלא אם הקוד קצר מאוד (מתחת ל-5 שורות) ואז אפשר reference_only=false עם
  code_snippet מקוצר.

לעולם אל תמציא/י תוכן שלא הופיע במקור. אל תשלים/י raw תשובה חסרה.
החזר/י אך ורק JSON תקין לפי הסכמה שתקבל/י, ללא טקסט נוסף.
"""

USER_PROMPT_TEMPLATE = """\
נושא: {topic}
סוג שאלה: {qtype}

השאלות בקבוצה זו (לפני איחוד):
{questions_json}

החזר/י JSON של רשימת פריטים מאוחדים במבנה המתאים לסוג {qtype}.
"""


def _group_by_topic_and_type(
    questions: List[ClassifiedQuestion],
) -> Dict[tuple, List[ClassifiedQuestion]]:
    groups: Dict[tuple, List[ClassifiedQuestion]] = defaultdict(list)
    for q in questions:
        if not q.has_answer:
            logger.info("Skipping question without answer: %s", q.id)
            continue
        groups[(q.topic, q.type)].append(q)
    return groups


def _build_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY לא מוגדר בסביבה.")
    return anthropic.Anthropic(api_key=api_key)


def _merge_group(
    client: anthropic.Anthropic, topic: str, qtype: QuestionType, group: List[ClassifiedQuestion]
) -> List[dict]:
    questions_payload = [
        {
            "question_text": q.question_text,
            "answer_text": q.answer_text,
            "source_label": q.source_label,
        }
        for q in group
    ]

    prompt = USER_PROMPT_TEMPLATE.format(
        topic=topic,
        qtype=qtype.value,
        questions_json=json.dumps(questions_payload, ensure_ascii=False, indent=2),
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
        raise ValueError(f"תגובת מנוע האיחוד אינה JSON תקין: {exc}\nRaw: {raw[:500]}") from exc

    for item in parsed:
        item.setdefault("type", qtype.value)
        item["topic"] = topic

    return parsed


def merge_batch(batch: ClassificationBatch, max_pages: int) -> MergedBank:
    """מאחד אצווה שלמה של שאלות מסווגות לבנק מרוכז (חוזה שלב 2)."""

    client = _build_client()
    groups = _group_by_topic_and_type(batch.questions)

    merged_items: List[dict] = []
    for (topic, qtype), group in groups.items():
        merged_items.extend(_merge_group(client, topic, qtype, group))

    return MergedBank(course=batch.course, max_pages=max_pages, items=merged_items)


def merge_batch_offline(batch: ClassificationBatch, max_pages: int) -> MergedBank:
    """
    גרסת fallback ללא קריאת API -- קיבוץ מבוסס טקסט זהה בלבד (ללא שיפוט סמנטי).
    שימושי לבדיקות/פיתוח מקומי כשאין מפתח API זמין. אינה תחליף למנוע האמיתי.
    """

    groups = _group_by_topic_and_type(batch.questions)
    merged_items: List[dict] = []

    for (topic, qtype), group in groups.items():
        if qtype == QuestionType.CLOSED:
            merged_items.append(
                {
                    "type": "closed",
                    "topic": topic,
                    "question_text": group[0].question_text,
                    "correct_answer": group[0].answer_text,
                    "distractors": [],
                    "sources": [q.source_label for q in group],
                }
            )
        elif qtype == QuestionType.OPEN_CALC:
            rep, *rest = group
            merged_items.append(
                {
                    "type": "open_calc",
                    "topic": topic,
                    "representative": {
                        "question_text": rep.question_text,
                        "answer_text": rep.answer_text,
                        "source_label": rep.source_label,
                    },
                    "variants": [
                        {
                            "question_text": q.question_text,
                            "answer_text": q.answer_text,
                            "source_label": q.source_label,
                        }
                        for q in rest
                    ],
                }
            )
        else:  # CODE
            merged_items.append(
                {
                    "type": "code",
                    "topic": topic,
                    "reference_only": True,
                    "code_snippet": None,
                    "sources": [q.source_label for q in group],
                }
            )

    return MergedBank(course=batch.course, max_pages=max_pages, items=merged_items)
