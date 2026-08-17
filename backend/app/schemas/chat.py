from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = Field(
        default=None,
        alias="conversationId",
        max_length=128,
    )

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value.strip()


class Source(BaseModel):
    title: str
    url: str
    section: str
    relevance: float = Field(..., ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
