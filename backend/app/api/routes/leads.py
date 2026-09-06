from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.enums import AuditAction, LeadStatus, SuppressionReason, WorkspaceRole
from app.models.lead import Lead, Tag, LeadTag
from app.schemas.lead import (
    BulkActionRequest,
    BulkActionResponse,
    DuplicateGroup,
    LeadCreate,
    LeadFilter,
    LeadListResponse,
    LeadOut,
    LeadUpdate,
    MergeRequest,
)
from app.services import audit, dedup, lead_query
from app.services.suppression import add_suppression

router = APIRouter(prefix="/leads", tags=["leads"])


def _get_owned_lead(db: Session, ws_id: str, lead_id: str) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.workspace_id != ws_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return lead


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> LeadOut:
    lead = Lead(workspace_id=ctx.workspace_id, **payload.model_dump(exclude_unset=True))
    if lead.full_name is None and (lead.first_name or lead.last_name):
        lead.full_name = " ".join(filter(None, [lead.first_name, lead.last_name]))
    db.add(lead)
    db.flush()
    audit.record(db, action=AuditAction.create, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="lead", entity_id=lead.id)
    db.commit()
    db.refresh(lead)
    return LeadOut.model_validate(lead)


@router.post("/search", response_model=LeadListResponse)
def search_leads(
    flt: LeadFilter,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> LeadListResponse:
    conds = lead_query.build_conditions(flt)
    base = select(Lead).where(Lead.workspace_id == ctx.workspace_id, *conds)

    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()

    rows = db.execute(
        base.order_by(lead_query.order_by(flt))
        .offset((flt.page - 1) * flt.page_size)
        .limit(flt.page_size)
    ).scalars().all()

    return LeadListResponse(
        items=[LeadOut.model_validate(r) for r in rows],
        total=total,
        page=flt.page,
        page_size=flt.page_size,
    )


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(
    lead_id: str,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> LeadOut:
    return LeadOut.model_validate(_get_owned_lead(db, ctx.workspace_id, lead_id))


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> LeadOut:
    lead = _get_owned_lead(db, ctx.workspace_id, lead_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(lead, k, v)
    db.flush()
    audit.record(db, action=AuditAction.update, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="lead", entity_id=lead.id)
    db.commit()
    db.refresh(lead)
    return LeadOut.model_validate(lead)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_lead(
    lead_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> None:
    lead = _get_owned_lead(db, ctx.workspace_id, lead_id)
    db.delete(lead)
    audit.record(db, action=AuditAction.delete, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="lead", entity_id=lead_id)
    db.commit()


@router.post("/bulk", response_model=BulkActionResponse)
def bulk_action(
    payload: BulkActionRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> BulkActionResponse:
    leads = db.execute(
        select(Lead).where(
            Lead.workspace_id == ctx.workspace_id, Lead.id.in_(payload.lead_ids)
        )
    ).scalars().all()

    affected = 0
    tag_obj: Tag | None = None
    if payload.action == "add_tag" and payload.tag:
        tag_obj = db.execute(
            select(Tag).where(Tag.workspace_id == ctx.workspace_id, Tag.name == payload.tag)
        ).scalar_one_or_none()
        if tag_obj is None:
            tag_obj = Tag(workspace_id=ctx.workspace_id, name=payload.tag)
            db.add(tag_obj)
            db.flush()

    for lead in leads:
        if payload.action == "delete":
            db.delete(lead)
        elif payload.action == "set_status" and payload.status:
            lead.status = payload.status
        elif payload.action == "add_tag" and tag_obj:
            exists = db.get(LeadTag, {"lead_id": lead.id, "tag_id": tag_obj.id})
            if not exists:
                db.add(LeadTag(lead_id=lead.id, tag_id=tag_obj.id))
        elif payload.action == "suppress" and lead.email:
            add_suppression(db, ctx.workspace_id, "email", lead.email,
                            SuppressionReason.manual, note="bulk suppress")
        affected += 1

    audit.record(db, action=AuditAction.update, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="lead",
                 data={"bulk": payload.action, "count": affected})
    db.commit()
    return BulkActionResponse(affected=affected)


@router.get("/duplicates/all", response_model=list[DuplicateGroup])
def list_duplicates(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[DuplicateGroup]:
    leads = db.execute(
        select(Lead).where(Lead.workspace_id == ctx.workspace_id)
    ).scalars().all()
    groups = dedup.find_duplicate_groups(leads)
    return [DuplicateGroup(**g) for g in groups]


@router.post("/merge", response_model=LeadOut)
def merge_leads(
    payload: MergeRequest,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> LeadOut:
    primary = _get_owned_lead(db, ctx.workspace_id, payload.primary_id)
    dups = [_get_owned_lead(db, ctx.workspace_id, did) for did in payload.duplicate_ids]

    fields = ["first_name", "last_name", "title", "email", "phone", "linkedin_url",
              "location", "company_id", "notes", "full_name"]
    for dup in dups:
        for f in fields:
            merged = dedup.merge_field_values(getattr(primary, f), getattr(dup, f))
            setattr(primary, f, merged)
        db.delete(dup)

    db.flush()
    audit.record(db, action=AuditAction.merge, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="lead", entity_id=primary.id,
                 data={"merged_ids": payload.duplicate_ids})
    db.commit()
    db.refresh(primary)
    return LeadOut.model_validate(primary)
