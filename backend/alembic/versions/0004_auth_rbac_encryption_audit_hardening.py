"""Phase 4: RBAC seed data, per-tenant data encryption keys, an append-only
audit_log trigger, and a restricted application database role.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = [
    (
        "platform_admin",
        "Platform Administrator",
        "Manages tenants, plans, global config, LLM settings",
    ),
    (
        "tenant_admin",
        "Tenant Administrator",
        "Manages tenant users and thresholds, views tenant analytics",
    ),
    ("compliance_analyst", "Compliance Analyst (L1)", "Works the Review queue"),
    (
        "senior_reviewer",
        "Senior Reviewer (L2 / MLRO)",
        "Works the High Risk queue, decides and second-approves",
    ),
    ("auditor", "Auditor", "Read-only access to cases, audit log and reports"),
    ("customer", "Customer", "Submits and tracks their own application"),
]

PERMISSIONS = [
    ("tenants:manage", "Create, update, suspend tenants"),
    ("plans:manage", "Manage billing plans"),
    ("config:manage", "Manage global platform configuration"),
    ("llm:manage", "Manage LLM provider settings and quotas"),
    ("revenue:view", "View platform revenue analytics"),
    ("users:manage", "Manage users within a tenant"),
    ("risk_config:manage_tenant", "Adjust risk thresholds within allowed bounds"),
    ("analytics:view_tenant", "View tenant-scoped operational analytics"),
    ("cases:work_review", "Work cases in the Review (L1) queue"),
    ("cases:work_high_risk", "Work cases in the High Risk (L2) queue"),
    ("cases:note", "Add notes to a case"),
    ("cases:clear", "Clear a false-positive hit"),
    ("cases:escalate", "Escalate a case to High Risk"),
    ("cases:request_info", "Request information from the applicant (RFI)"),
    ("cases:decide", "Approve or reject a case"),
    ("cases:approve_second", "Provide the second approval on a dual-approval decision"),
    ("cases:read", "Read case details"),
    ("audit:read", "Read the audit log"),
    ("reports:read", "Read compliance and operational reports"),
    ("applications:submit_own", "Submit one's own application"),
    ("applications:view_own", "View the status of one's own application"),
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "platform_admin": [
        "tenants:manage",
        "plans:manage",
        "config:manage",
        "llm:manage",
        "revenue:view",
        "users:manage",
        "risk_config:manage_tenant",
        "analytics:view_tenant",
        "cases:read",
        "audit:read",
        "reports:read",
    ],
    "tenant_admin": [
        "users:manage",
        "risk_config:manage_tenant",
        "analytics:view_tenant",
        "cases:read",
    ],
    "compliance_analyst": [
        "cases:work_review",
        "cases:note",
        "cases:clear",
        "cases:escalate",
        "cases:request_info",
        "cases:read",
    ],
    "senior_reviewer": [
        "cases:work_high_risk",
        "cases:decide",
        "cases:approve_second",
        "cases:note",
        "cases:escalate",
        "cases:request_info",
        "cases:read",
    ],
    "auditor": ["cases:read", "audit:read", "reports:read"],
    "customer": ["applications:submit_own", "applications:view_own"],
}

APP_ROLE = "sentinelkyc_app"

# Tables the app role gets ordinary read/write on. audit_log is granted
# separately, INSERT/SELECT only, per PROJECT_PLAN.md Phase 4.4.
FULL_ACCESS_TABLES = [
    "tenants",
    "plans",
    "subscriptions",
    "invoices",
    "invoice_lines",
    "usage_events",
    "roles",
    "permissions",
    "role_permissions",
    "users",
    "user_roles",
    "refresh_tokens",
    "mfa_factors",
    "login_events",
    "customers",
    "applications",
    "documents",
    "document_checks",
    "screening_runs",
    "screening_hits",
    "cases",
    "case_events",
    "case_notes",
    "rfi_requests",
    "risk_config",
    "country_risk",
    "llm_calls",
    "llm_cache",
    "data_encryption_keys",
    "sanctions_list_versions",
    "sanctions_entities",
    "sanctions_names",
    "sanctions_identifiers",
    "sanctions_dobs",
    "sanctions_nationalities",
    "sanctions_addresses",
    "sanctions_changes",
    "sanctions_token_stats",
]


def upgrade() -> None:
    # --- Per-tenant data encryption keys ---
    op.create_table(
        "data_encryption_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("encrypted_dek", sa.LargeBinary(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "key_version", name="uq_data_encryption_keys_tenant_version"
        ),
    )

    # --- RBAC seed data ---
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        roles_table,
        [{"code": code, "name": name, "description": desc} for code, name, desc in ROLES],
    )

    permissions_table = sa.table(
        "permissions",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String()),
        sa.column("description", sa.Text()),
    )
    op.bulk_insert(
        permissions_table,
        [{"code": code, "description": desc} for code, desc in PERMISSIONS],
    )

    connection = op.get_bind()
    role_ids = dict(connection.execute(sa.text("SELECT code, id FROM roles")).fetchall())
    permission_ids = dict(
        connection.execute(sa.text("SELECT code, id FROM permissions")).fetchall()
    )

    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Integer()),
        sa.column("permission_id", sa.Integer()),
    )
    rows = [
        {"role_id": role_ids[role_code], "permission_id": permission_ids[perm_code]}
        for role_code, perm_codes in ROLE_PERMISSIONS.items()
        for perm_code in perm_codes
    ]
    op.bulk_insert(role_permissions_table, rows)

    # --- Append-only audit_log: block UPDATE and DELETE with a trigger ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_log_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_append_only
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();
        """
    )

    # --- Restricted application database role ---
    # The DO block body is an opaque string to Postgres's top-level parser, so
    # a bind parameter cannot be threaded into it; interpolating the password
    # directly is safe here only because it is our own generated secret
    # (token_urlsafe output), validated below to contain no quote character.
    app_db_password = _app_db_password()
    if "'" in app_db_password or "\\" in app_db_password:
        raise RuntimeError("APP_DB_PASSWORD must not contain a quote or backslash character")

    op.execute(
        f"""
        DO $do$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{app_db_password}'
                    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            ELSE
                ALTER ROLE {APP_ROLE} PASSWORD '{app_db_password}';
            END IF;
        END $do$;
        """
    )

    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )

    for table in FULL_ACCESS_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")

    # audit_log: INSERT and SELECT only, never UPDATE/DELETE (the trigger
    # above blocks it regardless, but the role grant is the first line of
    # defense and documents the intent at the privilege level too).
    op.execute(f"GRANT SELECT, INSERT ON audit_log TO {APP_ROLE}")

    # refresh_tokens is looked up by an opaque, unguessable token hash, not
    # by a known tenant: the token itself is the authorization proof (same
    # reasoning as the users table during login, which is looked up before
    # tenant context can be established from anything else). Migration 0002
    # enabled tenant-isolation RLS on it along with every other tenant-owned
    # table; that default is wrong for this one table, so it is corrected
    # here rather than by editing the already-shipped 0002.
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON refresh_tokens")
    op.execute("ALTER TABLE refresh_tokens DISABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE refresh_tokens FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON refresh_tokens "
        "USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true)::integer) "
        "WITH CHECK (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true)::integer)"
    )

    op.execute(f"REVOKE ALL ON audit_log FROM {APP_ROLE}")
    for table in FULL_ACCESS_TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    # ALTER DEFAULT PRIVILEGES writes a separate pg_default_acl entry that
    # outlives any REVOKE on existing objects; without reversing it too,
    # DROP ROLE fails with "cannot be dropped because some objects depend on
    # it" (found by running this migration's downgrade end to end, not by
    # inspection).
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")

    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_log_mutation()")

    op.execute("DELETE FROM role_permissions")
    op.execute("DELETE FROM permissions")
    op.execute("DELETE FROM roles")

    op.drop_table("data_encryption_keys")


def _app_db_password() -> str:
    from backend.app.core.config import get_settings

    password = get_settings().app_db_password
    if not password:
        raise RuntimeError(
            "APP_DB_PASSWORD must be set (in .env or the environment) before running this migration"
        )
    return password
