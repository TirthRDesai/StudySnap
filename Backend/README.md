# StudySnap backend

FastAPI service that turns an uploaded PDF into flashcards, a quiz and an explainer using a local Ollama server, and writes the results to Supabase.

## Layout
```
app/
├── main.py            FastAPI app, CORS, /health, POST /books/{id}/jobs
├── auth.py            Verifies the bearer token with Supabase Auth
├── db.py              Service-role Supabase client (bypasses RLS)
├── llm.py             Ollama wrapper: JSON-schema output, embeddings, health
├── jobs.py            Single-worker queue, restart recovery
├── schemas.py         Request/response models
└── pipeline/
    ├── extract.py     PDF text, header/footer cleanup, chapter detection
    ├── chunking.py    Chapters → ~1.8k-word sections on paragraph boundaries
    ├── flashcards.py  Per-section card generation
    ├── ranking.py     Importance scoring, MMR selection, per-chapter quotas
    ├── quiz.py        Multiple-choice generation + validation + shuffling
    ├── explainer.py   Section → chapter → book explanations
    ├── textclean.py   Strips "according to the passage" style references
    └── runner.py      Orchestrates a job end to end
Tests/                 pytest unit tests (+ fixtures/*.pdf sample books)
scripts/               e2e_smoke.py, seed_demo.py (local dev tools)
```

## Setup
```bash
python -m venv .venv
```
```bash
.venv\Scripts\pip install -r requirements.txt
```
Copy `.env.example` to `.env` and fill it in (see the comments there). Start local Supabase and Ollama first (see the root README), then:
```bash
.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload
```

## API
All job routes need `Authorization: Bearer <Supabase access token>`.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Whether Ollama is reachable and the configured models are pulled |
| POST | `/books/{book_id}/jobs` | Queue a job for a book you own. Returns `202` with the job |

Body for `kind: "study"`: `n_cards` (10–300, total kept for the whole book), `mode` (`exam` or `overview`), `include_quiz`, `quiz_questions` (5–100).
Body for `kind: "explainer"`: `level` (`eli5`, `student` or `detailed`).

Errors: `401` bad/missing token, `404` not your book, `409` a job is already active for it, `422` invalid options, `429` too many queued jobs. Progress and results are read from Supabase (the `jobs`, `flashcards`, `quiz_questions`, `explanations` tables) under row-level security.

## How generation works
1. **Extract:** download the PDF, clean text, detect chapters (bookmarks → "Chapter N" headings → 15-page parts).
2. **Flashcards:** every section is sent to the model directly (so the whole book is covered) with a JSON schema. About 2.5× the requested cards are generated, each with a 1–5 importance rating.
3. **Rank:** ratings become within-chapter percentiles, blended with embedding centrality, key-term overlap and (exam mode) a card-type bonus. MMR picks the top N with a per-chapter quota proportional to length, dropping near-duplicates.
4. **Quiz:** per-section questions, validated (4 distinct options, no "all of the above"), options shuffled, deduplicated by embedding.
5. **Explainer:** section explanations → chapter overview built from them → book overview; glossary collected from key terms.

Re-running a job replaces the previous flashcards/quiz (or the explainer at that depth).

## Tests
```bash
.venv\Scripts\python -m pytest
```
The end-to-end check needs the whole stack running (Supabase, Ollama, this API). It creates throwaway users, so it refuses to run against a non-local Supabase:
```bash
.venv\Scripts\python scripts/e2e_smoke.py Tests/fixtures/Book3.pdf
```
`scripts/seed_demo.py` creates `demo@example.com` with a generated book so you can look around the UI.

## Configuration
See `.env.example`. The model names are configurable (`GENERATION_MODEL`, `EMBEDDING_MODEL`). Larger `NUM_CTX` uses more VRAM; 8192 fits a 7–8B model on an 8 GB GPU.
