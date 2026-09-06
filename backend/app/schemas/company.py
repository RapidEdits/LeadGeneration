from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CompanyBase(BaseModel):
    name: str
    domain: str | None = None
    website: str | None = None
    industry: str | None = None
    size: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    description: str | None = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    website: str | None = None
    industry: str | None = None
    size: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    description: str | None = None


class CompanyOut(CompanyBase):
    id: str
    workspace_id: str
    enrichment: dict[str, Any] | None = None
    lead_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
