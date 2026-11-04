# StudySnap — Product Requirements Document

Status: Draft v0.2 · Owner: Tirth Desai

> **Implementation status:** the app was rebuilt from scratch against a local Supabase. Built: auth, private upload, background jobs with progress, structure-aware flashcards with top-N ranking and study modes (F10, F11), multiple-choice quiz, hierarchical explainer (F12), RLS and token-verified API (most of section 9a). Not yet: OCR/EPUB, "focus" generation (F9), resumable jobs, export beyond CSV, hosted deployment.

## 1. Summary
StudySnap is a web app where a user uploads a book (PDF) and receives AI-generated **flashcards** and **quizzes** covering that book. All AI runs locally through **Ollama** (`ollama serve`), so there are no per-token costs and the book never leaves the user's infrastructure.

## 2. Problem
Students and self-learners read long books but have no cheap way to turn them into active-recall material. Making flashcards by hand takes hours. Existing tools are paid, cap input size, or send content to third-party APIs.

## 3. Goals / Non-goals
**Goals**
- Upload a book and get flashcards + a quiz that cover the *whole* book, not only the first chapters.
- Free to run: local models via Ollama, Supabase free tier for auth/storage/DB.
- Output grounded in the book text (no invented facts), with chapter/page references.
- Long jobs run in the background; the user sees progress.

**Non-goals (v1)**
- Scanned/image-only PDFs (OCR), DRM-protected books, EPUB/MOBI (planned v1.1).
- Spaced-repetition scheduling, social features, mobile app.
- Hosting GPU inference for the public (v1 assumes a self-hosted/local Ollama).

## 4. Users
- **Student** — uploads a textbook, wants per-chapter flashcards and exam-style quizzes.
- **Self-learner** — uploads non-fiction, wants key concepts and a comprehension check.

## 5. User stories
1. As a user I can sign up / sign in.
2. I can upload a PDF and see it in my library.
3. I can start generation, choosing flashcards, quiz, or both, and optionally limits (cards per chapter, question count).
4. I can watch progress (queued → extracting → generating → done/failed).
5. I can browse flashcards by chapter, flip them, and mark known/unknown.
6. I can take the quiz, get scored, and see the correct answer plus the source passage.
7. I can export flashcards/quiz (JSON/CSV; Anki later) and delete a book with all derived data.

## 6. Functional requirements
| ID | Requirement |
|---|---|
| F1 | Accept PDF uploads up to 50 MB (configurable); reject non-PDF and password-protected files with a clear error. |
| F2 | Extract text, detect chapters from the PDF outline/bookmarks, falling back to heading heuristics, then fixed-size sections. |
| F3 | Generate flashcards per section; target density configurable (default ~8 cards per 2–3k words). |
| F4 | Generate multiple-choice quizzes with answer, explanation, and source reference (chapter/page). |
| F5 | Validate every generated item against a JSON schema; retry once on failure; drop items that still fail. |
| F6 | Deduplicate near-identical cards/questions across the book (embedding similarity). |
| F7 | Jobs are asynchronous and idempotent, with status in the `jobs` table and visible in the UI. |
| F8 | Results persisted in Supabase (tables + storage); each user sees only their own data (RLS). |
| F9 | Optional "focus" prompt (e.g. "chapter 4 only", "photosynthesis") restricts generation using retrieval. |
| F10 | After per-chapter generation, rank all flashcards by importance and output only the top *n* (user-configurable, default e.g. 100). *n* is the **total** number of cards across the book. Every chapter keeps a minimum share so none is dropped. The full pool is stored, so the user can raise *n* later without regenerating. |
| F11 | Study mode selector. **Exam prep** favours definitions, formulas, cause/effect, comparisons and other testable facts, and weights the ranking toward them. **Overview** favours big-picture concepts and chapter themes. Mode changes the generation prompt and the F10 scoring weights. |
| F12 | **Book explainer:** produce a plain-language explanation of the whole book, organised book → chapter → section, with analogies, worked examples and a glossary. See section 8a. |

## 7. Non-functional requirements
- **Cost:** no paid APIs required.
- **Privacy:** book text is processed only by the user's Ollama and their Supabase project.
- **Performance target:** a 300-page book finishes in under ~45 min on an 8 GB-VRAM GPU (to be measured; CPU-only is slower).
- **Reliability:** a failed section does not fail the whole job; partial results are saved and the job can resume.
- **Security:** service-role key is server-only; backend CORS restricted to the frontend origin (currently `*`); authenticated requests only.

