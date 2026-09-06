from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.enums import AuditAction, WorkspaceRole
from app.models.outreach import SuppressionEntry
from app.schemas.common import SuppressionCreate, SuppressionOut
from app.services import audit
from app.services.suppression import add_suppression

router = APIRouter(prefix="/suppression", tags=["suppression"])


@router.get("", response_model=list[SuppressionOut])
def list_suppression(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[SuppressionOut]:
    rows = db.execute(
        select(SuppressionEntry)
        .where(SuppressionEntry.workspace_id == ctx.workspace_id)
        .order_by(SuppressionEntry.created_at.desc())
    ).scalars().all()
    return [SuppressionOut.model_validate(r) for r in rows]


@router.post("", response_model=SuppressionOut, status_code=status.HTTP_201_CREATED)
def create_suppression(
    payload: SuppressionCreate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> SuppressionOut:
    entry = add_suppression(
        db, ctx.workspace_id, payload.channel, payload.value, payload.reason, payload.note
    )
    audit.record(db, action=AuditAction.suppress, workspace_id=ctx.workspace_id,
                 actor_id=ctx.user.id, entity_type="suppression",
                 entity_id=entry.id if entry else None, data={"value": payload.value})
    db.commit()
    db.refresh(entry)
    return SuppressionOut.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_suppression(
    entry_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> None:
    entry = db.get(SuppressionEntry, entry_id)
    if entry and entry.workspace_id == ctx.workspace_id:
        db.delete(entry)
        db.commit()
