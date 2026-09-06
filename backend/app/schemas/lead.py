from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import CampaignStatus, LeadStatus, Provenance


class LeadBase(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    location: str | None = None
    company_id: str | None = None
    notes: str | None = None
    custom_fields: dict[str, Any] | None = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(LeadBase):
    status: LeadStatus | None = None
    score: float | None = None


class LeadOut(LeadBase):
    id: str
    workspace_id: str
    status: LeadStatus
    campaign_status: CampaignStatus
    score: float | None = None
    email_provenance: Provenance
    ai_qualification: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadListResponse(BaseModel):
    items: list[LeadOut]
    total: int
    page: int
    page_size: int


# ---- Advanced filtering (spec §22) ----
FilterOp = Literal[
    "eq", "neq", "contains", "starts_with", "in", "gt", "gte", "lt", "lte", "is_null", "not_null"
]


class FilterCondition(BaseModel):
    field: str
    op: FilterOp = "eq"
    value: Any | None = None


class LeadFilter(BaseModel):
    match: Literal["all", "any"] = "all"
    conditions: list[FilterCondition] = Field(default_factory=list)
    search: str | None = None
    sort_by: str = "created_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)


class BulkActionRequest(BaseModel):
    lead_ids: list[str]
    action: Literal["delete", "set_status", "add_tag", "suppress"]
    status: LeadStatus | None = None
    tag: str | None = None


class BulkActionResponse(BaseModel):
    affected: int


class DuplicateGroup(BaseModel):
    key: str
    match_type: str  # email | linkedin | phone | name_company
    lead_ids: list[str]


class MergeRequest(BaseModel):
    primary_id: str
    duplicate_ids: list[str]
