"""Person A — PDF ingestion package."""

from .pdf_extract import (
    ExtractedDocument,
    extract_many,
    extract_pdf,
    label_from_filename,
    parse_syllabus_topics,
)

__all__ = [
    "ExtractedDocument",
    "extract_many",
    "extract_pdf",
    "label_from_filename",
    "parse_syllabus_topics",
]
