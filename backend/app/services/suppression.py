"""Suppression checks. Global per workspace, honored across all channels/campaigns."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.outreach import SuppressionEntry
from app.utils.normalize import normalize_email, normalize_linkedin, normalize_phone


def _normalized_value(channel: str, raw: str) -> str | None:
    if channel == "email":
        return normalize_email(raw)
    if channel == "whatsapp":
        return normalize_phone(raw)
    if channel == "linkedin":
        return normalize_linkedin(raw)
    return raw.strip().lower() if raw else None


def is_suppressed(db: Session, workspace_id: str, channel: str, value: str) -> bool:
    """True if `value` is suppressed for `channel` (or via an 'all'-channel entry)."""
    norm = _normalized_value(channel, value)
    if not norm:
        return False
    stmt = select(SuppressionEntry.id).where(
        SuppressionEntry.workspace_id == workspace_id,
        SuppressionEntry.value == norm,
        SuppressionEntry.channel.in_([channel, "all"]),
    ).limit(1)
    return db.execute(stmt).first() is not None


def add_suppression(
    db: Session,
    workspace_id: str,
    channel: str,
    value: str,
    reason,
    note: str | None = None,
) -> SuppressionEntry | None:
    """Idempotent insert (unique on workspace+channel+value). Returns entry or None if dup."""
    norm = _normalized_value(channel, value)
    if not norm:
        return None
    existing = db.execute(
        select(SuppressionEntry).where(
            SuppressionEntry.workspace_id == workspace_id,
            SuppressionEntry.channel == channel,
            SuppressionEntry.value == norm,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    entry = SuppressionEntry(
        workspace_id=workspace_id, channel=channel, value=norm, reason=reason, note=note
    )
    db.add(entry)
    db.flush()
    return entry
