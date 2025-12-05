from supabase_utils import client

supabase_client = client.get_supabase_client()

status_types = ["pending", "reading",
                "flashcards", "quizzes", "completed", "failed"]


def add_job(job_id: str, status: str, file_id: str):
    """Add a new job record to the Supabase 'jobs' table."""

    if (status not in status_types):
        raise ValueError(f"Invalid status type: {status}")

    data = {
        "job_id": job_id,
        "status": status,
        "document_id": file_id,
    }

    try:
        response = supabase_client.table("jobs").insert(data).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to add job: {e}")

    print(f"Job: {job_id} added with status: {status}")

    return response.data


def update_job_status(job_id: str, status: str):
    """Update the status of an existing job in the Supabase 'jobs' table."""
    if (status not in status_types):
        raise ValueError(f"Invalid status type: {status}")
    data = {
        "status": status,
    }
    try:
        response = supabase_client.table("jobs").update(
            data).eq("job_id", job_id).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to update job status: {e}")

    print(f"Job: {job_id} updated with status: {status}")
    return response.data
