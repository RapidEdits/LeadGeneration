from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import ApprovalMode, CampaignLeadState, CampaignState, Channel


class ScheduleWindow(BaseModel):
    days: list[int] | None = Field(default=None, description="0=Mon … 6=Sun; null = any day")
    start: str | None = Field(default=None, description="HH:MM")
    end: str | None = Field(default=None, description="HH:MM")
    tz: str = "UTC"


class ChannelConfig(BaseModel):
    enabled: bool = False
    daily_limit: int | None = None
    schedule: ScheduleWindow | None = None


class StepIn(BaseModel):
    channel: Channel
    delay_days: int = Field(default=0, ge=0, le=365)
    subject: str | None = None
    body_template: str | None = None
    ai_prompt: str | None = None
    enabled: bool = True


class StepOut(StepIn):
    id: str
    order_index: int
    model_config = {"from_attributes": True}


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    approval_mode: ApprovalMode = ApprovalMode.auto
    test_mode: bool = True
    steps: list[StepIn] = Field(default_factory=list)


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    channels: dict[str, ChannelConfig] | None = None
    approval_mode: ApprovalMode | None = None
    test_mode: bool | None = None
    steps: list[StepIn] | None = None


class CampaignStats(BaseModel):
    total: int = 0
    pending: int = 0
    active: int = 0
    completed: int = 0
    replied: int = 0
    skipped: int = 0
    failed: int = 0
    awaiting_action: int = 0
    messages_sent: int = 0


class CampaignOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None = None
    state: CampaignState
    test_mode: bool
    approval_mode: ApprovalMode
    channels: dict
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[StepOut] = []
    stats: CampaignStats | None = None

    model_config = {"from_attributes": True}


class AddLeadsRequest(BaseModel):
    lead_ids: list[str]


class AddLeadsResponse(BaseModel):
    added: int


class CampaignLeadOut(BaseModel):
    id: str
    lead_id: str
    state: CampaignLeadState
    current_step: int
    next_action_at: datetime | None = None
    last_sent_at: datetime | None = None
    attempts: int
    last_reason: str | None = None
    lead_name: str | None = None
    lead_email: str | None = None

    model_config = {"from_attributes": True}


class CanSendPreview(BaseModel):
    lead_id: str
    channel: Channel


class CanSendResult(BaseModel):
    allowed: bool
    reasons: list[str]
    checks: dict[str, bool]


class MessageOut(BaseModel):
    id: str
    channel: Channel
    direction: str
    status: str
    subject: str | None = None
    body: str | None = None
    to_address: str | None = None
    lead_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransitionResponse(BaseModel):
    id: str
    state: CampaignState
