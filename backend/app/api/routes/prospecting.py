"""Product brief → web discovery → reviewed leads → existing campaigns."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models.campaign import Campaign
from app.models.enums import AuditAction, CampaignState, Provenance, WorkspaceRole
from app.models.lead import Company, Lead, LeadSource
from app.models.user import Workspace
from app.schemas.prospecting import DiscoveryRequest, ImportProspects, ProductProfile, SearchCredentials
from app.services import audit, campaign_service, prospecting
from app.services.suppression import is_suppressed

router = APIRouter(prefix="/prospecting", tags=["prospecting"])
write_access = require_role(WorkspaceRole.sales)


def _owned_run(db, ws, run_id, lock=False):
    stmt = select(LeadSource).where(LeadSource.id == run_id, LeadSource.workspace_id == ws,
                                  LeadSource.kind == prospecting.RUN_KIND)
    source = db.scalar(stmt.with_for_update() if lock else stmt)
    if source is None:
        raise HTTPException(404, "Discovery run not found")
    return source


def _run_out(run):
    data = dict(run.meta or {})
    if data.get("status") in {"queued", "running"} and run.updated_at < datetime.now(timezone.utc) - timedelta(minutes=15):
        data.update(status="failed", error="Discovery worker stopped or did not start. Check the worker and start a new run.")
    return {"id": run.id, "created_at": run.created_at, **data}


@router.get("/profile")
def get_profile(ctx: WorkspaceContext = Depends(get_workspace_context), db: Session = Depends(get_db)):
    source = prospecting.profile_source(db, ctx.workspace_id)
    return {"profile": (source.meta or {}).get("profile") if source else None,
            "search_configured": bool(prospecting.search_key(source))}


@router.put("/profile")
def save_profile(payload: ProductProfile, ctx: WorkspaceContext = Depends(write_access), db: Session = Depends(get_db)):
    db.scalar(select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update())
    source = prospecting.profile_source(db, ctx.workspace_id)
    if source is None:
        source = LeadSource(workspace_id=ctx.workspace_id, kind=prospecting.PROFILE_KIND, name=payload.name, meta={})
        db.add(source)
    source.name = payload.name
    source.meta = {**(source.meta or {}), "profile": payload.model_dump(mode="json")}
    audit.record(db, action=AuditAction.update, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="product_profile", entity_id=source.id)
    db.commit()
    return get_profile(ctx, db)


@router.put("/search-key", status_code=204)
def save_key(payload: SearchCredentials, ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin)),
             db: Session = Depends(get_db)):
    db.scalar(select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update())
    source = prospecting.profile_source(db, ctx.workspace_id)
    if source is None:
        raise HTTPException(400, "Save your product profile first")
    source.meta = {**(source.meta or {}), "search_key": encrypt_secret(payload.api_key.strip())}
    db.commit()


@router.get("/runs")
def list_runs(ctx: WorkspaceContext = Depends(get_workspace_context), db: Session = Depends(get_db)):
    rows = db.scalars(select(LeadSource).where(LeadSource.workspace_id == ctx.workspace_id,
        LeadSource.kind == prospecting.RUN_KIND).order_by(LeadSource.created_at.desc()).limit(30)).all()
    return [_run_out(r) for r in rows]


@router.get("/runs/{run_id}")
def get_run(run_id: str, ctx: WorkspaceContext = Depends(get_workspace_context), db: Session = Depends(get_db)):
    return _run_out(_owned_run(db, ctx.workspace_id, run_id))


@router.post("/runs", status_code=202)
def start_run(payload: DiscoveryRequest, ctx: WorkspaceContext = Depends(write_access), db: Session = Depends(get_db)):
    db.scalar(select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update())
    source = prospecting.profile_source(db, ctx.workspace_id)
    if source is None or not (source.meta or {}).get("profile"):
        raise HTTPException(400, "Save your product profile first")
    if payload.mode == "search" and not prospecting.search_key(source):
        raise HTTPException(400, "Configure a Brave Search API key or choose supplied websites")
    pending = db.scalars(select(LeadSource).where(LeadSource.workspace_id == ctx.workspace_id,
        LeadSource.kind == prospecting.RUN_KIND, LeadSource.updated_at >= datetime.now(timezone.utc) - timedelta(minutes=15))).all()
    if any(r.meta.get("status") in {"queued", "running"} for r in pending):
        raise HTTPException(409, "A discovery run is already in progress")
    run = LeadSource(workspace_id=ctx.workspace_id, kind=prospecting.RUN_KIND, name=source.name,
        meta={"profile": source.meta["profile"], "mode": payload.mode,
              "websites": [str(u) for u in payload.websites], "status": "queued", "candidates": [],
              "warnings": [], "queries": [], "sites_total": 0, "sites_scanned": 0, "filtered": 0, "error": None})
    db.add(run)
    db.commit()
    db.refresh(run)
    try:
        from app.worker.tasks import discover_prospects
        discover_prospects.apply_async(args=[run.id], retry=False)
    except Exception:
        run.meta = {**run.meta, "status": "failed", "error": "Discovery queue unavailable; start Redis and the worker, then retry"}
        db.commit()
        raise HTTPException(503, run.meta["error"])
    return _run_out(run)


@router.post("/runs/{run_id}/import")
def import_candidates(run_id: str, payload: ImportProspects, ctx: WorkspaceContext = Depends(write_access),
                      db: Session = Depends(get_db)):
    # Serialize imports in a workspace so independent runs cannot duplicate an email.
    db.scalar(select(Workspace).where(Workspace.id == ctx.workspace_id).with_for_update())
    run = _owned_run(db, ctx.workspace_id, run_id, lock=True)
    if run.meta.get("status") != "completed":
        raise HTTPException(409, "Wait for discovery to complete before importing")
    campaign = None
    if payload.campaign_id:
        campaign = db.scalar(select(Campaign).where(Campaign.id == payload.campaign_id,
            Campaign.workspace_id == ctx.workspace_id).with_for_update())
        if campaign is None:
            raise HTTPException(404, "Campaign not found")
        if campaign.state not in {CampaignState.draft, CampaignState.paused, CampaignState.scheduled}:
            raise HTTPException(409, "Choose a draft or paused campaign; review the sequence before launching")
    import copy
    meta = copy.deepcopy(run.meta)
    candidates = {c["id"]: c for c in meta["candidates"]}
    if any(cid not in candidates for cid in payload.candidate_ids):
        raise HTTPException(400, "Unknown prospect selection")
    ids, created, duplicates, suppressed = [], 0, 0, 0
    for cid in dict.fromkeys(payload.candidate_ids):
        candidate = candidates[cid]
        email = candidate["email"]
        if is_suppressed(db, ctx.workspace_id, "email", email):
            suppressed += 1
            continue
        from sqlalchemy import func
        lead = db.scalar(select(Lead).where(Lead.workspace_id == ctx.workspace_id, func.lower(Lead.email) == email.lower()))
        if lead is None:
            domain = urlsplit(candidate["website"]).hostname
            company = db.scalar(select(Company).where(Company.workspace_id == ctx.workspace_id, Company.domain == domain))
            if company is None:
                company = Company(workspace_id=ctx.workspace_id, name=candidate["company"][:255],
                    domain=domain, website=candidate["website"][:512], location=candidate["location"][:255])
                db.add(company)
                db.flush()
            lead = Lead(workspace_id=ctx.workspace_id, source_id=run.id, company_id=company.id,
                email=email, email_provenance=Provenance.observed, location=candidate["location"][:255],
                notes=f"Public business contact: {candidate['company']}. Source: {candidate['source_url']}",
                custom_fields={"discovery": candidate, "product_name": meta["profile"]["name"]})
            db.add(lead)
            db.flush()
            created += 1
        else:
            duplicates += 1
        ids.append(lead.id)
        candidate["lead_id"] = lead.id
    added = campaign_service.add_leads(db, campaign, ids) if campaign else 0
    run.meta = meta
    audit.record(db, action=AuditAction.create, workspace_id=ctx.workspace_id, actor_id=ctx.user.id,
        entity_type="discovery_import", entity_id=run.id,
        data={"created": created, "duplicates": duplicates, "suppressed": suppressed, "campaign_id": payload.campaign_id})
    db.commit()
    return {"created": created, "duplicates": duplicates, "suppressed": suppressed, "added": added, "lead_ids": ids}
