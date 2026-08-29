from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, SecretStr


class RegisterRequest(BaseModel):
    organization_slug: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    organization_slug: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, max_length=10)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"  # noqa: S105 — nom de schéma d'auth, pas un secret
    expires_in: int


class MeResponse(BaseModel):
    id: str
    email: str
    organization_id: str
    roles: list[str]


class StatusResponse(BaseModel):
    status: str
