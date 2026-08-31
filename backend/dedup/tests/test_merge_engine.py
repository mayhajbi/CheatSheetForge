"""
בדיקת קבלה לאדם B (פרק 12): fixture עם 2-3 כפילויות מכוונות -> JSON מאוחד
נכון מול חוזה שלב 2.

הרצה: pytest backend/dedup/tests/test_merge_engine.py
(דורש pydantic מותקן -- ראו backend/requirements.txt)
"""

import json
from pathlib import Path

from backend.dedup.merge_engine import merge_batch_offline
from backend.schemas import ClassificationBatch

FIXTURE_PATH = Path(__file__).resolve().parents[3] / "fixtures" / "sample_classified.json"


def load_fixture_batch() -> ClassificationBatch:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return ClassificationBatch(**data)


def test_fixture_has_intentional_duplicates():
    batch = load_fixture_batch()
    # ה-fixture מכיל 2 שאלות closed על אותו נושא (כפילות מכוונת)
    closed = [q for q in batch.questions if q.type.value == "closed"]
    assert len(closed) == 2
    assert closed[0].topic == closed[1].topic


def test_merge_offline_deduplicates_closed_questions():
    batch = load_fixture_batch()
    merged = merge_batch_offline(batch, max_pages=4)

    closed_items = [i for i in merged.items if i["type"] == "closed"]
    assert len(closed_items) == 1, "שתי השאלות הסגורות הזהות אמורות להתאחד לפריט אחד"
    assert len(closed_items[0]["sources"]) == 2


def test_merge_offline_groups_open_calc_into_family():
    batch = load_fixture_batch()
    merged = merge_batch_offline(batch, max_pages=4)

    open_items = [i for i in merged.items if i["type"] == "open_calc"]
    assert len(open_items) == 1, "שתי שאלות ה-open_calc על אותו נושא אמורות להתקבץ למשפחה אחת"
    assert "representative" in open_items[0]
    assert len(open_items[0]["variants"]) == 1


def test_merge_offline_code_question_is_reference_only():
    batch = load_fixture_batch()
    merged = merge_batch_offline(batch, max_pages=4)

    code_items = [i for i in merged.items if i["type"] == "code"]
    assert len(code_items) == 1
    assert code_items[0]["reference_only"] is True
    assert code_items[0]["code_snippet"] is None
