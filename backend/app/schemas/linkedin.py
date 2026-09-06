"""Schemas for the assisted-LinkedIn subsystem (Phase 5): identity connect + task queue."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LinkedInConnectRequest(BaseModel):
    """Connect a LinkedIn *identity* — the operator/profile that will send manually.

    No credentials are stored: automation is deliberately not attempted. Connecting an
    identity is what satisfies `can_send`'s account-connected check for live LinkedIn.
    """

    display_name: str = Field(min_length=1, max_length=255)
    profile_url: str | None = Field(default=None, max_length=512)


class LinkedInAccountOut(BaseModel):
    id: str
    provider: str
    display_name: str | None = None
    profile_url: str | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LinkedInTaskOut(BaseModel):
    id: str                       # the outbound Message id
    lead_id: str | None = None
    lead_name: str | None = None
    lead_title: str | None = None
    profile_url: str | None = None
    campaign_id: str | None = None
    campaign_name: str | None = None
    body: str | None = None
    created_at: datetime


class CompleteTaskRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class SkipTaskRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class LogReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    from_name: str | None = Field(default=None, max_length=255)


class SimpleOk(BaseModel):
    ok: bool = True
    detail: str | None = None
