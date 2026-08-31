"""Gemini-backed question classification (Person A)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Protocol

from google import genai
from google.genai import types

from backend.ingestion.pdf_extract import ExtractedDocument, parse_syllabus_topics
from backend.schemas import ClassifiedBatch, ClassifiedQuestion, QuestionType

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_MAX_TOKENS = int(os.getenv("CLASSIFY_MAX_TOKENS", "16384"))

_SYSTEM = """\
את/ה מסווג/ת שאלות ממבחנים ותרגילי בית פתורים בעברית לקורס אקדמי.
החזר אך ורק JSON תקין (בלי markdown ובלי הסברים).

כללי חובה:
1. אל תמציא תוכן. אם אין תשובה במקור — has_answer=false ו-answer_text ריק.
2. type חייב להיות בדיוק אחד מ: closed | open_calc | code
3. topic חייב להיות אחד מהנושאים ברשימת הסילבוס שסופקה (העתק מדויק). אם אין התאמה סבירה — בחר את הנושא הקרוב ביותר מהרשימה.
4. חלק את המסמך לשאלות נפרדות (שאלה+תשובה). אל תאחד שאלות שונות.
5. שמור על עברית כפי שמופיעה במקור; קוד/נוסחאות באנגלית כפי שהם.
6. אם המסמך הוא סריקה/תמונה — קרא את העמודים בעיון והעתק טקסט כפי שמופיע.
"""


class GeminiClient(Protocol):
    """Minimal interface so tests can inject a fake client."""

    def generate(self, *, system: str, user: str, max_tokens: int) -> str: ...

    def generate_with_pdf(
        self, *, system: str, user: str, pdf_bytes: bytes, max_tokens: int
    ) -> str: ...


class GenAIGeminiClient:
    """Wrapper around google-genai Client."""

    def __init__(self, client: genai.Client, model: str) -> None:
        self._client = client
        self._model = model

    def generate(self, *, system: str, user: str, max_tokens: int) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini returned an empty response")
        return text

    def generate_with_pdf(
        self, *, system: str, user: str, pdf_bytes: bytes, max_tokens: int
    ) -> str:
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                user,
            ],
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Gemini returned an empty response for PDF input")
        return text


def _json_schema_hint(*, source_file: str, source_label: str, id_start: int) -> str:
    return f"""\
החזר אובייקט JSON במבנה:
{{
  "questions": [
    {{
      "id": "q_{id_start:04d}",
      "source_file": "{source_file}",
      "source_label": "{source_label}",
      "type": "closed|open_calc|code",
      "topic": "<נושא מהסילבוס>",
      "question_text": "...",
      "answer_text": "...",
      "has_answer": true
    }}
  ]
}}

התחל את מספרי ה-id מ-q_{id_start:04d} והעלה ב-1 לכל שאלה.
"""


def _build_user_prompt(
    *,
    syllabus_topics: list[str],
    doc: ExtractedDocument,
    id_start: int,
) -> str:
    topics_block = "\n".join(f"- {t}" for t in syllabus_topics) or "- (לא סופקו נושאים)"
    return f"""\
נושאי הסילבוס המותרים:
{topics_block}

קובץ מקור: {doc.source_file}
תווית מקור (source_label): {doc.source_label}

טקסט המבחן/תרגיל:
---
{doc.text}
---

{_json_schema_hint(source_file=doc.source_file, source_label=doc.source_label, id_start=id_start)}
"""


def _build_pdf_user_prompt(
    *,
    syllabus_topics: list[str],
    doc: ExtractedDocument,
    id_start: int,
) -> str:
    topics_block = "\n".join(f"- {t}" for t in syllabus_topics) or "- (לא סופקו נושאים)"
    return f"""\
הקובץ המצורף הוא מבחן/תרגיל פתור (ייתכן סרוק).
קרא את כל העמודים, חלץ שאלות+תשובות, וסווג.

נושאי הסילבוס המותרים:
{topics_block}

קובץ מקור: {doc.source_file}
תווית מקור (source_label): {doc.source_label}

