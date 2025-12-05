# StudySnapAI (PDF → Flashcards/Quiz)

Backend and pipeline to turn PDFs into flashcards and quizzes using LanceDB + Ollama, with a FastAPI service that pulls PDFs from Supabase Storage and pushes generated outputs back to Supabase.

## Project layout
- `api.py` — FastAPI app exposing `/process/{file_id}` and `/health`
- `main.py` — PDFToFlashcardPipeline orchestration (processing, generation, saving)
- `pipeline/` — PDF processing, embedding, flashcard and quiz generation
- `supabase_utils/` — Supabase client helpers (`client.py`), storage helpers (`storage.py`), job utilities (`jobs.py`)
- `supabase-schema.sql` — tables and buckets (including `document_files`, no chunk uploads)
- `output/` — local outputs when running the pipeline directly

## Requirements
- Python 3.8+
- Ollama installed (models stored at `D:\OllamaModels` by default)
- Models: `llama3:8b` (generation) and `mxbai-embed-large:latest` (embeddings)
- Install deps: `pip install -r requirements.txt`

## Environment variables
Set these (or put them in `.env`, automatically loaded by `supabase_utils.client`):
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (preferred) or `SUPABASE_ANON_KEY` (if it has table+storage rights)
- `OLLAMA_HOME` and `OLLAMA_MODELS` (defaulted to `D:\OllamaModels` in `main.py`)
- Optional: `OLLAMA_BIN` if Ollama is in a non-standard path

## Supabase setup
Run `supabase-schema.sql`. Key pieces:
- Tables: `documents`, `document_files`, `flashcards`, `quiz_sessions`, `quiz_questions`, `quiz_attempts`, `user_quiz_answers`, `summaries`, `generation_logs`, `users`, `jobs` (if you add it), etc.
- Storage buckets created: `documents`, `flashcards`, `quizzes`, `answer-keys`, `student-quizzes`, `summaries`, `attempt-results`.
- `document_files.storage_key` is the path inside the `documents` bucket (not the full URL). Recommended: `{document_id}/{original_filename}`.

### Creating a `document_files` record
1) Upload the PDF to the `documents` bucket using your chosen key (e.g., `1234.../test.pdf`).  
2) Insert into `document_files` pointing at that key:
```sql
insert into document_files (document_id, storage_key, original_name, content_type)
values ('<document_id>', '<document_id>/test.pdf', 'test.pdf', 'application/pdf');
```
Use the returned `id` as `file_id` for the API.

## Running the FastAPI backend
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```
Endpoints:
- `GET /health` — basic health check.
- `POST /process/{file_id}?include_quiz=true|false` — kicks off processing in a background task.

Processing flow:
1) Look up `document_files` by `file_id`, read `storage_key`, download from `documents` bucket.  
2) Run `PDFToFlashcardPipeline` (process PDF, generate flashcards, optionally quiz).  
3) Save outputs locally, then upload to buckets with keys `{document_id}/flashcards_*.json`, `quiz_*.json`, `answer_key_*.txt`, `quiz_student_*.txt`, `summary_*.txt`.  
4) Watch Supabase Storage (Realtime) to see uploads land; optional `jobs.py` helpers can write status rows if you wire them in.

## Running the pipeline locally (no Supabase)
```bash
python main.py              # runs PDFToFlashcardPipeline with quiz
# or
python main.py --no-quiz    # if you add your own flag handling
```
Defaults: `Tests/test.pdf`, chunk size 400/overlap 80, LanceDB at `./chunks-storage`, Ollama models above. Outputs written to `output/` (flashcards, quiz, answer key, student quiz view, summary).

## Storage key format (important)
- Bucket: `documents`
- Key: path inside the bucket only (no URL, no bucket name prefix). Recommended: `{document_id}/{original_filename}`.
- Example: if the object is at `documents/47a4.../myfile.pdf`, then `storage_key` should be `47a4.../myfile.pdf`.

## Troubleshooting
- Missing Supabase creds: ensure `.env` or environment has `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`/`ANON_KEY`.
- Method not allowed: `/process/{file_id}` is POST-only.
- Upload errors to Storage: `storage_key` must be a string path; upserts are sent with `{"upsert": "true"}`.
- Ollama errors: confirm models exist under `OLLAMA_MODELS` and `ollama` is on PATH or `OLLAMA_BIN` is set.
