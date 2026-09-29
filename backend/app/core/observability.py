"""Prometheus metrics and OpenTelemetry tracing (PROJECT_PLAN.md Phase
11.1). `instrument_app` wires up request latency/count automatically
(prometheus-fastapi-instrumentator) plus the domain-specific metrics named
in the plan: screening latency, LLM calls and failovers, SLA breaches, and
ETL freshness. Tracing is opt-in: it only exports spans if
OTEL_EXPORTER_OTLP_ENDPOINT is set, since this environment has no
collector to send them to; FastAPI auto-instrumentation still runs either
way; a span exists but goes nowhere without a configured exporter.
"""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram

SCREENING_LATENCY_SECONDS = Histogram(
    "sentinelkyc_screening_latency_seconds",
    "Time to score and rank one screening query (candidate generation through composite scoring).",
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5, 10),
)

LLM_CALLS_TOTAL = Counter(
    "sentinelkyc_llm_calls_total",
    "LLM calls by provider and outcome.",
    labelnames=("provider", "status"),
)

LLM_FAILOVERS_TOTAL = Counter(
    "sentinelkyc_llm_failovers_total",
    "Times the router failed over from the primary LLM provider to the secondary.",
)


_metrics_session_factory = None


def _sync_session():
    global _metrics_session_factory
    if _metrics_session_factory is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from backend.app.core.config import get_settings

        engine = create_engine(get_settings().sync_database_url(), pool_pre_ping=True)
        _metrics_session_factory = sessionmaker(bind=engine)
    return _metrics_session_factory()


def instrument_app(app: FastAPI) -> None:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    _register_live_gauges()
    _maybe_configure_tracing(app)


def _register_live_gauges() -> None:
    """Gauges backed by a live query at scrape time, not an in-process
    counter, since queue depth and ETL freshness are properties of the
    database's current state rather than events this process observed."""

    def _queue_depth() -> float:
        from sqlalchemy import func, select

        from backend.app.models.cases import Case

        try:
            with _sync_session() as session:
                return float(
                    session.execute(
                        select(func.count(Case.id)).where(
                            Case.state.in_(("PENDING_L1", "PENDING_L2", "ESCALATED"))
                        )
                    ).scalar_one()
                )
        except Exception:  # noqa: BLE001 - a metrics scrape must never 500 the app
            return float("nan")

    def _etl_freshness_seconds() -> float:
        import datetime as dt

        from sqlalchemy import select

        from backend.app.models.sanctions import SanctionsListVersion

        try:
            with _sync_session() as session:
                last = session.execute(
                    select(SanctionsListVersion.fetched_at).order_by(
                        SanctionsListVersion.fetched_at.desc()
                    ).limit(1)
                ).scalar_one_or_none()
                if last is None:
                    return float("nan")
                if last.tzinfo is None:
                    last = last.replace(tzinfo=dt.UTC)
                return (dt.datetime.now(dt.UTC) - last).total_seconds()
        except Exception:  # noqa: BLE001 - a metrics scrape must never 500 the app
            return float("nan")

    Gauge(
        "sentinelkyc_review_queue_depth",
        "Open cases in PENDING_L1/PENDING_L2/ESCALATED right now.",
    ).set_function(_queue_depth)

    Gauge(
        "sentinelkyc_etl_freshness_seconds",
        "Seconds since the most recent sanctions list version was ingested.",
    ).set_function(_etl_freshness_seconds)

    def _sla_breaches() -> float:
        from backend.app.services.analytics.queries import sla_compliance

        try:
            with _sync_session() as session:
                return float(sla_compliance(session)["breached"])
        except Exception:  # noqa: BLE001 - a metrics scrape must never 500 the app
            return float("nan")

    Gauge(
        "sentinelkyc_sla_breaches_current",
        "Open cases (Review/High Risk) currently past their SLA due date.",
    ).set_function(_sla_breaches)


def _maybe_configure_tracing(app: FastAPI) -> None:
    import os

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "sentinelkyc-api"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