## 8. AI architecture (recommendation)

### Question: RAG, or give the whole book to the model?
**Neither on its own. Use structure-aware map-reduce generation, with embeddings used as a supporting tool.**

- **Whole book in the prompt is not viable.** A 300-page book is ~100k+ words (~150k tokens). Local 7–8B models have small usable context (Ollama defaults to 4k unless `num_ctx` is raised; quality degrades well before the advertised maximum), and memory use grows quickly with context.
- **Pure RAG is the wrong tool for this job.** RAG answers a *query* with the top-k most similar chunks. Flashcards need *coverage*, not relevance, so query-based retrieval is biased toward a few topics and misses the rest. (The current backend works this way: `generate_flashcards_from_query` retrieves k=5 chunks per query.)

**Recommended pipeline**
1. **Extract + structure:** read the PDF, split into chapters (outline → headings → fixed windows). Clean headers/footers/page numbers.
2. **Section chunking:** split each chapter into ~1.5–2.5k-word sections on paragraph boundaries, keeping chapter title and page range as metadata.
3. **Map (generate):** for every section, call the model with that section's text *directly* (no retrieval) and request flashcards/questions as JSON, enforced with Ollama's structured outputs (`format` = JSON schema). This guarantees coverage of the whole book and runs sections independently, so they can be retried or parallelised.
4. **Reduce (clean):** schema-validate, drop invalid items, deduplicate with embeddings (cosine similarity threshold), and balance counts per chapter.
4b. **Rank and select top *n* (F10):** over-generate (about 2–3× the target per chapter), then score every card and keep the best *n*:
    - **Importance score at generation time:** each card is returned with a 1–5 `importance` rating and a one-line `why`, judged against its section (the model sees the source text).
    - **Cross-chapter normalisation:** LLM ratings are only calibrated within a section (a chapter's "5" may be another's "3"), so convert them to within-chapter percentiles before comparing chapters.
    - **Centrality signal:** cosine similarity of the card's embedding to its chapter centroid, plus overlap with the chapter title/headings and repeated key terms. This is cheap and objective, so it dampens noisy LLM scores.
    - **Combined score:** `0.5 × LLM percentile + 0.3 × centrality + 0.2 × key-term overlap` (starting weights, to be tuned on a sample book). In **exam prep** mode, add a bonus for card types that are typically tested (definition, formula, comparison, cause/effect) and weight the LLM rating higher; in **overview** mode, weight centrality higher.
    - **Selection:** greedy MMR (maximal marginal relevance) over the combined score so near-duplicates and tightly clustered cards don't crowd out other topics. Per-chapter quota is proportional to chapter length, with a floor of 1–2 cards.
    - **Optional second pass:** a single LLM call per chapter on only the shortlisted cards ("which of these 20 matter most for understanding the chapter?") as a tie-breaker. Add only if the scoring above proves too noisy.
    - Each stored card keeps its `rank`, `score`, and `selected` flag.
5. **Embeddings/RAG where it helps:** store section embeddings for (a) dedupe, (b) the optional "focus on topic X" generation (F9), (c) quiz distractor selection from similar passages, and (d) a future "ask the book" chat. The existing LanceDB + `mxbai-embed-large` setup is reusable for this.
6. **Quality pass (optional):** a cheap verifier call asks "is this answer supported by the passage?" and drops items that fail. Treat as a later optimisation.

For quiz distractors, ask the model for plausible wrong answers from the same section, then optionally swap in answers from the nearest-neighbour cards.

### 8a. Book explainer (F12)
Same hierarchy as the flashcards, so it reuses the extraction and chaptering work and shares the section chunks:
1. **Section explanations (map):** for each section, ask the model to explain it for a beginner: short paragraphs, plain words, one analogy or example where it helps, and key terms defined inline. Output is structured (heading, explanation, key terms, "why it matters").
2. **Chapter explainer (reduce):** feed that chapter's section explanations (not the raw text) into one call to produce a chapter overview: main idea, how the sections connect, and a short "if you remember one thing" summary. Working from the section explanations keeps it within a local model's context.
3. **Book overview (reduce again):** combine the chapter overviews into a book-level summary and a whole-book glossary. For very long books, do this in batches of chapters first.
4. **Adjustable level:** the user picks a depth (ELI5 / student / detailed). This changes the prompt only, and results are cached per level.
5. **Grounding:** each explanation keeps its chapter and page reference. Explanations are written from the source text, with a prompt rule to say "the book doesn't cover this" instead of filling gaps from the model's own knowledge. Small local models can still drift, so spot-check before trusting it.
6. **Links to the rest of the app:** flashcards and quiz questions link back to the explainer section they came from, and the explainer can link to the cards for that section. A later "ask the book" chat uses the same embeddings.

