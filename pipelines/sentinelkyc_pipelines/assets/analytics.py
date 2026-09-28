import dagster as dg
from dagster import AssetExecutionContext
from sqlalchemy import text

from sentinelkyc_pipelines.resources import DatabaseResource


@dg.asset(group_name="analytics", required_resource_keys={"db"})
def analytics_refresh(context: AssetExecutionContext) -> dict:
    """Refresh every materialized view registered by the analytics domain (Phase 9).

    No materialized views exist until Phase 9 introduces them; this asset is a real,
    working refresh routine that currently has nothing to do.
    """
    db: DatabaseResource = context.resources.db
    with db.session() as session:
        views: list[str] = list(
            session.execute(
                text("SELECT matviewname FROM pg_matviews WHERE matviewname LIKE 'mv_%'")
            ).scalars()
        )
        for view_name in views:
            session.execute(text(f'REFRESH MATERIALIZED VIEW CONCURRENTLY "{view_name}"'))

    context.log.info(f"Refreshed {len(views)} materialized view(s)")
    return {"refreshed": views}


analytics_refresh_job = dg.define_asset_job(
    "analytics_refresh_job", selection=dg.AssetSelection.assets(analytics_refresh)
)

analytics_nightly_schedule = dg.ScheduleDefinition(
    name="analytics_nightly_schedule",
    job=analytics_refresh_job,
    cron_schedule="0 2 * * *",
)
