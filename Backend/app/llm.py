"""Thin wrapper around the local Ollama server (`ollama serve`)."""
import json
import logging
from typing import Any

import ollama
from pydantic import BaseModel, ValidationError

from .config import settings

log = logging.getLogger("studysnap.llm")

_client = ollama.Client(host=settings.ollama_host, timeout=600)


class LLMError(RuntimeError):
    pass


def health() -> dict[str, Any]:
    """Report whether Ollama is reachable and the configured models are pulled."""
    try:
        listed = _client.list()
    except Exception as exc:  # connection refused, etc.
        return {"reachable": False, "error": str(exc), "missing_models": []}
    names = {m.model for m in listed.models}

    def has(wanted: str) -> bool:
        # "name" matches "name:latest"
        return wanted in names or f"{wanted}:latest" in names

    missing = [m for m in (settings.generation_model, settings.embedding_model) if not has(m)]
    return {"reachable": True, "missing_models": missing}


def generate_json(system: str, user: str, model_cls: type[BaseModel], retries: int = 1) -> BaseModel | None:
    """Ask the model for JSON matching `model_cls`'s schema. Returns None if it never validates.

    Ollama's structured output (`format=<json schema>`) constrains decoding, so invalid JSON
    is rare; validation still guards against schema-valid but semantically bad output.
    """
    schema = model_cls.model_json_schema()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(retries + 1):
        try:
            resp = _client.chat(
                model=settings.generation_model,
                messages=messages,
                format=schema,
                options={"temperature": 0.3, "num_ctx": settings.num_ctx},
            )
        except Exception as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        content = resp.message.content or ""
        try:
            return model_cls.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("Model output rejected (attempt %d): %s", attempt + 1, str(exc)[:200])
    return None


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    out: list[list[float]] = []
    for i in range(0, len(texts), 32):
        batch = texts[i : i + 32]
        try:
            resp = _client.embed(model=settings.embedding_model, input=batch)
        except Exception as exc:
            raise LLMError(f"Embedding request failed: {exc}") from exc
        out.extend(resp.embeddings)
    return out
