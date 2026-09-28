"""Import every model module so Base.metadata is fully populated for Alembic
autogenerate and for tests that create the schema directly."""

from backend.app.models import (  # noqa: F401
    cases,
    governance,
    identity,
    onboarding,
    sanctions,
    screening,
    tenancy,
)
