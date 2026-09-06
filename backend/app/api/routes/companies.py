from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.enums import AuditAction, WorkspaceRole
from app.models.lead import Company, Lead
from app.schemas.company import CompanyCreate, CompanyOut, CompanyUpdate
from app.services import audit

router = APIRouter(prefix="/companies", tags=["companies"])


def _to_out(db: Session, company: Company) -> CompanyOut:
    count = db.execute(
        select(func.count()).select_from(Lead).where(Lead.company_id == company.id)
    ).scalar_one()
    out = CompanyOut.model_validate(company)
    out.lead_count = count
    return out


def _get_owned(db: Session, ws_id: str, company_id: str) -> Company:
    c = db.get(Company, company_id)
    if c is None or c.workspace_id != ws_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return c


@router.get("", response_model=list[CompanyOut])
def list_companies(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[CompanyOut]:
    stmt = select(Company).where(Company.workspace_id == ctx.workspace_id)
    if search:
        stmt = stmt.where(Company.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Company.name.asc()).offset(offset).limit(limit)
    return [_to_out(db, c) for c in db.execute(stmt).scalars().all()]


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> CompanyOut:
    company = Company(workspace_id=ctx.workspace_id, **payload.model_dump(exclude_unset=True))
    db.add(company)
    db.flush()
    audit.record(db, action=AuditAction.create, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="company", entity_id=company.id)
    db.commit()
    db.refresh(company)
    return _to_out(db, company)


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: str,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> CompanyOut:
    return _to_out(db, _get_owned(db, ctx.workspace_id, company_id))


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: str,
    payload: CompanyUpdate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> CompanyOut:
    company = _get_owned(db, ctx.workspace_id, company_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(company, k, v)
    db.flush()
    audit.record(db, action=AuditAction.update, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="company", entity_id=company.id)
    db.commit()
    db.refresh(company)
    return _to_out(db, company)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_company(
    company_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.admin)),
    db: Session = Depends(get_db),
) -> None:
    company = _get_owned(db, ctx.workspace_id, company_id)
    db.delete(company)
    audit.record(db, action=AuditAction.delete, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="company", entity_id=company_id)
    db.commit()
