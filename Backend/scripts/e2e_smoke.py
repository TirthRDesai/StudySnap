"""End-to-end smoke test against a running local stack.

Needs: local Supabase (`npx supabase start`), `ollama serve` with the models pulled, and the
backend running on :8000. Creates throwaway users, so only use it with a LOCAL Supabase.

    python scripts/e2e_smoke.py Tests/fixtures/Book3.pdf
"""
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")  # book text may contain symbols the Windows console can't encode

API = "http://127.0.0.1:8000"
SB = settings.supabase_url
ANON = settings.supabase_anon_key

if "127.0.0.1" not in SB and "localhost" not in SB:
    sys.exit("Refusing to run against a non-local Supabase.")


def sign_up() -> tuple[str, str]:
    email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"
    r = httpx.post(f"{SB}/auth/v1/signup", headers={"apikey": ANON},
                   json={"email": email, "password": "password123"}, timeout=30)
    r.raise_for_status()
    body = r.json()
    return body["user"]["id"], body["access_token"]


def rest(token: str) -> dict[str, str]:
    return {"apikey": ANON, "Authorization": f"Bearer {token}"}


def upload_book(user_id: str, token: str, pdf: Path) -> str:
    book_id = str(uuid.uuid4())
    path = f"{user_id}/{book_id}.pdf"
    data = pdf.read_bytes()
    r = httpx.post(f"{SB}/storage/v1/object/books/{path}",
                   headers={**rest(token), "Content-Type": "application/pdf"}, content=data, timeout=60)
    r.raise_for_status()
    r = httpx.post(f"{SB}/rest/v1/books", headers={**rest(token), "Prefer": "return=minimal"}, json={
        "id": book_id, "user_id": user_id, "title": pdf.stem, "original_filename": pdf.name,
        "storage_path": path, "size_bytes": len(data)}, timeout=30)
    r.raise_for_status()
    return book_id


def wait_for(book_id: str, token: str, job_id: str, timeout_s: int = 3600) -> dict:
    start, last = time.time(), None
    while time.time() - start < timeout_s:
        r = httpx.get(f"{SB}/rest/v1/jobs?id=eq.{job_id}&select=*", headers=rest(token), timeout=30)
        job = r.json()[0]
        line = f"{job['status']:<11} {job['progress']:>3}%  {job['message'] or ''}"
        if line != last:
            print("  ", line)
            last = line
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(3)
    raise SystemExit("timed out")


def count(table: str, book_id: str, token: str) -> list[dict]:
    r = httpx.get(f"{SB}/rest/v1/{table}?book_id=eq.{book_id}&select=*", headers=rest(token), timeout=30)
    return r.json()


def main() -> None:
    pdf = Path(sys.argv[1] if len(sys.argv) > 1 else "Tests/fixtures/Book3.pdf")
    print("health:", httpx.get(f"{API}/health", timeout=30).json())

    uid, token = sign_up()
    uid2, token2 = sign_up()
    book_id = upload_book(uid, token, pdf)
    print("book:", book_id)

    # --- security checks
    body = {"kind": "study", "n_cards": 10, "mode": "exam", "include_quiz": False}
    assert httpx.post(f"{API}/books/{book_id}/jobs", json=body).status_code == 401, "no token must be 401"
    r = httpx.post(f"{API}/books/{book_id}/jobs", json=body, headers=rest(token2))
    assert r.status_code == 404, f"other user must get 404, got {r.status_code}"
    other = httpx.get(f"{SB}/rest/v1/books?id=eq.{book_id}", headers=rest(token2)).json()
    assert other == [], "RLS: other user must not see the book"
    bad = httpx.post(f"{SB}/storage/v1/object/books/{uid}/x.pdf", headers={**rest(token2), "Content-Type": "application/pdf"}, content=b"%PDF-1")
    assert bad.status_code >= 400, "other user must not write into this user's folder"
    r = httpx.post(f"{API}/books/{book_id}/jobs", json={**body, "n_cards": 5}, headers=rest(token))
    assert r.status_code == 422, "n_cards below minimum must be rejected"
    print("security checks passed")

    # --- study job
    t0 = time.time()
    r = httpx.post(f"{API}/books/{book_id}/jobs", headers=rest(token),
                   json={"kind": "study", "n_cards": 15, "mode": "exam", "include_quiz": True, "quiz_questions": 8})
    r.raise_for_status()
    job_id = r.json()["id"]
    dup = httpx.post(f"{API}/books/{book_id}/jobs", headers=rest(token), json={"kind": "explainer", "level": "student"})
    assert dup.status_code == 409, f"second active job must be 409, got {dup.status_code}"
    job = wait_for(book_id, token, job_id)
    print(f"study job {job['status']} in {time.time() - t0:.0f}s", job["error"] or "")
    assert job["status"] == "completed", job["error"]

    cards = count("flashcards", book_id, token)
    selected = [c for c in cards if c["selected"]]
    quiz = count("quiz_questions", book_id, token)
    print(f"flashcards: {len(cards)} generated, {len(selected)} selected; quiz: {len(quiz)} questions")
    for c in sorted(selected, key=lambda c: c["rank"])[:5]:
        print(f"   #{c['rank']} [{c['card_type']}, imp {c['importance']}] {c['front']}  ->  {c['back'][:90]}")
    for q in quiz[:2]:
        print("   Q:", q["question"], q["options"], "answer:", q["correct_index"])
    assert len(selected) == min(15, len(cards))
    assert all(len(q["options"]) == 4 for q in quiz)

    # --- explainer job
    t0 = time.time()
    r = httpx.post(f"{API}/books/{book_id}/jobs", headers=rest(token), json={"kind": "explainer", "level": "student"})
    r.raise_for_status()
    job = wait_for(book_id, token, r.json()["id"])
    print(f"explainer job {job['status']} in {time.time() - t0:.0f}s", job["error"] or "")
    assert job["status"] == "completed", job["error"]
    ex = count("explanations", book_id, token)
    print(f"explanations: {len(ex)} rows")
    overview = next(e for e in ex if e["chapter_id"] is None)
    print("--- overview ---\n" + overview["content_md"][:700])
    print("OK")


if __name__ == "__main__":
    main()
