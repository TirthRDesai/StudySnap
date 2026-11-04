from typing import Literal

from pydantic import BaseModel, Field


class JobRequest(BaseModel):
    kind: Literal["study", "explainer"]

    # study: flashcards (+ quiz)
    n_cards: int = Field(default=100, ge=10, le=300, description="Total flashcards to keep for the whole book.")
    mode: Literal["exam", "overview"] = "exam"
    include_quiz: bool = True
    quiz_questions: int = Field(default=30, ge=5, le=100)

    # explainer
    level: Literal["eli5", "student", "detailed"] = "student"


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    progress: int
    message: str | None = None
