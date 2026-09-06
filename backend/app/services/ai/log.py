"""Persist an `AIResult` as an `AIGeneration` audit row.

Called from routes/engine/inbound after every AI call so each output is traceable
to the exact facts it saw. Flushes but does not commit — the caller owns the txn.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.ai import AIGeneration
from app.services.ai.base import AIResult


def record(
    db: Session,
    result: AIResult,
    *,
    workspace_id: str,
    facts: dict[str, Any] | None = None,
    created_by: str | None = None,
    lead_id: str | None = None,
    campaign_id: str | None = None,
    message_id: str | None = None,
) -> AIGeneration:
    row = AIGeneration(
        workspace_id=workspace_id,
        created_by=created_by,
        kind=result.kind or "unknown",
        model=result.model,
        status=result.status,
        lead_id=lead_id,
        campaign_id=campaign_id,
        message_id=message_id,
        facts=facts,
        output=result.output or None,
        assumptions=result.assumptions or None,
        error=result.error,
        latency_ms=result.latency_ms,
        tokens=result.tokens,
    )
    db.add(row)
    db.flush()
    return row
