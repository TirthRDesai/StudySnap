import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    ollama_host: str
    generation_model: str
    embedding_model: str
    num_ctx: int
    frontend_origins: tuple[str, ...]
    max_upload_mb: int
    books_bucket: str = "books"


def load_settings() -> Settings:
    origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    return Settings(
        supabase_url=os.getenv("SUPABASE_URL", "http://127.0.0.1:54321").rstrip("/"),
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
        supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        generation_model=os.getenv("GENERATION_MODEL", "qwen2.5:7b-instruct"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "mxbai-embed-large"),
        num_ctx=_int("NUM_CTX", 8192),
        frontend_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        max_upload_mb=_int("MAX_UPLOAD_MB", 50),
    )


settings = load_settings()
