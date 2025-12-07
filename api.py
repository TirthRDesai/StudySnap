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
    jobs
)
from starlette.middleware.cors import CORSMiddleware

app = FastAPI(title="StudySnapAI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your needs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _process_file_job(file_id: str, job_id: str, email: str, userId: str, include_quiz: bool = True, test: bool = False):
    """Background job to download a PDF from Supabase, run the pipeline, and upload outputs."""
    client = get_supabase_client()
    record = fetch_document_file(client, file_id)

    document_id = record["document_id"]
    storage_key = record["storage_key"]
    original_name = record.get("original_name") or f"{file_id}.pdf"

    namespace = original_name.rsplit(".", 1)[0]

    jobs.add_job(job_id=job_id, status="pending",
                 file_id=document_id, email=email)
    temp_dir = Path(tempfile.mkdtemp(prefix="studysnap_"))
    local_pdf = temp_dir / original_name

    try:

        jobs.update_job_status(job_id=job_id, status="reading")

        fp = download_document_file(client, storage_key, local_pdf)

        print("="*70)
        print("\n\n")
        print("File Downloaded at " + str(fp))
        print("\n\n")
        print("="*70)

        pipeline = PDFToFlashcardPipeline(
            pdf_path=str(local_pdf), table_name=namespace)

        # Run the pipeline steps
        if not pipeline.process_pdf():
            raise RuntimeError("Failed during PDF processing")

        jobs.update_job_status(job_id=job_id, status="flashcards")
        flashcards = pipeline.generate_flashcards()
        if not flashcards:
            raise RuntimeError("No flashcards generated")

        jobs.update_job_status(job_id=job_id, status="quizzes")
        quiz_questions: List = []
        if include_quiz:
            quiz_questions = pipeline.generate_quiz()

        jobs.update_job_status(job_id=job_id, status="completed")
        output_files = pipeline.save_outputs(
            flashcards, quiz_questions if quiz_questions else None, namespace=namespace
        )
        if not output_files:
            raise RuntimeError("No outputs were saved")

        uploaded_keys = upload_generated_outputs(
            client, str(email), output_files, original_name)

        # Remove the outputs after upload
        pipeline.remove_outputs(output_files)

        print("==================================================\n\n")

        print(f"Uploaded generated outputs: {uploaded_keys}")

        print("\n\n==================================================")
    except Exception as e:
        jobs.update_job_status(job_id=job_id, status="failed")
        print(f"Error processing file {file_id} for job {job_id}: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/test/{id}")
async def test_endpoint(id: str, param1: str, param2: int):
    print(
        f"Test endpoint called with id: {id}, param1: {param1}, param2: {param2}")
    return {"message": f"Test endpoint received id: {id}"}


@app.post("/process/{file_id}")
async def process_file(file_id: str, email: str, userId: str, include_quiz: bool = True, background_tasks: BackgroundTasks = None):
    """
    Kick off processing for a file uploaded to Supabase Storage.

    The request returns immediately while the heavy work runs in a background task.
    Supabase Realtime can be used to watch the target buckets for uploaded outputs.
    """
    print(
        f"Received processing request for file_id: {file_id}, email: {email}, userId: {userId}")

    if not file_id:
        raise HTTPException(status_code=400, detail="file_id is required")

    job_id = str(uuid.uuid4())
    background_tasks.add_task(
        _process_file_job, file_id, job_id, email, userId, include_quiz, True)

    return {
        "jobId": job_id,
        "status": "started",
        "message": "Processing started. Watch Supabase buckets for outputs.",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
