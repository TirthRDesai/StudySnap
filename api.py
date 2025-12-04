import shutil
import tempfile
import uuid
from pathlib import Path
from typing import List

from fastapi import BackgroundTasks, FastAPI, HTTPException

from main import PDFToFlashcardPipeline
from supabase_utils import (
    download_document_file,
    fetch_document_file,
    get_supabase_client,
    upload_generated_outputs,
)

app = FastAPI(title="StudySnapAI")


def _process_file_job(file_id: str, include_quiz: bool = True):
    """Background job to download a PDF from Supabase, run the pipeline, and upload outputs."""
    client = get_supabase_client()
    record = fetch_document_file(client, file_id)

    document_id = record["document_id"]
    storage_key = record["storage_key"]
    original_name = record.get("original_name") or f"{file_id}.pdf"

    temp_dir = Path(tempfile.mkdtemp(prefix="studysnap_"))
    local_pdf = temp_dir / original_name

    try:
        download_document_file(client, storage_key, local_pdf)

        pipeline = PDFToFlashcardPipeline(pdf_path=str(local_pdf))

        # Run the pipeline steps
        if not pipeline.process_pdf():
            raise RuntimeError("Failed during PDF processing")

        flashcards = pipeline.generate_flashcards()
        if not flashcards:
            raise RuntimeError("No flashcards generated")

        quiz_questions: List = []
        if include_quiz:
            quiz_questions = pipeline.generate_quiz()

        output_files = pipeline.save_outputs(
            flashcards, quiz_questions if quiz_questions else None
        )
        if not output_files:
            raise RuntimeError("No outputs were saved")

        upload_generated_outputs(client, str(document_id), output_files)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/process/{file_id}")
async def process_file(file_id: str, include_quiz: bool = True, background_tasks: BackgroundTasks = None):
    """
    Kick off processing for a file uploaded to Supabase Storage.

    The request returns immediately while the heavy work runs in a background task.
    Supabase Realtime can be used to watch the target buckets for uploaded outputs.
    """
    if not file_id:
        raise HTTPException(status_code=400, detail="file_id is required")

    job_id = str(uuid.uuid4())
    background_tasks.add_task(_process_file_job, file_id, include_quiz)

    return {
        "job_id": job_id,
        "status": "started",
        "message": "Processing started. Watch Supabase buckets for outputs.",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
