"""Shared FastAPI dependencies: DB session, current user, workspace scoping, RBAC."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import WorkspaceRole
from app.models.user import User, WorkspaceMember

_bearer = HTTPBearer(auto_error=False)

# Role hierarchy for RBAC checks (higher index = more privilege).
_ROLE_ORDER = {
    WorkspaceRole.viewer: 0,
    WorkspaceRole.sales: 1,
    WorkspaceRole.admin: 2,
    WorkspaceRole.owner: 3,
}


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = decode_access_token(creds.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


@dataclass
class WorkspaceContext:
    user: User
    workspace_id: str
    role: WorkspaceRole


def get_workspace_context(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
) -> WorkspaceContext:
    """Resolve the caller's active workspace + role. Every workspace-scoped query
    MUST filter on `ctx.workspace_id` — this is the tenant-isolation boundary."""
    memberships = db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
    ).scalars().all()
    if not memberships:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User has no workspace")

    if x_workspace_id:
        member = next((m for m in memberships if m.workspace_id == x_workspace_id), None)
        if member is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this workspace")
    else:
        member = memberships[0]  # default to first membership

    return WorkspaceContext(user=user, workspace_id=member.workspace_id, role=member.role)


def require_role(minimum: WorkspaceRole):
    """Dependency factory enforcing a minimum role in the active workspace."""

    def _checker(ctx: WorkspaceContext = Depends(get_workspace_context)) -> WorkspaceContext:
        if _ROLE_ORDER[ctx.role] < _ROLE_ORDER[minimum]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Requires {minimum.value} role or higher"
            )
        return ctx

    return _checker
