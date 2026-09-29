from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.app.api.v1 import router as api_v1_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.core.observability import instrument_app
from backend.app.core.rate_limit import limiter
from backend.app.core.security_headers import SecurityHeadersMiddleware

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="SentinelKYC API",
    description="KYC/AML customer onboarding and sanctions screening platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
# slowapi's handler is typed for RateLimitExceeded specifically, narrower
# than Starlette's generic Exception handler signature; safe at runtime
# since FastAPI dispatches by the exact registered exception type.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(api_v1_router)
instrument_app(app)


@app.get("/health/live")
def health_live() -> dict[str, str]:
    """Process is up and serving requests. Never checks dependencies - a
    dependency outage should surface on /health/ready, not make the
    process look dead and get restarted needlessly."""
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, object]:
    """Process is up AND its dependencies (Postgres, Redis) are reachable.
    Used by an orchestrator/load balancer to decide whether to route
    traffic here, per PROJECT_PLAN.md Phase 11.1."""
    from fastapi import HTTPException, status
    from sqlalchemy import create_engine, text

    checks: dict[str, str] = {}

    try:
        engine = create_engine(settings.sync_database_url(), pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report the failure, don't crash the health check
        checks["postgres"] = f"unreachable: {exc}"

    try:
        import redis

        redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report the failure, don't crash the health check
        checks["redis"] = f"unreachable: {exc}"

    if any(v != "ok" for v in checks.values()):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, {"status": "not_ready", "checks": checks})

    return {"status": "ready", "checks": checks}
