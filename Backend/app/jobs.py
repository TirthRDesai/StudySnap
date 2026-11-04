"""Single-worker job queue.

One worker keeps the GPU from being shared by several jobs at once. Jobs are persisted in the
`jobs` table; on startup, queued jobs are re-queued and jobs that were mid-run are marked failed.
"""
import logging
import queue
import threading
from datetime import datetime, timezone

from .db import admin
from .pipeline.runner import friendly_error, run_job

log = logging.getLogger("studysnap.jobs")

_queue: "queue.Queue[str]" = queue.Queue()
_worker: threading.Thread | None = None
_stop = threading.Event()


def enqueue(job_id: str) -> None:
    _queue.put(job_id)


def _finish_book_status(book_id: str) -> None:
    has_cards = admin().table("flashcards").select("id", count="exact").eq("book_id", book_id).limit(1).execute()
    status = "ready" if (has_cards.count or 0) > 0 else "uploaded"
    admin().table("books").update({"status": status}).eq("id", book_id).execute()


def _process(job_id: str) -> None:
    res = admin().table("jobs").select("*").eq("id", job_id).limit(1).execute()
    if not res.data or res.data[0]["status"] != "queued":
        return
    job = res.data[0]
    try:
        run_job(job)
    except Exception as exc:  # noqa: BLE001 - every failure must end up on the job row
        log.exception("Job %s failed", job_id)
        admin().table("jobs").update({
            "status": "failed",
            "error": friendly_error(exc),
            "message": None,
        }).eq("id", job_id).execute()
    finally:
        done = admin().table("jobs").select("status").eq("id", job_id).limit(1).execute()
        if done.data and done.data[0]["status"] in ("completed", "failed"):
            admin().table("jobs").update(
                {"finished_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", job_id).execute()
        try:
            _finish_book_status(job["book_id"])
        except Exception:  # noqa: BLE001
            log.exception("Could not update book status for %s", job["book_id"])


def _loop() -> None:
    while not _stop.is_set():
        try:
            job_id = _queue.get(timeout=1)
        except queue.Empty:
            continue
        try:
            _process(job_id)
        except Exception:  # noqa: BLE001
            log.exception("Worker error on job %s", job_id)


def recover() -> None:
    """Fail jobs interrupted by a restart; re-queue those that never started."""
    db = admin()
    stale = db.table("jobs").select("id,book_id").not_.in_("status", ["queued", "completed", "failed"]).execute()
    for row in stale.data:
        db.table("jobs").update({
            "status": "failed",
            "error": "The server restarted while this job was running. Please retry.",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", row["id"]).execute()
        _finish_book_status(row["book_id"])
    queued = db.table("jobs").select("id").eq("status", "queued").order("created_at").execute()
    for row in queued.data:
        enqueue(row["id"])


def start() -> None:
    global _worker
    _stop.clear()
    _worker = threading.Thread(target=_loop, name="job-worker", daemon=True)
    _worker.start()


def stop() -> None:
    _stop.set()
    if _worker:
        _worker.join(timeout=5)
