# CheatSheetForge

A web product that takes solved past exams (PDFs) and generates a single printed cheat sheet, automatically identifying question types and consolidating duplicates — a process previously done manually with Claude through repeated conversations and file uploads.

Built during an AI workshop (Moshal scholarship), within a ~36-hour timeframe.

## The Problem

Preparing for an exam in a technical course (e.g., Operating Systems) involves manual processing of dozens of past exams: sorting questions by type, locating duplicates and recurring question variants, and consolidating everything into a single cheat sheet. This is a highly useful process, but time-consuming and completely manual.

## The Solution

1. Upload PDF files of solved exams/exercises + syllabus file.
2. The system extracts questions, classifies them (multiple-choice / open-computational / code) and assigns them under a syllabus topic.
3. An LLM-based deduplication engine identifies duplicates and groups similar open questions into "families".
4. Preview interface with the option to remove items.
5. Export to a printed cheat sheet (Word/PDF), with proper RTL Hebrew support.

## Technologies

- **Backend:** Python + FastAPI
- **Frontend:** React + Vite
- **LLM:** Anthropic API (Claude)
- **PDF Extraction:** pdfplumber
- **Word Generation:** python-docx | **PDF Generation:** Conversion via LibreOffice headless
- **Deployment:** Railway
- **No Database** — session-based, complete deletion at the end, local storage on the user's end.

Full background documents (PRD and work plan) can be found in [`docs/`](docs/PRD.md).

## Project Structure

```text
backend/
├── ingestion/       # Text extraction from PDF
├── classification/  # Question classification using Claude
├── dedup/           # Deduplication engine
├── export/          # docx/PDF generation with RTL support
├── schemas.py       # Shared data contract (Pydantic)
└── main.py          # FastAPI, connects all steps
frontend/            # React — Upload -> Preview -> Export
fixtures/            # Example JSONs for independent module testing
docs/                # PRD, work plan, RTL PoC documentation
```

## Current Status / What Actually Works

- ✅ **RTL PoC manually verified** — Hebrew + English formula/code in the correct direction, both in docx and after PDF conversion. Full details + images: [`docs/rtl_poc_notes.md`](docs/rtl_poc_notes.md).
- ✅ **End-to-end test on fixture data** (no actual API call): Extraction → Merge (offline version, no LLM) → docx+PDF export — works and verified.
- ⚠️ **Actual Claude API calls (classification + semantic merge) were not tested against the real API** in the development environment where the code was written (no API key / network access there). The code is written and ready, but **must be run and verified with a real Anthropic key before presentation** (`backend/classification/classifier.py`, `backend/dedup/merge_engine.py`). An offline `merge_batch_offline` version exists for testing without an API.
- ⚠️ **Frontend was not tested with an actual npm install/build** (no network access in dev environment) — standard React code, but it is highly recommended to run `npm install && npm run dev` early and fix any version-dependent issues.

## Local Run

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173` and forwards `/api` requests to the backend on port 8000 (see `vite.config.js`).

### Tests

```bash
# No API key needed -- tests merge/export logic against fixtures
pytest backend/dedup/tests/test_merge_engine.py
pytest backend/export/tests/test_export.py
```

## Deployment to Railway

1. Connect the repository to Railway.
2. One service for the backend: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` (see `Procfile`), with the `ANTHROPIC_API_KEY` environment variable.
3. Ensure LibreOffice is available in the build environment (`apt-get install libreoffice` is required in Nixpacks/Dockerfile — Railway's default does not include it).
4. Second service (or static hosting) for the frontend, with `VITE_API_BASE_URL` pointing to the backend's URL.

## Suggested Demo Scenario (under 3 minutes)

1. Upload 5 PDF files of Operating Systems exams + syllabus (available in `docs/`, see PRD sources).
2. Set maximum pages to 4.
3. Show the preview — highlight a question merged from two different dates.
4. Remove one irrelevant item.
5. Export to Word, open the file, and demonstrate proper RTL directionality.

## Sources

- Superpowers — https://claude.com/plugins/superpowers
- BMad Method — https://github.com/bmad-code-org/BMAD-METHOD
