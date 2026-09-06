from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_current_user, get_workspace_context
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.enums import AuditAction, WorkspaceRole
from app.models.user import User, Workspace, WorkspaceMember
from app.schemas.auth import (
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
    WorkspaceOut,
)
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return base[:100]


def _unique_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug, i = base, 1
    while db.execute(select(Workspace.id).where(Workspace.slug == slug)).first():
        i += 1
        slug = f"{base}-{i}"
    return slug


def _token_response(db: Session, user: User, member: WorkspaceMember) -> TokenResponse:
    ws = db.get(Workspace, member.workspace_id)
    token = create_access_token(user.id, extra={"ws": member.workspace_id})
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(user),
        workspace=WorkspaceOut(id=ws.id, name=ws.name, slug=ws.slug, role=member.role),
    )


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.flush()

    ws = Workspace(name=payload.workspace_name, slug=_unique_slug(db, payload.workspace_name))
    db.add(ws)
    db.flush()

    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.owner)
    db.add(member)
    db.flush()

    audit.record(db, action=AuditAction.signup, workspace_id=ws.id, actor_id=user.id,
                 entity_type="user", entity_id=user.id)
    db.commit()
    db.refresh(user)
    return _token_response(db, user, member)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.execute(
        select(User).where(func.lower(User.email) == payload.email.lower())
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    member = db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
    ).scalars().first()
    if not member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no workspace")

    audit.record(db, action=AuditAction.login, workspace_id=member.workspace_id, actor_id=user.id)
    db.commit()
    return _token_response(db, user, member)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/workspaces", response_model=list[WorkspaceOut])
def my_workspaces(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[WorkspaceOut]:
    members = db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
    ).scalars().all()
    out: list[WorkspaceOut] = []
    for m in members:
        ws = db.get(Workspace, m.workspace_id)
        out.append(WorkspaceOut(id=ws.id, name=ws.name, slug=ws.slug, role=m.role))
    return out
