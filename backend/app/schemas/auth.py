from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_id: int | None = None


class LoginSuccessResponse(BaseModel):
    status: Literal["success"] = "success"
    access_token: str
    refresh_token: str
    user_id: int
    tenant_id: int | None
    roles: list[str]


class MfaRequiredResponse(BaseModel):
    status: Literal["mfa_required"] = "mfa_required"
    user_id: int


class MfaVerifyRequest(BaseModel):
    user_id: int
    code: str
    tenant_id: int | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class PasswordResetRequestRequest(BaseModel):
    email: EmailStr
    tenant_id: int | None = None


class PasswordResetRequestResponse(BaseModel):
    detail: str
    reset_token: str | None = None  # only populated outside production, for testing


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=12)


class MfaEnrollStartResponse(BaseModel):
    factor_id: int
    provisioning_uri: str
    recovery_codes: list[str]


class MfaEnrollConfirmRequest(BaseModel):
    code: str
