"""CLI for Person A: PDF exams + syllabus → classified JSON (stage-1 contract).

Usage:
  set GEMINI_API_KEY=...
  python -m backend.classification.run_classify ^
    --syllabus path\\to\\syllabus.pdf ^
    --exams path\\to\\exam1.pdf path\\to\\exam2.pdf ^
    --out out\\classified.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from backend.classification.classifier import classify_exams
from backend.ingestion.pdf_extract import extract_many, extract_pdf

# Load secrets from repo-root .env (never commit that file).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def main() -> None:
    parser = argparse.ArgumentParser(description="CheatSheetForge — Person A classify pipeline")
    parser.add_argument("--syllabus", required=True, help="Syllabus PDF path")
    parser.add_argument("--exams", nargs="+", required=True, help="Exam/homework PDF paths")
    parser.add_argument("--out", default="classified.json", help="Output JSON path")
    parser.add_argument("--model", default=None, help="Override Gemini model id (default: gemini-2.5-flash)")
    args = parser.parse_args()

    syllabus = extract_pdf(args.syllabus)
    if not syllabus.extraction_ok:
        raise SystemExit(f"Syllabus extraction failed: {syllabus.warning}")

    exams = extract_many(args.exams)
    scanned = [d for d in exams if not d.extraction_ok]
    missing = [d for d in exams if not d.path or not Path(d.path).exists()]
    usable = [d for d in exams if d.path and Path(d.path).exists()]
    if not usable:
        raise SystemExit("No exam PDF files found on disk.")
    if missing:
        print("Skipped missing files:")
        for d in missing:
            print(f"  - {d.source_file}: {d.warning}")

    kwargs = {}
    if args.model:
        kwargs["model"] = args.model

    if scanned:
        print(
            f"Note: {len(scanned)} exam(s) have no text layer — "
            "sending PDF pages to Gemini (slower/costlier)."
        )

    batch = classify_exams(usable, syllabus, **kwargs)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(batch.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {len(batch.questions)} questions → {out_path}")
    if scanned:
        print("Scanned / no-text-layer files (handled via Gemini PDF):")
        for d in scanned:
            print(f"  - {d.source_file}: {d.warning}")


if __name__ == "__main__":
    main()
