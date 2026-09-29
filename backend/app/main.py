from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.app.api.v1 import router as api_v1_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
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


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}
