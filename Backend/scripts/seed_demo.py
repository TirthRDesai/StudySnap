"""Create (or sign in) a local demo user, upload a book and generate everything for it.

LOCAL Supabase only. Needs the backend on :8000 and `ollama serve` running.

    python scripts/seed_demo.py Tests/fixtures/Book3.pdf
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_smoke import API, ANON, SB, rest, upload_book, wait_for  # noqa: E402

EMAIL, PASSWORD = "demo@example.com", "demo-password-123"


def main() -> None:
    pdf = Path(sys.argv[1] if len(sys.argv) > 1 else "Tests/fixtures/Book3.pdf")
    r = httpx.post(f"{SB}/auth/v1/signup", headers={"apikey": ANON}, json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    if r.status_code >= 400:  # already registered
        r = httpx.post(f"{SB}/auth/v1/token?grant_type=password", headers={"apikey": ANON},
                       json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    r.raise_for_status()
    body = r.json()
    uid, token = body["user"]["id"], body["access_token"]

    book_id = upload_book(uid, token, pdf)
    print("book:", book_id)
    for payload in (
        {"kind": "study", "n_cards": 15, "mode": "exam", "include_quiz": True, "quiz_questions": 8},
        {"kind": "explainer", "level": "student"},
    ):
        job = httpx.post(f"{API}/books/{book_id}/jobs", headers=rest(token), json=payload, timeout=30)
        job.raise_for_status()
        done = wait_for(book_id, token, job.json()["id"])
        print(payload["kind"], done["status"], done["error"] or "")
    print(f"Sign in with {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
