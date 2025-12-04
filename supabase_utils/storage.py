from pathlib import Path
from typing import Dict, List, Optional

from supabase import Client


def fetch_document_file(client: Client, file_id: str) -> Dict:
    """
    Fetch a document_files row by id.

    Returns:
        The row dict including document_id and storage_key.
    Raises:
        ValueError if not found.
    """
    response = (
        client.table("document_files")
        .select("*")
        .eq("id", file_id)
        .limit(1)
        .execute()
    )
    data = response.data or []
    if not data:
        raise ValueError(f"No document_files row found for id={file_id}")
    return data[0]


def download_document_file(client: Client, storage_key: str, dest_path: Path, bucket: str = "documents") -> Path:
    """
    Download a file from Supabase Storage to dest_path.
    """
    file_bytes = client.storage.from_(bucket).download(storage_key)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(file_bytes)
    return dest_path


def _detect_bucket_for_output(filename: str) -> Optional[str]:
    """Map output filename to a storage bucket."""
    name = filename.lower()
    if name.startswith("flashcards_"):
        return "flashcards"
    if name.startswith("quiz_"):
        return "quizzes"
    if name.startswith("answer_key_"):
        return "answer-keys"
    if name.startswith("quiz_student_"):
        return "student-quizzes"
    if name.startswith("summary_"):
        return "summaries"
    return None


def upload_generated_outputs(client: Client, document_id: str, files: List[Path]) -> List[str]:
    """
    Upload generated output files to their respective buckets.

    Args:
        client: Supabase client
        document_id: documents.id to namespace objects
        files: List of file Paths to upload

    Returns:
        List of storage keys that were uploaded.
    """
    uploaded_keys: List[str] = []
    for file_path in files:
        bucket = _detect_bucket_for_output(file_path.name)
        if not bucket:
            # Skip unknown files instead of failing the whole upload
            continue

        storage_key = f"{document_id}/{file_path.name}"
        client.storage.from_(bucket).upload(
            storage_key,
            file_path.read_bytes(),
            {"upsert": "true"},  # header values must be strings
        )
        uploaded_keys.append(f"{bucket}/{storage_key}")

    return uploaded_keys
