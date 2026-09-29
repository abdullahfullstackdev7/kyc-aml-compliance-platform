"""RBAC (role -> permission, seeded in migration 0004) and ABAC rules that
need more than a role check: same-tenant scoping, the four-eyes principle,
and case-assignment ownership.

See PROJECT_PLAN.md Phase 4.2.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.identity import Permission, Role, RolePermission


class AuthorizationError(Exception):
    pass


@dataclass
class Principal:
    """The authenticated caller, resolved from a validated access token."""

    user_id: int
    tenant_id: int | None
    roles: list[str]


def role_has_permission(session: Session, role_code: str, permission_code: str) -> bool:
    result = session.execute(
        select(Permission.id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .where(Role.code == role_code, Permission.code == permission_code)
    ).first()
    return result is not None


def principal_has_permission(session: Session, principal: Principal, permission_code: str) -> bool:
    return any(role_has_permission(session, role, permission_code) for role in principal.roles)


def require_permission(permission_code: str):
    """FastAPI dependency factory: require_permission("cases:decide")."""
    from backend.app.api.deps import get_current_principal, get_db

    def dependency(
        principal: Principal = Depends(get_current_principal),
        db: Session = Depends(get_db),
    ) -> Principal:
        if not principal_has_permission(db, principal, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission_code}",
            )
        return principal

    return dependency


# --- ABAC rules ---


def check_same_tenant(principal: Principal, resource_tenant_id: int | None) -> None:
    if "platform_admin" in principal.roles:
        return
    if principal.tenant_id != resource_tenant_id:
        raise AuthorizationError("Resource belongs to a different tenant")


def check_four_eyes(first_approver_id: int, second_approver_id: int) -> None:
    if first_approver_id == second_approver_id:
        raise AuthorizationError("The first approver cannot also be the second approver")


def check_case_assignment(
    principal: Principal, assignee_id: int | None, *, is_reassigning: bool
) -> None:
    if is_reassigning:
        return
    if "platform_admin" in principal.roles or "tenant_admin" in principal.roles:
        return
    if assignee_id is not None and assignee_id != principal.user_id:
        raise AuthorizationError(
            "Only the assigned analyst can decide this case without reassigning it first"
        )
