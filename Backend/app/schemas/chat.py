from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    # Real visitor questions are short; a tight cap limits cost and prompt-injection payloads.
    message: str = Field(min_length=1, max_length=500)

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


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]
    fallback: bool = False      # True: no grounded answer; the widget should offer human contact
