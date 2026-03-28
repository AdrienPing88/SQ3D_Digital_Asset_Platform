"""Auth request/response schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserResponse"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    org_name: Optional[str] = None


class UserResponse(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    display_name: str
    global_role: str
    avatar_url: Optional[str] = None
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
