"""Shared data contract for CheatSheetForge (see docs/12-team-split-and-data-contract.md).

Person A produces ClassifiedQuestion.
Person B consumes that and produces MergedBank.
Person C consumes MergedBank for export/frontend.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class QuestionType(str, Enum):
    CLOSED = "closed"
    OPEN_CALC = "open_calc"
    CODE = "code"


# --- Stage 1 → 2: classification output (A produces, B consumes) ---


class ClassifiedQuestion(BaseModel):
    id: str = Field(..., description="Stable id, e.g. q_0001")
    source_file: str
    source_label: str
    type: QuestionType
    topic: str = Field(..., description="Must come from the uploaded syllabus")
    question_text: str
    answer_text: str = ""
    has_answer: bool = True

    @model_validator(mode="after")
    def answer_consistency(self) -> ClassifiedQuestion:
        if self.has_answer and not (self.answer_text or "").strip():
            # Prefer explicit missing-answer flag over inventing content.
            self.has_answer = False
        return self


class ClassifiedBatch(BaseModel):
    """Wrapper for a full classification run (exams + syllabus topics used)."""

    course: str = ""
    syllabus_topics: list[str] = Field(default_factory=list)
    questions: list[ClassifiedQuestion] = Field(default_factory=list)


# Alias kept for the dedup module, which imports the batch under this name.
ClassificationBatch = ClassifiedBatch


# --- Stage 2 → 3: merge output (B produces, C consumes) ---


class OpenCalcVariant(BaseModel):
    question_text: str
    answer_text: str
    source_label: str


class OpenCalcRepresentative(BaseModel):
    question_text: str
    answer_text: str
    source_label: str


class ClosedItem(BaseModel):
    type: Literal["closed"] = "closed"
    topic: str
    question_text: str
    correct_answer: str
    distractors: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class OpenCalcItem(BaseModel):
    type: Literal["open_calc"] = "open_calc"
    topic: str
    representative: OpenCalcRepresentative
    variants: list[OpenCalcVariant] = Field(default_factory=list)


class CodeItem(BaseModel):
    type: Literal["code"] = "code"
    topic: str
    reference_only: bool = True
    code_snippet: str | None = None
    sources: list[str] = Field(default_factory=list)


MergedItem = ClosedItem | OpenCalcItem | CodeItem


class MergedBank(BaseModel):
    course: str
    max_pages: int = Field(..., ge=1)
    items: list[MergedItem] = Field(default_factory=list)


# --- API-level models (main.py / export) ---


class UploadLimits(BaseModel):
    """Per-request upload cap (docs/06, decision 15 — calibrate against the model)."""

    max_files: int = 15
    max_total_mb: int = 5


class ExportFormat(str, Enum):
    DOCX = "docx"
    PDF = "pdf"
