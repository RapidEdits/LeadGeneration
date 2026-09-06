from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import WorkspaceRole


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    full_name: str | None = Field(default=None, max_length=255)
    workspace_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class WorkspaceOut(BaseModel):
    id: str
    name: str
    slug: str
    role: WorkspaceRole

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    workspace: WorkspaceOut