Cost note: the explainer touches the whole book once per depth level, so it roughly doubles generation time. Run it as a separate job so flashcards can finish first.

### Model recommendations (all free via Ollama)
Model names and sizes are from my general knowledge; verify with `ollama list` / the Ollama library and benchmark 2–3 on one real chapter before committing.

| Role | Primary pick | Alternatives | Notes |
|---|---|---|---|
| Generation | `qwen2.5:7b-instruct` | `llama3.1:8b`, `gemma3:12b` (if you have the VRAM) | Qwen 2.5 is generally strong at following JSON/instructions at 7B. Llama 3.1 8B is a safe, well-supported default. |
| Low-resource machine | `llama3.2:3b`, `phi4-mini`, `gemma3:4b` | | Expect noticeably lower question quality. |
| Embeddings | `nomic-embed-text` (small, fast) | `mxbai-embed-large` (already used) | Keep one embedding model across the whole pipeline. |

The current code uses `llama3:8b`; switching to `llama3.1:8b` or `qwen2.5:7b-instruct` is a one-line change and the first thing to A/B test. Set `num_ctx` explicitly (e.g. 8192) and `temperature` low (~0.2–0.4) for factual output.

### Using `ollama serve`
- Run `ollama serve` once; the backend talks to it over HTTP (`http://localhost:11434` by default, configurable with `OLLAMA_HOST`).
- The backend should depend on the **Ollama host URL**, not on a binary path. Today `main.py` requires `OLLAMA_BIN` and `OLLAMA_MODELS_DIR` and crashes if they are missing; this should become optional config plus a startup health check that confirms the server is reachable and the models are pulled.

## 9. System architecture
```
Browser (Next.js) ──upload PDF──▶ Supabase Storage (documents bucket)
      │                                   ▲
      │ POST /process/{file_id}           │ download PDF / upload results
      ▼                                   │
FastAPI backend ──▶ pipeline ──▶ ollama serve (generation + embeddings)
      │                 └──▶ LanceDB (section embeddings, local)
      ▼
Supabase Postgres (documents, document_files, jobs, flashcards, quiz_*)
      ▲
      └── frontend polls / subscribes (Realtime) for job status and results
```

## 9a. Security and request flow

### Gaps in the previous prototype (the rebuild addresses S1–S7 by design)
The code referenced below was replaced. The rebuild verifies tokens with Supabase Auth, derives the user id server-side, checks ownership before any job, uses RLS plus per-user storage policies, restricts CORS, validates uploads (size, PDF magic bytes), names files by ID, only marks jobs `completed` at the end, and runs one job at a time from a persisted queue. Remaining: a shared-secret or private-network hop if the backend is ever hosted, and rate limits beyond the per-user queue cap.
| # | Gap | Where | Impact |
|---|---|---|---|
| S1 | `userId` and `path` are taken from the request body and used with the service-role key; nothing checks the caller. | `Frontend/app/api/table-update/route.ts` | Anyone can create documents for any user. |
| S2 | `email` and `userId` come from the query string; `storage_key` is trusted and downloaded with the service-role key; outputs are uploaded under a caller-supplied email folder. | `Backend/api.py` | A caller can get another user's book processed and receive the results. |
| S3 | The browser calls FastAPI directly. CORS is `*`, with no auth, rate limit, or file size/type checks. | `Frontend/app/page.tsx`, `Backend/api.py` | Unlimited GPU jobs if the backend is reachable. |
| S4 | Job is marked `completed` before outputs are saved and uploaded. | `Backend/api.py` | UI shows "done" while results are missing or the upload failed. |
| S5 | Original filename is used for the temp file and for the LanceDB table name. | `Backend/api.py` | Path escape with odd filenames; table collisions between users. |
| S6 | Jobs run in the web process (`BackgroundTasks`). | `Backend/api.py` | Jobs are lost on restart; concurrent jobs fight over one GPU. |
| S7 | Email is used in storage paths. | `Backend/supabase_utils/storage.py` | Personal data in object names. |

