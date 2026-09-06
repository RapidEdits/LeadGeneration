"""AI endpoints (Phase 4) — every route funnels through the AIService seam and
records an AIGeneration audit row. When AI is not configured the service returns
`status="unknown"` (never fabricates, never 500s)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.ai import AIGeneration
from app.models.campaign import Campaign, CampaignLead
from app.models.enums import (
    AuditAction,
    LeadStatus,
    MessageDirection,
    SuppressionReason,
    WorkspaceRole,
)
from app.models.lead import Company, Lead
from app.models.message import Message
from app.schemas.ai import (
    AIGenerationOut,
    AIResultOut,
    AIStatus,
    BulkQualifyItem,
    BulkQualifyRequest,
    BulkQualifyResponse,
    ClassifyReplyRequest,
    CopilotRequest,
    FollowUpRequest,
    GenerateRequest,
    NLSearchRequest,
    NLSearchResponse,
    QualifyRequest,
)
from app.schemas.lead import FilterCondition, LeadFilter, LeadListResponse, LeadOut
from app.services import audit, lead_query, suppression
from app.services.ai import log as ai_log
from app.services.ai.base import AIResult
from app.services.ai.factory import get_ai_service

router = APIRouter(prefix="/ai", tags=["ai"])

# Fields the NL-search translator is allowed to target (mirrors lead_query._FILTERABLE).
_SEARCH_SCHEMA = {
    "fields": {
        "full_name": "string", "first_name": "string", "last_name": "string",
        "title": "string (job title)", "email": "string", "location": "string",
        "status": "enum: new|enriched|qualified|contacted|replied|won|lost|disqualified",
        "campaign_status": "enum: none|queued|active|paused|completed",
        "score": "number 0-100", "created_at": "datetime", "updated_at": "datetime",
    },
    "operators": ["eq", "neq", "contains", "starts_with", "in", "gt", "gte", "lt", "lte",
                  "is_null", "not_null"],
}


def _result_out(res: AIResult) -> AIResultOut:
    return AIResultOut(
        status=res.status, kind=res.kind, model=res.model, output=res.output or {},
        assumptions=res.assumptions or [], latency_ms=res.latency_ms, error=res.error,
    )


def _owned_lead(db: Session, ws_id: str, lead_id: str) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.workspace_id != ws_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return lead


def _lead_dict(db: Session, lead: Lead) -> dict:
    d = {
        "full_name": lead.full_name, "first_name": lead.first_name, "title": lead.title,
        "email": lead.email, "location": lead.location, "linkedin_url": lead.linkedin_url,
        "notes": lead.notes,
    }
    if lead.company_id:
        company = db.get(Company, lead.company_id)
        if company:
            d.update({"company_name": company.name, "industry": company.industry,
                      "company_size": company.size})
    return d


def _thread(db: Session, ws_id: str, lead_id: str) -> list[dict]:
    msgs = db.execute(
        select(Message).where(Message.workspace_id == ws_id, Message.lead_id == lead_id)
        .order_by(Message.created_at.asc()).limit(20)
    ).scalars().all()
    return [{"direction": m.direction.value, "subject": m.subject, "body": m.body} for m in msgs]


# ---------------------------------------------------------------------------

@router.get("/status", response_model=AIStatus)
def ai_status(ctx: WorkspaceContext = Depends(get_workspace_context)) -> AIStatus:
    svc = get_ai_service()
    return AIStatus(enabled=svc.enabled, model=svc.model_id if svc.enabled else None)


@router.post("/qualify/{lead_id}", response_model=AIResultOut)
def qualify_lead(
    lead_id: str,
    payload: QualifyRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> AIResultOut:
    lead = _owned_lead(db, ctx.workspace_id, lead_id)
    svc = get_ai_service()
    res = svc.qualify_lead(_lead_dict(db, lead), payload.icp)
    ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id, lead_id=lead.id)
    if res.ok:
        score = res.output.get("score")
        lead.score = float(score) if score is not None else lead.score
        lead.ai_qualification = res.output
        if res.output.get("verdict") in {"strong", "medium"} and lead.status == LeadStatus.new:
            lead.status = LeadStatus.qualified
    audit.record(db, action=AuditAction.ai_generate, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="lead", entity_id=lead.id,
                 data={"kind": "qualify_lead", "status": res.status})
    db.commit()
    return _result_out(res)


@router.post("/qualify", response_model=BulkQualifyResponse)
def qualify_bulk(
    payload: BulkQualifyRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> BulkQualifyResponse:
    svc = get_ai_service()
    leads = db.execute(
        select(Lead).where(Lead.workspace_id == ctx.workspace_id, Lead.id.in_(payload.lead_ids))
    ).scalars().all()
    results: list[BulkQualifyItem] = []
    for lead in leads:
        res = svc.qualify_lead(_lead_dict(db, lead), payload.icp)
        ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id, lead_id=lead.id)
        score = res.output.get("score") if res.ok else None
        if res.ok:
            lead.score = float(score) if score is not None else lead.score
            lead.ai_qualification = res.output
            if res.output.get("verdict") in {"strong", "medium"} and lead.status == LeadStatus.new:
                lead.status = LeadStatus.qualified
        results.append(BulkQualifyItem(
            lead_id=lead.id, status=res.status, score=score,
            verdict=res.output.get("verdict") if res.ok else None,
        ))
    audit.record(db, action=AuditAction.ai_generate, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="lead",
                 data={"kind": "qualify_lead", "count": len(results)})
    db.commit()
    return BulkQualifyResponse(processed=len(results), results=results)


@router.post("/generate/email", response_model=AIResultOut)
def generate_email(
    payload: GenerateRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> AIResultOut:
    lead = _owned_lead(db, ctx.workspace_id, payload.lead_id)
    res = get_ai_service().generate_email(_lead_dict(db, lead), payload.context)
    ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id, lead_id=lead.id)
    db.commit()
    return _result_out(res)


@router.post("/generate/linkedin", response_model=AIResultOut)
def generate_linkedin(
    payload: GenerateRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> AIResultOut:
    lead = _owned_lead(db, ctx.workspace_id, payload.lead_id)
    res = get_ai_service().generate_linkedin_message(_lead_dict(db, lead), payload.context)
    ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id, lead_id=lead.id)
    db.commit()
    return _result_out(res)


@router.post("/generate/follow-up", response_model=AIResultOut)
def generate_follow_up(
    payload: FollowUpRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> AIResultOut:
    lead = _owned_lead(db, ctx.workspace_id, payload.lead_id)
    thread = _thread(db, ctx.workspace_id, lead.id)
    res = get_ai_service().generate_follow_up(thread, payload.context)
    ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id, lead_id=lead.id)
    db.commit()
    return _result_out(res)


@router.post("/classify-reply", response_model=AIResultOut)
def classify_reply(
    payload: ClassifyReplyRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> AIResultOut:
    text = payload.message
    lead_id = None
    if payload.message_id:
        msg = db.get(Message, payload.message_id)
        if msg is None or msg.workspace_id != ctx.workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
        text = msg.body or ""
        lead_id = msg.lead_id
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "message or message_id required")
    res = get_ai_service().classify_reply(text)
    ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id, lead_id=lead_id)
    db.commit()
    return _result_out(res)


@router.post("/nl-search", response_model=NLSearchResponse)
def nl_search(
    payload: NLSearchRequest,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> NLSearchResponse:
    res = get_ai_service().nl_to_filters(payload.query, _SEARCH_SCHEMA)
    ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id)
    db.commit()

    out = res.output or {}
    raw_conditions = out.get("conditions") or []
    allowed_fields = set(_SEARCH_SCHEMA["fields"])
    conditions: list[FilterCondition] = []
    for c in raw_conditions:
        # Keep only well-formed conditions on fields we actually support, so the
        # returned filter reflects exactly what was applied.
        if isinstance(c, dict) and c.get("field") in allowed_fields:
            try:
                conditions.append(FilterCondition(**c))
            except Exception:  # noqa: BLE001 — drop malformed conditions, keep the valid ones
                continue
    flt = LeadFilter(
        match=out.get("match") if out.get("match") in ("all", "any") else "all",
        conditions=conditions,
        sort_by=out.get("sort_by") or "created_at",
        sort_dir=out.get("sort_dir") if out.get("sort_dir") in ("asc", "desc") else "desc",
    )

    from sqlalchemy import func
    conds = lead_query.build_conditions(flt)
    base = select(Lead).where(Lead.workspace_id == ctx.workspace_id, *conds)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(lead_query.order_by(flt)).limit(flt.page_size)
    ).scalars().all()
    leads = LeadListResponse(
        items=[LeadOut.model_validate(r) for r in rows], total=total,
        page=1, page_size=flt.page_size,
    )
    return NLSearchResponse(result=_result_out(res), filter=flt, leads=leads)


@router.post("/analyze-campaign/{campaign_id}", response_model=AIResultOut)
def analyze_campaign(
    campaign_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> AIResultOut:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.workspace_id != ctx.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Campaign not found")

    from sqlalchemy import func
    from app.models.enums import CampaignLeadState, MessageStatus

    def _count(model, *conds) -> int:
        return db.execute(select(func.count()).select_from(model).where(*conds)).scalar_one()

    total_members = _count(CampaignLead, CampaignLead.campaign_id == campaign.id)
    replied = _count(CampaignLead, CampaignLead.campaign_id == campaign.id,
                     CampaignLead.state == CampaignLeadState.replied)
    bounced = _count(CampaignLead, CampaignLead.campaign_id == campaign.id,
                     CampaignLead.state == CampaignLeadState.bounced)
    sent = _count(Message, Message.campaign_id == campaign.id,
                  Message.direction == MessageDirection.outbound)
    opened = _count(Message, Message.campaign_id == campaign.id,
                    Message.status == MessageStatus.opened)
    stats = {
        "name": campaign.name, "state": campaign.state.value,
        "steps": len(campaign.steps), "channels": list((campaign.channels or {}).keys()),
        "total_leads": total_members, "messages_sent": sent, "opened": opened,
        "replied": replied, "bounced": bounced,
        "reply_rate": round(replied / sent, 3) if sent else 0,
        "bounce_rate": round(bounced / sent, 3) if sent else 0,
    }
    res = get_ai_service().analyze_campaign(stats)
    ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id,
                  campaign_id=campaign.id)
    db.commit()
    return _result_out(res)


@router.post("/copilot", response_model=AIResultOut)
def copilot(
    payload: CopilotRequest,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> AIResultOut:
    from sqlalchemy import func

    context = {
        "total_leads": db.execute(
            select(func.count()).select_from(Lead).where(Lead.workspace_id == ctx.workspace_id)
        ).scalar_one(),
        "total_campaigns": db.execute(
            select(func.count()).select_from(Campaign).where(Campaign.workspace_id == ctx.workspace_id)
        ).scalar_one(),
        "leads_by_status": {
            s.value: db.execute(
                select(func.count()).select_from(Lead).where(
                    Lead.workspace_id == ctx.workspace_id, Lead.status == s)
            ).scalar_one() for s in LeadStatus
        },
    }
    res = get_ai_service().copilot(payload.question, context)
    ai_log.record(db, res, workspace_id=ctx.workspace_id, created_by=ctx.user.id)
    db.commit()
    return _result_out(res)


@router.get("/generations", response_model=list[AIGenerationOut])
def list_generations(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
    limit: int = 50,
) -> list[AIGenerationOut]:
    rows = db.execute(
        select(AIGeneration).where(AIGeneration.workspace_id == ctx.workspace_id)
        .order_by(AIGeneration.created_at.desc()).limit(min(limit, 200))
    ).scalars().all()
    return [AIGenerationOut.model_validate(r) for r in rows]
