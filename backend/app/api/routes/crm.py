"""CRM endpoints (Phase 7): tasks/meetings, per-lead notes, a unified lead
timeline, and the pipeline (Kanban) board.

Everything is workspace-scoped. The pipeline reuses `Lead.status` as the stage —
moving a card is a normal `PATCH /leads/{id}` — so there's a single source of truth
for a lead's stage across the table, pipeline, and outreach engine.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_workspace_context, require_role
from app.db.session import get_db
from app.models.crm import LeadNote, Task
from app.models.enums import AuditAction, LeadStatus, MessageDirection, TaskStatus, WorkspaceRole
from app.models.lead import Company, Lead
from app.models.message import Message
from app.models.user import User
from app.schemas.crm import (
    NoteCreate,
    NoteOut,
    PipelineCard,
    PipelineResponse,
    PipelineStage,
    SimpleOk,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    TimelineItem,
)
from app.services import audit

router = APIRouter(prefix="/crm", tags=["crm"])

# Pipeline column order + labels (Lead.status is the stage).
_STAGES: list[tuple[LeadStatus, str]] = [
    (LeadStatus.new, "New"),
    (LeadStatus.enriched, "Enriched"),
    (LeadStatus.qualified, "Qualified"),
    (LeadStatus.contacted, "Contacted"),
    (LeadStatus.replied, "Replied"),
    (LeadStatus.won, "Won"),
    (LeadStatus.lost, "Lost"),
    (LeadStatus.disqualified, "Disqualified"),
]
_PIPELINE_CARD_LIMIT = 100


def _user_names(db: Session, ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.full_name, User.email).where(User.id.in_(ids))).all()
    return {uid: (name or email) for uid, name, email in rows}


def _owned_lead(db: Session, ws_id: str, lead_id: str) -> Lead:
    lead = db.get(Lead, lead_id)
    if lead is None or lead.workspace_id != ws_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")
    return lead


# ---- Tasks ----

def _task_out(t: Task, lead_names: dict[str, str], user_names: dict[str, str]) -> TaskOut:
    out = TaskOut.model_validate(t)
    out.lead_name = lead_names.get(t.lead_id) if t.lead_id else None
    out.assignee_name = user_names.get(t.assignee_id) if t.assignee_id else None
    return out


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    scope: str = Query("open", pattern="^(open|overdue|today|upcoming|done|all)$"),
    lead_id: str | None = None,
    assignee_id: str | None = None,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[TaskOut]:
    now = datetime.now(timezone.utc)
    stmt = select(Task).where(Task.workspace_id == ctx.workspace_id)
    if lead_id:
        stmt = stmt.where(Task.lead_id == lead_id)
    if assignee_id:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if scope == "open":
        stmt = stmt.where(Task.status == TaskStatus.open)
    elif scope == "done":
        stmt = stmt.where(Task.status == TaskStatus.done)
    elif scope == "overdue":
        stmt = stmt.where(Task.status == TaskStatus.open, Task.due_at.isnot(None), Task.due_at < now)
    elif scope == "today":
        end = now.replace(hour=23, minute=59, second=59)
        stmt = stmt.where(Task.status == TaskStatus.open, Task.due_at.isnot(None), Task.due_at <= end)
    elif scope == "upcoming":
        stmt = stmt.where(Task.status == TaskStatus.open, Task.due_at.isnot(None), Task.due_at >= now)
    # scope == "all": no status filter

    # Open tasks first by soonest due; completed by most recent.
    stmt = stmt.order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.desc()).limit(500)
    tasks = db.execute(stmt).scalars().all()

    lead_ids = {t.lead_id for t in tasks if t.lead_id}
    lead_names = dict(db.execute(
        select(Lead.id, Lead.full_name).where(Lead.id.in_(lead_ids))
    ).all()) if lead_ids else {}
    user_names = _user_names(db, {t.assignee_id for t in tasks})
    return [_task_out(t, lead_names, user_names) for t in tasks]


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> TaskOut:
    if payload.lead_id:
        _owned_lead(db, ctx.workspace_id, payload.lead_id)
    task = Task(
        workspace_id=ctx.workspace_id,
        lead_id=payload.lead_id,
        created_by=ctx.user.id,
        assignee_id=payload.assignee_id or ctx.user.id,
        type=payload.type,
        title=payload.title,
        description=payload.description,
        due_at=payload.due_at,
    )
    db.add(task)
    audit.record(db, action=AuditAction.create, workspace_id=ctx.workspace_id, actor_id=ctx.user.id,
                 entity_type="task", entity_id=task.id, data={"type": payload.type.value})
    db.commit()
    db.refresh(task)
    lead_names = {task.lead_id: _owned_lead(db, ctx.workspace_id, task.lead_id).full_name} if task.lead_id else {}
    return _task_out(task, lead_names, _user_names(db, {task.assignee_id}))


def _owned_task(db: Session, ws_id: str, task_id: str) -> Task:
    t = db.get(Task, task_id)
    if t is None or t.workspace_id != ws_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    return t


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> TaskOut:
    t = _owned_task(db, ctx.workspace_id, task_id)
    data = payload.model_dump(exclude_unset=True)
    for field in ("title", "type", "description", "due_at", "assignee_id"):
        if field in data:
            setattr(t, field, data[field])
    if "status" in data and data["status"] is not None:
        t.status = data["status"]
        t.completed_at = datetime.now(timezone.utc) if t.status == TaskStatus.done else None
    db.commit()
    db.refresh(t)
    lead_names = dict(db.execute(select(Lead.id, Lead.full_name).where(Lead.id == t.lead_id)).all()) if t.lead_id else {}
    return _task_out(t, lead_names, _user_names(db, {t.assignee_id}))


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete_task(
    task_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> TaskOut:
    t = _owned_task(db, ctx.workspace_id, task_id)
    t.status = TaskStatus.done
    t.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(t)
    lead_names = dict(db.execute(select(Lead.id, Lead.full_name).where(Lead.id == t.lead_id)).all()) if t.lead_id else {}
    return _task_out(t, lead_names, _user_names(db, {t.assignee_id}))


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_task(
    task_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> None:
    t = _owned_task(db, ctx.workspace_id, task_id)
    db.delete(t)
    db.commit()


# ---- Notes ----

@router.get("/leads/{lead_id}/notes", response_model=list[NoteOut])
def list_notes(
    lead_id: str,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[NoteOut]:
    _owned_lead(db, ctx.workspace_id, lead_id)
    notes = db.execute(
        select(LeadNote).where(LeadNote.lead_id == lead_id).order_by(LeadNote.created_at.desc())
    ).scalars().all()
    names = _user_names(db, {n.author_id for n in notes})
    out = []
    for n in notes:
        item = NoteOut.model_validate(n)
        item.author_name = names.get(n.author_id) if n.author_id else None
        out.append(item)
    return out


@router.post("/leads/{lead_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_note(
    lead_id: str,
    payload: NoteCreate,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> NoteOut:
    _owned_lead(db, ctx.workspace_id, lead_id)
    note = LeadNote(workspace_id=ctx.workspace_id, lead_id=lead_id, author_id=ctx.user.id, body=payload.body)
    db.add(note)
    db.commit()
    db.refresh(note)
    out = NoteOut.model_validate(note)
    out.author_name = ctx.user.full_name or ctx.user.email
    return out


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_note(
    note_id: str,
    ctx: WorkspaceContext = Depends(require_role(WorkspaceRole.sales)),
    db: Session = Depends(get_db),
) -> None:
    note = db.get(LeadNote, note_id)
    if note is None or note.workspace_id != ctx.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    db.delete(note)
    db.commit()


# ---- Unified timeline ----

@router.get("/leads/{lead_id}/timeline", response_model=list[TimelineItem])
def lead_timeline(
    lead_id: str,
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> list[TimelineItem]:
    """Messages + notes + tasks for a lead, newest first — the detail-drawer feed."""
    _owned_lead(db, ctx.workspace_id, lead_id)
    items: list[TimelineItem] = []

    messages = db.execute(
        select(Message).where(Message.lead_id == lead_id).order_by(Message.created_at.desc()).limit(200)
    ).scalars().all()
    for m in messages:
        items.append(TimelineItem(
            kind="message", id=m.id, at=m.created_at,
            title=m.subject or f"{m.channel.value} {m.direction.value}",
            body=m.body, channel=m.channel.value, direction=m.direction.value,
            status=m.status.value, meta=m.meta,
        ))

    notes = db.execute(
        select(LeadNote).where(LeadNote.lead_id == lead_id).order_by(LeadNote.created_at.desc()).limit(200)
    ).scalars().all()
    author_names = _user_names(db, {n.author_id for n in notes})
    for n in notes:
        items.append(TimelineItem(
            kind="note", id=n.id, at=n.created_at, body=n.body,
            actor=author_names.get(n.author_id) if n.author_id else None,
        ))

    tasks = db.execute(
        select(Task).where(Task.lead_id == lead_id).order_by(Task.created_at.desc()).limit(200)
    ).scalars().all()
    for t in tasks:
        items.append(TimelineItem(
            kind="task", id=t.id, at=t.created_at, title=t.title, body=t.description,
            status=t.status.value, channel=t.type.value,
            meta={"due_at": t.due_at.isoformat() if t.due_at else None},
        ))

    items.sort(key=lambda x: x.at, reverse=True)
    return items


# ---- Pipeline (Kanban) ----

@router.get("/pipeline", response_model=PipelineResponse)
def pipeline(
    ctx: WorkspaceContext = Depends(get_workspace_context),
    db: Session = Depends(get_db),
) -> PipelineResponse:
    # Per-stage total counts (all leads, not just the capped cards).
    counts = dict(db.execute(
        select(Lead.status, func.count()).where(Lead.workspace_id == ctx.workspace_id).group_by(Lead.status)
    ).all())

    # Open-task counts per lead, for the card badge.
    open_tasks = dict(db.execute(
        select(Task.lead_id, func.count()).where(
            Task.workspace_id == ctx.workspace_id, Task.status == TaskStatus.open, Task.lead_id.isnot(None)
        ).group_by(Task.lead_id)
    ).all())

    stages: list[PipelineStage] = []
    for st, label in _STAGES:
        rows = db.execute(
            select(Lead, Company.name).join(Company, Company.id == Lead.company_id, isouter=True)
            .where(Lead.workspace_id == ctx.workspace_id, Lead.status == st)
            .order_by(Lead.updated_at.desc()).limit(_PIPELINE_CARD_LIMIT)
        ).all()
        cards = [
            PipelineCard(
                id=lead.id, full_name=lead.full_name, title=lead.title, company_name=cname,
                email=lead.email, score=lead.score, status=lead.status, updated_at=lead.updated_at,
                open_tasks=open_tasks.get(lead.id, 0),
            )
            for lead, cname in rows
        ]
        stages.append(PipelineStage(status=st, label=label, count=counts.get(st, 0), cards=cards))
    return PipelineResponse(stages=stages)
