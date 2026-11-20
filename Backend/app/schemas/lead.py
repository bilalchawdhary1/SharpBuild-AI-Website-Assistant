from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.chat import ChatTurn
from app.services.contact_validation import normalize_email, normalize_phone


class LeadRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=1000)
    consent: bool
    kind: Literal["sales", "handoff"] = "sales"   # "handoff": the visitor asked to talk to a person
    share_chat: bool = False                      # separate opt-in: pass the visitor's recent messages to the team
    # Recent conversation, only used to compute the lead score on the server; never stored.
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)
    website: str = Field(default="", max_length=200)    # honeypot: real visitors never see or fill it

    @field_validator("name", "email", "phone", "company", "message", "website", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        return normalize_phone(value) if value else None

    @field_validator("company", "message")
    @classmethod
    def empty_is_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("consent")
    @classmethod
    def consent_required(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("consent is required to save your details")
        return value


class LeadResponse(BaseModel):
    ok: bool = True
