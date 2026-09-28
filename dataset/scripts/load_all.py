"""Apply database migrations and run the sanctions ingestion pipeline in-process.

Usage: uv run python dataset/scripts/load_all.py

This is the current scope of `make seed`. Synthetic tenant, customer, case and
document generation are introduced in later phases per PROJECT_PLAN.md section 5.3.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def run_migrations() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"],
        check=True,
        cwd=ROOT,
    )


def run_sanctions_ingestion() -> None:
    from dagster import DagsterInstance, materialize
    from sentinelkyc_pipelines.assets import ofac
    from sentinelkyc_pipelines.resources import defs_resources

    instance = DagsterInstance.get()
    result = materialize(
        [
            ofac.ofac_sdn_raw,
            ofac.ofac_sdn_parsed,
            ofac.sdn_normalized,
            ofac.sdn_embeddings,
            ofac.sdn_loaded,
            ofac.delta_rescreen,
        ],
        resources=defs_resources,
        instance=instance,
    )
    if not result.success:
        raise SystemExit("Sanctions ingestion pipeline failed")


def main() -> None:
    print("Applying migrations...")
    run_migrations()
    print("Running sanctions ingestion pipeline...")
    run_sanctions_ingestion()
    print("Done.")


if __name__ == "__main__":
    main()
