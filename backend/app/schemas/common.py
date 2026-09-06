from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.models.enums import SuppressionReason


class SuppressionCreate(BaseModel):
    channel: Literal["email", "whatsapp", "linkedin", "all"] = "all"
    value: str
    reason: SuppressionReason = SuppressionReason.manual
    note: str | None = None


class SuppressionOut(BaseModel):
    id: str
    channel: str
    value: str
    reason: SuppressionReason
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CSVImportMapping(BaseModel):
    """Maps CSV column headers -> lead fields (spec §42)."""

    column_map: dict[str, str]           # {"Email": "email", "Full Name": "full_name", ...}
    rows: list[dict[str, Any]]           # parsed CSV rows
    source_name: str = "CSV Import"
    dedup: bool = True
    apply_suppression: bool = True


class CSVImportResult(BaseModel):
    created: int
    duplicates_skipped: int
    suppressed_skipped: int
    errors: list[str]
    source_id: str
