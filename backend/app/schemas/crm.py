"""Schemas for the CRM subsystem (Phase 7): tasks, notes, timeline, pipeline."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import LeadStatus, TaskStatus, TaskType


# ---- Tasks ----

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    type: TaskType = TaskType.todo
    description: str | None = None
    due_at: datetime | None = None
    lead_id: str | None = None
    assignee_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    type: TaskType | None = None
    status: TaskStatus | None = None
    description: str | None = None
    due_at: datetime | None = None
    assignee_id: str | None = None


class TaskOut(BaseModel):
    id: str
    type: TaskType
    status: TaskStatus
    title: str
    description: str | None = None
    due_at: datetime | None = None
    completed_at: datetime | None = None
    lead_id: str | None = None
    lead_name: str | None = None
    assignee_id: str | None = None
    assignee_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Notes ----

class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class NoteOut(BaseModel):
    id: str
    lead_id: str
    body: str
    author_id: str | None = None
    author_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Unified lead timeline ----

class TimelineItem(BaseModel):
    kind: Literal["message", "note", "task", "event"]
    id: str
    at: datetime
    title: str | None = None
    body: str | None = None
    channel: str | None = None
    direction: str | None = None
    status: str | None = None
    actor: str | None = None
    meta: dict[str, Any] | None = None


# ---- Pipeline ----

class PipelineCard(BaseModel):
    id: str
    full_name: str | None = None
    title: str | None = None
    company_name: str | None = None
    email: str | None = None
    score: float | None = None
    status: LeadStatus
    updated_at: datetime
    open_tasks: int = 0


class PipelineStage(BaseModel):
    status: LeadStatus
    label: str
    count: int
    cards: list[PipelineCard]


class PipelineResponse(BaseModel):
    stages: list[PipelineStage]


class SimpleOk(BaseModel):
    ok: bool = True
    detail: str | None = None
