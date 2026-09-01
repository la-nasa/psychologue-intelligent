from __future__ import annotations

from datetime import datetime
from typing import Literal

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


# --- Phase 3 : plateforme utilisateur ---

ConsentPurpose = Literal["CARE", "LEARNING", "AI_EXTERNAL", "VOICE", "ANALYTICS", "RESEARCH"]


class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaActivateRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class ConsentRequest(BaseModel):
    purpose: ConsentPurpose


class ConsentItem(BaseModel):
    purpose: str
    version: str
    granted_at: str
    revoked_at: str | None
    active: bool


class ProfileResponse(BaseModel):
    display_name: str
    about_me: str
    language: str
    onboarding_completed_at: str | None


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(max_length=100)
    about_me: str = Field(default="", max_length=2000)
    language: Literal["fr", "en"] = "fr"


class PreferencesResponse(BaseModel):
    tone: Literal["warm", "neutral", "direct"]
    response_length: Literal["short", "medium", "detailed"]
    question_frequency: Literal["low", "medium", "high"]
    directiveness: Literal["reflective", "balanced", "directive"]


class PreferencesUpdateRequest(PreferencesResponse):
    pass


class GoalCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)


class GoalProgressRequest(BaseModel):
    value: int = Field(ge=0, le=100)
    note: str = Field(default="", max_length=1000)


class GoalItem(BaseModel):
    id: str
    title: str
    description: str
    status: str
    progress: int


# --- Phase 8 : PHQ-9 ---


class Phq9SubmitRequest(BaseModel):
    answers: list[int] = Field(min_length=9, max_length=9)


class Phq9SubmitResponse(BaseModel):
    id: str
    instrument_version: str
    total_score: int
    item9_score: int
    severity_band: str
    alert_level: str | None
    alert_created: bool


class ReminderRequest(BaseModel):
    due_at: datetime


# --- Phase 10 : canaux de notification (admin) ---


class ChannelCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["email", "sms", "push", "log"]
    target: str = Field(min_length=1, max_length=200)


class ChannelItem(BaseModel):
    id: str
    name: str
    kind: str
    is_active: bool
    target_hint: str
