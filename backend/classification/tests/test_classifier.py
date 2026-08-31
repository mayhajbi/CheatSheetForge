import json
from pathlib import Path

from backend.classification.classifier import QuestionClassifier, _strip_json_fence
from backend.ingestion.pdf_extract import ExtractedDocument
from backend.schemas import QuestionType


def test_strip_json_fence():
    raw = """```json
{"questions": []}
```"""
    assert _strip_json_fence(raw) == '{"questions": []}'


def test_classify_document_with_mock_client():
    payload = {
        "questions": [
            {
                "id": "q_0001",
                "source_file": "exam_2023_A.pdf",
                "source_label": "מועד א 2023",
                "type": "closed",
                "topic": "עקביות אחרי קריסה",
                "question_text": "האם journaling תמיד משלים כתיבות?",
                "answer_text": "לא",
                "has_answer": True,
            },
            {
                "id": "q_0002",
                "source_file": "exam_2023_A.pdf",
                "source_label": "מועד א 2023",
                "type": "open_calc",
                "topic": "ביצועי דיסק",
                "question_text": "חשבו זמן קריאה",
                "answer_text": "",
                "has_answer": True,
            },
        ]
    }

    class FakeClient:
        def generate(self, *, system: str, user: str, max_tokens: int) -> str:
            return json.dumps(payload, ensure_ascii=False)

        def generate_with_pdf(
            self, *, system: str, user: str, pdf_bytes: bytes, max_tokens: int
        ) -> str:
            raise RuntimeError("should not use PDF path for text docs")

    classifier = QuestionClassifier(client=FakeClient(), model="mock")
    doc = ExtractedDocument(
        source_file="exam_2023_A.pdf",
        source_label="מועד א 2023",
        text="שאלה 1 ... תשובה ...",
        page_count=1,
        char_count=20,
        extraction_ok=True,
    )
    topics = ["עקביות אחרי קריסה", "ביצועי דיסק", "סנכרון תהליכים"]
    questions = classifier.classify_document(doc, topics, id_start=1)

    assert len(questions) == 2
    assert questions[0].type == QuestionType.CLOSED
    assert questions[0].topic == "עקביות אחרי קריסה"
    assert questions[1].has_answer is False


def test_scanned_pdf_uses_multimodal_fallback(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    payload = {
        "questions": [
            {
                "id": "q_0001",
                "source_file": "scan.pdf",
                "source_label": "סרוק",
                "type": "code",
                "topic": "סנכרון תהליכים",
                "question_text": "ממשו mutex",
                "answer_text": "קוד...",
                "has_answer": True,
            }
        ]
    }

    class FakeClient:
        def generate(self, *, system: str, user: str, max_tokens: int) -> str:
            raise RuntimeError("text path should not run")

        def generate_with_pdf(
            self, *, system: str, user: str, pdf_bytes: bytes, max_tokens: int
        ) -> str:
            assert pdf_bytes.startswith(b"%PDF")
            return json.dumps(payload, ensure_ascii=False)

    classifier = QuestionClassifier(client=FakeClient(), model="mock")
    doc = ExtractedDocument(
        source_file="scan.pdf",
        source_label="סרוק",
        text="",
        page_count=2,
        char_count=0,
        extraction_ok=False,
        warning="scanned",
        path=str(pdf_path),
    )
    questions = classifier.classify_document(doc, ["סנכרון תהליכים"], id_start=1)
    assert len(questions) == 1
    assert questions[0].type == QuestionType.CODE


def test_failed_extraction_without_path_returns_empty():
    class Boom:
        def generate(self, *, system: str, user: str, max_tokens: int) -> str:
            raise RuntimeError("no call")

        def generate_with_pdf(
            self, *, system: str, user: str, pdf_bytes: bytes, max_tokens: int
        ) -> str:
            raise RuntimeError("no call")

    classifier = QuestionClassifier(client=Boom(), model="mock")
    doc = ExtractedDocument(
        source_file="scan.pdf",
        source_label="סרוק",
        text="",
        page_count=0,
        char_count=0,
        extraction_ok=False,
        warning="no text",
        path=None,
    )
    assert classifier.classify_document(doc, ["נושא"]) == []


def test_sample_fixture_still_valid_for_b():
    path = Path(__file__).resolve().parents[3] / "fixtures" / "sample_classified.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "questions" in data
    assert all("type" in q and "topic" in q for q in data["questions"])
