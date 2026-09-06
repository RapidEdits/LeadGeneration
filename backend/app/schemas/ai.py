from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.lead import LeadFilter, LeadListResponse


class AIStatus(BaseModel):
    enabled: bool
    model: str | None = None


class AIResultOut(BaseModel):
    """Uniform envelope mirroring services.ai.base.AIResult."""

    status: str
    kind: str | None = None
    model: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    latency_ms: int | None = None
    error: str | None = None


class QualifyRequest(BaseModel):
    icp: dict[str, Any] | None = None


class BulkQualifyRequest(BaseModel):
    lead_ids: list[str]
    icp: dict[str, Any] | None = None


class BulkQualifyItem(BaseModel):
    lead_id: str
    status: str
    score: int | None = None
    verdict: str | None = None


class BulkQualifyResponse(BaseModel):
    processed: int
    results: list[BulkQualifyItem]


class GenerateRequest(BaseModel):
    lead_id: str
    context: dict[str, Any] | None = None


class FollowUpRequest(BaseModel):
    lead_id: str
    context: dict[str, Any] | None = None


class ClassifyReplyRequest(BaseModel):
    message: str | None = None
    message_id: str | None = None


class NLSearchRequest(BaseModel):
    query: str


class NLSearchResponse(BaseModel):
    result: AIResultOut
    filter: LeadFilter
    leads: LeadListResponse


class CopilotRequest(BaseModel):
    question: str


class AIGenerationOut(BaseModel):
    id: str
    kind: str
    model: str | None = None
    status: str
    lead_id: str | None = None
    campaign_id: str | None = None
    output: dict[str, Any] | None = None
    assumptions: list[Any] | None = None
    latency_ms: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
