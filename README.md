# CheatSheetForge

A product that takes solved past exams (PDF) and generates a filtered, categorized, deduplicated formula/cheat sheet, ready to print.

Built as part of an AI workshop, Moshel scholarship program.

## Documentation

All planning docs live in [`docs/`](./docs) (currently in Hebrew):

- [`docs/00-index.md`](./docs/00-index.md) — entry point to the full PRD
- [`docs/work-plan.md`](./docs/work-plan.md) — timeline leading up to the demo

## Running locally

Backend (FastAPI, from the repo root):

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

Frontend (React + Vite, dev server proxies `/api` to port 8000):

```bash
cd frontend && npm install && npm run dev
```

Environment: `GEMINI_API_KEY` for extraction/classification, `ANTHROPIC_API_KEY`
for the dedup engine (without it `/api/merge` falls back to offline grouping and
says so via `dedup_mode`). PDF export needs LibreOffice (`soffice`) on PATH —
Railway installs it through `nixpacks.toml`; Word export needs nothing extra.

## Status

MVP flow implemented end to end: upload → classify → merge → preview/remove →
export to Word/PDF. See [`docs/rtl_poc_notes.md`](./docs/rtl_poc_notes.md) for the
Hebrew RTL findings.
