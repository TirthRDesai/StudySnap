import logging
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from postgrest.exceptions import APIError

from . import jobs, llm
from .auth import AuthUser, current_user
from .config import settings
from .db import admin
from .schemas import JobOut, JobRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per Supabase call is too noisy
log = logging.getLogger("studysnap")

MAX_QUEUED_PER_USER = 3


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.supabase_service_role_key:
        try:
            jobs.recover()
        except Exception:  # noqa: BLE001 - don't block startup if Supabase is briefly down
            log.exception("Job recovery failed")
    else:
        log.warning("SUPABASE_SERVICE_ROLE_KEY is not set; jobs cannot run.")
    jobs.start()
    yield
    jobs.stop()


app = FastAPI(title="StudySnap API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health():
    ollama = llm.health()
    return {"ok": ollama["reachable"] and not ollama["missing_models"], "ollama": ollama}


@app.post("/books/{book_id}/jobs", response_model=JobOut, status_code=202)
def create_job(book_id: UUID, body: JobRequest, user: AuthUser = Depends(current_user)):
    db = admin()
    book = db.table("books").select("id,user_id,size_bytes").eq("id", str(book_id)).eq("user_id", user.id).limit(1).execute()
    if not book.data:
        raise HTTPException(status_code=404, detail="Book not found.")
    size = book.data[0].get("size_bytes") or 0
    if size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"The file is larger than {settings.max_upload_mb} MB.")

    queued = db.table("jobs").select("id", count="exact").eq("user_id", user.id).eq("status", "queued").execute()
    if (queued.count or 0) >= MAX_QUEUED_PER_USER:
        raise HTTPException(status_code=429, detail="Too many queued jobs. Wait for one to finish.")

    options = body.model_dump(exclude={"kind"})
    try:
        res = db.table("jobs").insert({
            "user_id": user.id,
            "book_id": str(book_id),
            "kind": body.kind,
            "options": options,
            "message": "Waiting in the queue",
        }).execute()
    except APIError as exc:
        if exc.code == "23505":  # unique violation: a job is already active for this book
            raise HTTPException(status_code=409, detail="A job is already running for this book.")
        raise

    job = res.data[0]
    jobs.enqueue(job["id"])
    return JobOut(id=job["id"], kind=job["kind"], status=job["status"],
                  progress=job["progress"], message=job["message"])
