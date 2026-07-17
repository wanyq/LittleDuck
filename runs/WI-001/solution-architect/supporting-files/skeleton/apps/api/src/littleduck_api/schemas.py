import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CreateGenerationRequest(ApiModel):
    conversation_id: uuid.UUID | None = Field(default=None, alias="conversationId")
    client_message_id: uuid.UUID = Field(alias="clientMessageId")
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content", mode="before")
    @classmethod
    def trim_content(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class RetryGenerationRequest(ApiModel):
    client_retry_id: uuid.UUID = Field(alias="clientRetryId")


class ErrorBody(ApiModel):
    code: str
    message: str
    request_id: str = Field(alias="requestId")
    generation_id: uuid.UUID | None = Field(default=None, alias="generationId")


class ErrorEnvelope(ApiModel):
    error: ErrorBody