{_json_schema_hint(source_file=doc.source_file, source_label=doc.source_label, id_start=id_start)}
"""


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _coerce_question(raw: dict[str, Any], *, fallback_file: str, fallback_label: str) -> ClassifiedQuestion:
    q_type = raw.get("type", "open_calc")
    if q_type not in {t.value for t in QuestionType}:
        q_type = QuestionType.OPEN_CALC.value

    has_answer = bool(raw.get("has_answer", True))
    answer = (raw.get("answer_text") or "").strip()
    if not answer:
        has_answer = False

    return ClassifiedQuestion(
        id=str(raw.get("id") or "q_0000"),
        source_file=str(raw.get("source_file") or fallback_file),
        source_label=str(raw.get("source_label") or fallback_label),
        type=QuestionType(q_type),
        topic=str(raw.get("topic") or "כללי").strip() or "כללי",
        question_text=str(raw.get("question_text") or "").strip(),
        answer_text=answer,
        has_answer=has_answer,
    )


def _parse_questions_payload(
    raw_text: str,
    *,
    doc: ExtractedDocument,
    syllabus_topics: list[str],
    id_start: int,
) -> list[ClassifiedQuestion]:
    payload = json.loads(_strip_json_fence(raw_text))
    items = payload.get("questions", payload if isinstance(payload, list) else [])

    questions: list[ClassifiedQuestion] = []
    allowed = {t.casefold(): t for t in syllabus_topics}
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        q = _coerce_question(
            item,
            fallback_file=doc.source_file,
            fallback_label=doc.source_label,
        )
        if not q.question_text:
            continue
        snap = allowed.get(q.topic.casefold())
        if snap:
            q.topic = snap
        elif syllabus_topics and q.topic.casefold() not in allowed:
            q.topic = syllabus_topics[0] if len(syllabus_topics) == 1 else q.topic
        if not q.id or q.id == "q_0000":
            q.id = f"q_{id_start + i:04d}"
        questions.append(q)
    return questions


class QuestionClassifier:
    """Extract + classify questions from exam PDFs against a syllabus (Gemini)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        client: GeminiClient | None = None,
    ) -> None:
        self.model = model
        if client is not None:
            self.client = client
        else:
            key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not key:
                raise RuntimeError(
                    "Missing GEMINI_API_KEY (or GOOGLE_API_KEY). "
                    "Get one at https://aistudio.google.com/apikey"
                )
            self.client = GenAIGeminiClient(genai.Client(api_key=key), model=model)

    def classify_document(
        self,
        doc: ExtractedDocument,
        syllabus_topics: list[str],
        *,
        id_start: int = 1,
    ) -> list[ClassifiedQuestion]:
        # Prefer text layer when available (cheaper / faster).
        if doc.extraction_ok and doc.text.strip():
            raw_text = self.client.generate(
                system=_SYSTEM,
                user=_build_user_prompt(
                    syllabus_topics=syllabus_topics,
                    doc=doc,
                    id_start=id_start,
                ),
                max_tokens=DEFAULT_MAX_TOKENS,
            )
            return _parse_questions_payload(
                raw_text, doc=doc, syllabus_topics=syllabus_topics, id_start=id_start
            )

        # Scanned PDF fallback: send file bytes to Gemini vision/PDF understanding.
        if not doc.path or not Path(doc.path).exists():
            return []

        pdf_bytes = Path(doc.path).read_bytes()
        raw_text = self.client.generate_with_pdf(
            system=_SYSTEM,
            user=_build_pdf_user_prompt(
                syllabus_topics=syllabus_topics,
                doc=doc,
                id_start=id_start,
            ),
            pdf_bytes=pdf_bytes,
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        return _parse_questions_payload(
            raw_text, doc=doc, syllabus_topics=syllabus_topics, id_start=id_start
        )

    def classify_batch(
        self,
        exam_docs: list[ExtractedDocument],
        syllabus_doc: ExtractedDocument,
        *,
        syllabus_topics: list[str] | None = None,
    ) -> ClassifiedBatch:
        topics = syllabus_topics or parse_syllabus_topics(syllabus_doc.text)
        if not topics and syllabus_doc.extraction_ok:
            topics = self._extract_topics_via_llm(syllabus_doc.text)
        if not topics and syllabus_doc.path and Path(syllabus_doc.path).exists():
            topics = self._extract_topics_from_pdf(Path(syllabus_doc.path).read_bytes())

        all_questions: list[ClassifiedQuestion] = []
        next_id = 1
        for doc in exam_docs:
            can_text = doc.extraction_ok and bool(doc.text.strip())
            can_pdf = bool(doc.path and Path(doc.path).exists())
            if not can_text and not can_pdf:
                continue
            qs = self.classify_document(doc, topics, id_start=next_id)
            all_questions.extend(qs)
            next_id += max(len(qs), 1)

        return ClassifiedBatch(syllabus_topics=topics, questions=all_questions)

    def _extract_topics_via_llm(self, syllabus_text: str) -> list[str]:
        raw_text = self.client.generate(
            system='החזר JSON בלבד: {"topics": ["..."]}. אל תמציא נושאים שלא מופיעים בסילבוס.',
            user=f"חלץ רשימת נושאים/פרקים מהסילבוס הבא:\n---\n{syllabus_text}\n---",
            max_tokens=2048,
        )
        payload = json.loads(_strip_json_fence(raw_text))
        topics = payload.get("topics", [])
        return [str(t).strip() for t in topics if str(t).strip()]

    def _extract_topics_from_pdf(self, pdf_bytes: bytes) -> list[str]:
        raw_text = self.client.generate_with_pdf(
            system='החזר JSON בלבד: {"topics": ["..."]}. אל תמציא נושאים שלא מופיעים בסילבוס.',
            user="חלץ רשימת נושאים/פרקים מקובץ הסילבוס המצורף.",
            pdf_bytes=pdf_bytes,
            max_tokens=2048,
        )
        payload = json.loads(_strip_json_fence(raw_text))
        topics = payload.get("topics", [])
        return [str(t).strip() for t in topics if str(t).strip()]


def classify_exams(
    exam_docs: list[ExtractedDocument],
    syllabus_doc: ExtractedDocument,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> ClassifiedBatch:
    """Convenience entry point for Person A pipeline."""
    return QuestionClassifier(api_key=api_key, model=model).classify_batch(
        exam_docs, syllabus_doc
    )
