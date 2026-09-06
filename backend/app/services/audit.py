"""Audit-log writer. Every meaningful mutation should record one."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import AuditAction
from app.models.outreach import AuditLog


def record(
    db: Session,
    *,
    action: AuditAction,
    workspace_id: str | None = None,
    actor_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> AuditLog:
    log = AuditLog(
        action=action,
        workspace_id=workspace_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data,
    )
    db.add(log)
    db.flush()
    return log
