"""Centralized outbound authorization gate (spec §52).

The ONLY sanctioned path to any outbound action. Enforced in the Celery worker,
never bypassed by the UI. Disabling a channel disables the backend, not just a
toggle. Every check is explicit and returned, so a denial is fully explainable.

Phase 2 implements the full chain against a Campaign. Live provider connectivity
(account_connected) is only required when a campaign is NOT in test mode; test
mode simulates sends so the whole engine is exercisable before Phases 3-6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.enums import (
    ApprovalMode,
    Channel,
    ConnectedAccountStatus,
    ConnectedAccountType,
    MessageDirection,
    MessageStatus,
)
from app.models.message import Message
from app.models.outreach import ConnectedAccount
from app.services.suppression import is_suppressed

# Statuses that count as "a message went out" for rate/frequency accounting.
_SENT_STATUSES = (MessageStatus.sent, MessageStatus.delivered, MessageStatus.simulated,
                  MessageStatus.opened, MessageStatus.replied)


@dataclass
class Decision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def blocked(cls, reason: str, checks: dict[str, bool] | None = None) -> "Decision":
        return cls(allowed=False, reasons=[reason], checks=checks or {})


def _channel_config(campaign: Campaign, channel: str) -> dict:
    return (campaign.channels or {}).get(channel, {}) if campaign else {}


def _within_schedule(schedule: dict | None, now: datetime | None = None) -> bool:
    """True if `now` falls within the schedule window. No schedule => always allowed."""
    if not schedule:
        return True
    now = now or datetime.now(timezone.utc)
    tz_name = schedule.get("tz", "UTC")
    try:
        local = now.astimezone(ZoneInfo(tz_name))
    except Exception:  # noqa: BLE001 — unknown tz falls back to UTC
        local = now.astimezone(timezone.utc)

    days = schedule.get("days")
    if days is not None and local.weekday() not in days:
        return False

    start, end = schedule.get("start"), schedule.get("end")
    if start and end:
        cur = local.hour * 60 + local.minute
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        if not (sh * 60 + sm <= cur <= eh * 60 + em):
            return False
    return True


def _sent_today(db: Session, *, campaign_id: str, channel: str) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.execute(
        select(func.count()).select_from(Message).where(
            Message.campaign_id == campaign_id,
            Message.channel == Channel(channel),
            Message.direction == MessageDirection.outbound,
            Message.status.in_(_SENT_STATUSES),
            Message.created_at >= since,
        )
    ).scalar_one()


def _contacted_lead_today(db: Session, *, lead_id: str, channel: str, exclude_campaign_id: str) -> bool:
    """Cross-campaign frequency cap: has this lead been contacted on `channel` in the
    last 24h by a DIFFERENT campaign? Intra-campaign cadence is governed by step delays,
    so the current campaign's own sends are excluded."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    row = db.execute(
        select(Message.id).where(
            Message.lead_id == lead_id,
            Message.channel == Channel(channel),
            Message.direction == MessageDirection.outbound,
            Message.status.in_(_SENT_STATUSES),
            Message.created_at >= since,
            Message.campaign_id != exclude_campaign_id,
        ).limit(1)
    ).first()
    return row is not None


def can_send(
    db: Session,
    *,
    campaign: Campaign,
    channel: str,
    lead_value: str,
    lead_id: str | None = None,
    approved: bool = False,
    now: datetime | None = None,
) -> Decision:
    """Evaluate the full outbound decision chain for one (campaign, channel, lead)."""
    cfg = _channel_config(campaign, channel)
    workspace_id = campaign.workspace_id

    checks: dict[str, bool] = {}

    # 1. Channel enabled on the campaign (server-side source of truth).
    checks["channel_enabled"] = bool(cfg.get("enabled", False))

    # 2. Sending account connected (only required outside test mode).
    if campaign.test_mode:
        checks["account_connected"] = True
    else:
        acct = db.execute(
            select(ConnectedAccount.id).where(
                ConnectedAccount.workspace_id == workspace_id,
                ConnectedAccount.type == ConnectedAccountType(channel),
                ConnectedAccount.status == ConnectedAccountStatus.connected,
            ).limit(1)
        ).first()
        checks["account_connected"] = acct is not None

    # 3. Lead not suppressed / opted out (global per workspace).
    checks["not_suppressed"] = not is_suppressed(db, workspace_id, channel, lead_value)

    # 4. Frequency: not already contacted on this channel in the last 24h by another campaign.
    checks["frequency_ok"] = not (
        lead_id and _contacted_lead_today(
            db, lead_id=lead_id, channel=channel, exclude_campaign_id=campaign.id
        )
    )

    # 5. Provider allowed (per-provider allowlist — placeholder, expands later).
    checks["provider_allowed"] = True

    # 6. Rate-limit budget: under the channel's daily_limit for this campaign.
    daily_limit = cfg.get("daily_limit")
    if daily_limit in (None, 0):
        checks["rate_limit_ok"] = True
    else:
        checks["rate_limit_ok"] = _sent_today(db, campaign_id=campaign.id, channel=channel) < daily_limit

    # 7. Schedule window valid.
    checks["schedule_ok"] = _within_schedule(cfg.get("schedule"), now)

    # 8. Human approval satisfied.
    if campaign.approval_mode == ApprovalMode.auto:
        checks["approval_satisfied"] = True
    else:
        checks["approval_satisfied"] = bool(approved)

    reasons = [name for name, ok in checks.items() if not ok]
    return Decision(allowed=len(reasons) == 0, reasons=reasons, checks=checks)