### Target request flow
1. **Upload:** the browser uploads the PDF straight to Supabase Storage at `{user_id}/{document_id}.pdf`. Storage policies allow a user to write and read only their own folder.
2. **Register:** the browser calls a Next.js API route with its Supabase session. The route verifies the JWT, derives `user_id` itself (never from the body), confirms the object exists in that user's folder, and creates the `documents` and `document_files` rows.
3. **Start job:** Next.js calls FastAPI with a shared-secret header over a private network (or FastAPI validates the Supabase JWT itself). The request carries only the `file_id`.
4. **Authorise:** FastAPI verifies ownership (file → document → `user_id`) before downloading. Outputs are uploaded to `{user_id}/{document_id}/...`; email is never used in paths. Temp files and LanceDB tables are named by document ID.
5. **Process:** jobs go through a single-worker queue with per-user limits. A job is set to `completed` only after all uploads succeed.
6. **Read results:** the frontend reads `flashcards`, `quiz_*`, `jobs` and explainer rows with the user's own session under row-level security, and uses signed URLs for any stored files. The service-role key never reaches the browser.

### Rules
- Service-role key is used only in server code and is never exposed with a `NEXT_PUBLIC_` prefix.
- Row-level security is enabled on every table; each policy ties rows to `auth.uid()`.
- `ollama serve` binds to `127.0.0.1` (it has no authentication). Never expose port 11434.
- CORS is restricted to the frontend origin. Uploads are limited by size, and the file must be a real PDF (check magic bytes, not just the extension).
- Treat book text as untrusted input: model output is validated against a JSON schema and never executed or used to build file paths or queries.
- Deleting a book deletes its storage objects, rows, embeddings and generated outputs.

## 10. Data model
Existing in `Backend/supabase-schema.sql`: `documents`, `document_files`, `flashcards`, `quiz_sessions`, `quiz_questions`, `quiz_attempts`, `user_quiz_answers`, `summaries`, `generation_logs`, `users`, plus a `jobs` table used by `supabase_utils/jobs.py`. Proposed additions: `sections` (document_id, chapter, page range, text hash) and `source_ref` columns on flashcards/questions.

## 11. API (v1)
- `POST /process/{file_id}?include_quiz=true|false` — start a job (exists).
- `GET /jobs/{job_id}` — status and progress (to add).
- `GET /health` — service + Ollama + model availability (extend).

## 12. Milestones
1. **M0 — Cleanup:** fix README/env drift, make Ollama config host-based, tighten CORS, add startup health check, close the security gaps S1–S7 (section 9a).
2. **M1 — Quality core:** chapter detection, section-level map generation with JSON-schema output, dedupe, top-*n* importance ranking (F10). Compare 2–3 models on a sample book.
3. **M2 — Product:** study-mode selector (F11), book explainer (F12), progress UI, flashcard viewer, quiz taking and scoring, export.
4. **M3 — Hardening:** RLS audit, resumable jobs, rate limits, tests.
5. **M4 — Extras:** "focus" generation, ask-the-book chat, EPUB, OCR, Anki export.

## 13. Success metrics
- ≥ 90% of generated items pass schema validation without manual fixes.
- Spot-check of 50 random cards/questions per book: ≥ 85% judged correct and supported by the source.
- Coverage: every chapter has ≥ 1 card per ~300 words (±), no chapter empty.
- Time to first flashcard visible < 2 min after starting a job.

## 14. Risks and open questions
- **Local model quality** on factual accuracy: mitigate with low temperature, grounding in the passage, and the verifier pass.
- **Throughput** on CPU-only machines: ship with a "fast mode" (smaller model, fewer items).
- **Messy PDFs** (two-column layouts, footnotes, scanned pages) hurt extraction; v1 documents the limitation.
- **Copyright:** users upload books they own; processing is private to their account. Needs a terms/notice before any public launch.
- Open: single-user/self-hosted only, or multi-tenant hosted? This decides queueing and GPU needs.
- "Importance" is subjective and a small local model rates it unreliably. Mitigation: blend with embedding-based signals (4b) and check the ranking against a hand-labelled sample chapter.
- Decided: *n* is the total number of cards; exam prep is a selectable mode (F11).
- Open: for the explainer, which depth levels to ship first, and should the output be viewed in-app only or also exportable (PDF/Markdown)?
- Open: is the quiz MCQ-only, or also short-answer/true-false?
