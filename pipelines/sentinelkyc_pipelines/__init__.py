import dagster as dg

from sentinelkyc_pipelines.assets import analytics, ofac
from sentinelkyc_pipelines.resources import defs_resources

defs = dg.Definitions(
    assets=[
        ofac.ofac_sdn_raw,
        ofac.ofac_sdn_parsed,
        ofac.sdn_normalized,
        ofac.sdn_embeddings,
        ofac.sdn_loaded,
        ofac.delta_rescreen,
        analytics.analytics_refresh,
    ],
    asset_checks=[
        ofac.check_unique_uid,
        ofac.check_no_null_primary_names,
        ofac.check_row_count_within_tolerance,
    ],
    jobs=[ofac.sdn_ingestion_job, analytics.analytics_refresh_job],
    schedules=[ofac.sdn_poll_schedule, analytics.analytics_nightly_schedule],
    sensors=[ofac.sdn_freshness_sensor],
    resources=defs_resources,
)
