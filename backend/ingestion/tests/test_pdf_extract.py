from pathlib import Path

from backend.ingestion.pdf_extract import label_from_filename, parse_syllabus_topics
from backend.schemas import ClassifiedBatch, ClassifiedQuestion, QuestionType


def test_label_from_filename_moed_patterns():
    assert label_from_filename("exam_2023_A.pdf") == "מועד א 2023"
    assert label_from_filename("moed_b_2022.pdf") == "מועד ב 2022"
    assert "מועד" in label_from_filename("מועד_א_2024.pdf")


def test_parse_syllabus_topics_bullet_list():
    text = """
    סילבוס מערכות הפעלה
    1. עקביות אחרי קריסה
    2. ביצועי דיסק
    - סנכרון תהליכים
    * ניהול זיכרון
    """
    topics = parse_syllabus_topics(text)
    assert "עקביות אחרי קריסה" in topics
    assert "ביצועי דיסק" in topics
    assert "סנכרון תהליכים" in topics
    assert "ניהול זיכרון" in topics


def test_classified_question_schema_roundtrip():
    q = ClassifiedQuestion(
        id="q_0001",
        source_file="exam_2023_A.pdf",
        source_label="מועד א 2023",
        type=QuestionType.CLOSED,
        topic="עקביות אחרי קריסה",
        question_text="שאלה לדוגמה",
        answer_text="תשובה",
        has_answer=True,
    )
    data = q.model_dump()
    again = ClassifiedQuestion.model_validate(data)
    assert again.type == QuestionType.CLOSED
    assert again.has_answer is True


def test_empty_answer_forces_has_answer_false():
    q = ClassifiedQuestion(
        id="q_0009",
        source_file="x.pdf",
        source_label="מקור",
        type=QuestionType.OPEN_CALC,
        topic="ביצועי דיסק",
        question_text="שאלה בלי תשובה",
        answer_text="   ",
        has_answer=True,
    )
    assert q.has_answer is False


def test_fixture_matches_stage1_contract():
    fixture_path = Path(__file__).resolve().parents[3] / "fixtures" / "sample_classified.json"
    batch = ClassifiedBatch.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    assert len(batch.questions) >= 4
    types = {q.type for q in batch.questions}
    assert QuestionType.CLOSED in types
    assert QuestionType.OPEN_CALC in types
    assert QuestionType.CODE in types
    # Intentional near-duplicate closed questions for Person B
    closed = [q for q in batch.questions if q.type == QuestionType.CLOSED]
    assert len(closed) >= 2
