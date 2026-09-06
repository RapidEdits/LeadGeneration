"""Shared enums used across models and schemas."""
from __future__ import annotations

import enum


class WorkspaceRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    sales = "sales"
    viewer = "viewer"


class LeadStatus(str, enum.Enum):
    new = "new"
    enriched = "enriched"
    qualified = "qualified"
    contacted = "contacted"
    replied = "replied"
    won = "won"
    lost = "lost"
    disqualified = "disqualified"


class CampaignStatus(str, enum.Enum):
    none = "none"          # not in any campaign
    queued = "queued"
    active = "active"
    paused = "paused"
    completed = "completed"


class Provenance(str, enum.Enum):
    observed = "observed"
    estimated = "estimated"
    unknown = "unknown"


class ConnectedAccountType(str, enum.Enum):
    email = "email"
    linkedin = "linkedin"
    whatsapp = "whatsapp"


class ConnectedAccountStatus(str, enum.Enum):
    disconnected = "disconnected"
    connected = "connected"
    error = "error"


class SuppressionReason(str, enum.Enum):
    unsubscribed = "unsubscribed"
    bounced = "bounced"
    complained = "complained"
    manual = "manual"
    invalid = "invalid"


# ---- Phase 7: CRM ----

class TaskType(str, enum.Enum):
    todo = "todo"
    call = "call"
    email = "email"
    meeting = "meeting"
    linkedin = "linkedin"


class TaskStatus(str, enum.Enum):
    open = "open"
    done = "done"
    cancelled = "cancelled"


class AuditAction(str, enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"
    login = "login"
    signup = "signup"
    import_csv = "import_csv"
    merge = "merge"
    suppress = "suppress"
    send_blocked = "send_blocked"
    campaign_launch = "campaign_launch"
    campaign_pause = "campaign_pause"
    campaign_resume = "campaign_resume"
    campaign_complete = "campaign_complete"
    message_sent = "message_sent"
    ai_generate = "ai_generate"


# ---- Phase 2: campaign engine ----

class Channel(str, enum.Enum):
    email = "email"
    linkedin = "linkedin"
    whatsapp = "whatsapp"


class CampaignState(str, enum.Enum):
    """Campaign lifecycle state machine (distinct from a lead's campaign_status)."""
    draft = "draft"
    scheduled = "scheduled"
    active = "active"
    paused = "paused"
    completed = "completed"
    archived = "archived"


class CampaignLeadState(str, enum.Enum):
    pending = "pending"        # added, not yet started
    active = "active"          # progressing through the sequence
    replied = "replied"        # lead replied — sequence halts
    bounced = "bounced"
    failed = "failed"
    skipped = "skipped"        # blocked by can_send (e.g. suppressed)
    awaiting_action = "awaiting_action"  # Phase 5: parked on an open assisted (LinkedIn) task
    completed = "completed"    # finished all steps


class ApprovalMode(str, enum.Enum):
    auto = "auto"              # send without human approval
    manual = "manual"          # each outbound needs human approval


class MessageDirection(str, enum.Enum):
    outbound = "outbound"
    inbound = "inbound"


class MessageStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    opened = "opened"
    replied = "replied"
    bounced = "bounced"
    failed = "failed"
    simulated = "simulated"    # test-mode send (no real provider hit)
    pending_action = "pending_action"  # Phase 5: queued for a human to send on an assisted channel


class MessageEventType(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    opened = "opened"
    clicked = "clicked"        # Phase 3: tracked link click
    replied = "replied"
    bounced = "bounced"
    unsubscribed = "unsubscribed"  # Phase 3: List-Unsubscribe / footer link
    complained = "complained"      # Phase 3: spam complaint
    failed = "failed"
    blocked = "blocked"        # can_send denied
