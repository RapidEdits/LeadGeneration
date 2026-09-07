"""Schemas for the analytics subsystem (Phase 8): overview KPIs, the lead funnel,
outreach performance, activity time series, per-campaign performance, and the AI
insights envelope."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.schemas.ai import AIResultOut


class OverviewResponse(BaseModel):
    days: int
    total_leads: int
    new_leads: int              # leads created in the window
    qualified_leads: int
    contacted_leads: int
    replied_leads: int
    won_leads: int
    lost_leads: int
    active_campaigns: int
    messages_sent: int          # outbound in the window
    replies_received: int       # inbound in the window
    reply_rate: float           # replies_received / messages_sent
    win_rate: float             # won_leads / (won + lost)
    open_tasks: int
    overdue_tasks: int


class FunnelStage(BaseModel):
    status: str
    label: str
    count: int
    # % of the widest upstream stage still present at this stage.
    conversion_from_top: float


class FunnelResponse(BaseModel):
    stages: list[FunnelStage]


class ChannelBreakdown(BaseModel):
    channel: str
    sent: int
    opened: int
    clicked: int
    replied: int
    bounced: int
    open_rate: float
    reply_rate: float
    bounce_rate: float


class OutreachResponse(BaseModel):
    days: int
    total_sent: int
    total_opened: int
    total_clicked: int
    total_replied: int
    total_bounced: int
    open_rate: float
    click_rate: float
    reply_rate: float
    bounce_rate: float
    by_channel: list[ChannelBreakdown]


class TimeseriesPoint(BaseModel):
    date: date
    leads_created: int
    messages_sent: int
    replies: int


class TimeseriesResponse(BaseModel):
    days: int
    points: list[TimeseriesPoint]


class CampaignPerformance(BaseModel):
    id: str
    name: str
    state: str
    total_leads: int
    messages_sent: int
    opened: int
    replied: int
    bounced: int
    reply_rate: float
    open_rate: float
    bounce_rate: float


class CampaignsPerformanceResponse(BaseModel):
    campaigns: list[CampaignPerformance]


class InsightsResponse(BaseModel):
    result: AIResultOut
