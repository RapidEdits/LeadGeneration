"""Import all models so Alembic autogenerate + Base.metadata see them."""
from app.models.enums import (  # noqa: F401
    AuditAction,
    CampaignStatus,
    ConnectedAccountStatus,
    ConnectedAccountType,
    LeadStatus,
    Provenance,
    SuppressionReason,
    TaskStatus,
    TaskType,
    WorkspaceRole,
)
from app.models.crm import (  # noqa: F401
    LeadNote,
    Task,
)
from app.models.ai import (  # noqa: F401
    AIGeneration,
)
from app.models.campaign import (  # noqa: F401
    Campaign,
    CampaignLead,
    CampaignStep,
)
from app.models.lead import (  # noqa: F401
    Company,
    Lead,
    LeadSource,
    LeadTag,
    Tag,
)
from app.models.message import (  # noqa: F401
    Message,
    MessageEvent,
)
from app.models.outreach import (  # noqa: F401
    AuditLog,
    ConnectedAccount,
    SavedFilter,
    SuppressionEntry,
    UnsubscribeEvent,
)
from app.models.user import (  # noqa: F401
    User,
    Workspace,
    WorkspaceMember,
)

__all__ = [
    "User",
    "Workspace",
    "WorkspaceMember",
    "Company",
    "Lead",
    "LeadSource",
    "Tag",
    "LeadTag",
    "SuppressionEntry",
    "ConnectedAccount",
    "SavedFilter",
    "AuditLog",
    "UnsubscribeEvent",
    "Campaign",
    "CampaignStep",
    "CampaignLead",
    "Message",
    "MessageEvent",
    "AIGeneration",
    "Task",
    "LeadNote",
]
