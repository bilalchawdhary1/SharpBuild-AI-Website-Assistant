from typing import Literal
from pydantic import BaseModel, Field, field_validator


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=500)


class ChatRequest(BaseModel):
    # Real visitor questions are short; a tight cap limits cost and prompt-injection payloads.
    message: str = Field(min_length=1, max_length=500)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class ChatSource(BaseModel):
    url: str
    title: str
    section: str


class LeadInfo(BaseModel):
    """Qualification picture for sales conversations. Booleans only: never the visitor's details."""
    score: Literal["hot", "warm", "cold"]
    need: bool
    budget: bool
    timeline: bool
    contact: bool
    next_field: str | None = None       # the most useful thing still unknown
    next_question: str | None = None    # suggested follow-up; None when it needs consent first


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    fallback: bool = False      # True: no grounded answer; the widget should offer human contact
    intent: str | None = None   # routing label from services/intent.py; informational for the widget
    lead: LeadInfo | None = None  # only present when the conversation shows a sales signal
