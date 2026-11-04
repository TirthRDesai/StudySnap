# StudySnap frontend

Next.js 16 (App Router) + React 19 + Tailwind 4 + Supabase JS.

## Pages
| Route | What it does |
|---|---|
| `/` | Landing page and sign in / sign up |
| `/library` | Upload PDFs (drag and drop), list and delete books |
| `/books/[id]` | Generate flashcards, quiz and explainer; study them |

## How it talks to the rest of the stack
- **Supabase (browser):** auth, uploading the PDF to the private `books` bucket (`<user_id>/<book_id>.pdf`), and reading books, chapters, jobs, flashcards, quizzes and explanations. Row-level security limits every query to the signed-in user.
- **Backend (browser → FastAPI):** only `POST /books/{id}/jobs` (and `GET /health`), with the user's access token as a bearer token.
- No service-role key lives in this app.

## Setup
```bash
npm install
```
Copy `.env.example` to `.env.local` and fill it in (`npx supabase status -o env` in the repo root prints the values), then:
```bash
npm run dev
```
Open http://localhost:3000.

## Scripts
```bash
npm run lint
```
```bash
npm run build
```

## Layout
```
app/            routes (page.tsx, library/, books/[id]/)
components/     AuthForm, Header, GeneratePanel, JobStatus, FlashcardsTab, QuizTab, ExplainerTab
lib/            supabase client, API client, types, session hooks
```
