"""Manually fetch the OFAC SDN export outside of the Dagster schedule.

Usage: uv run python dataset/scripts/download_ofac.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.config import get_settings
from backend.app.services.sanctions.fetcher import fetch_with_conditional_get
from backend.app.services.sanctions.ofac_parser import parse_publish_info


def main() -> None:
    settings = get_settings()
    result = fetch_with_conditional_get(
        settings.ofac_sdn_url,
        previous_etag=None,
        previous_last_modified=None,
        previous_sha256=None,
    )
    if result.status != "fetched" or result.body is None:
        print(f"No new content fetched (status={result.status})")
        return

    directory = Path(settings.dataset_raw_dir) / "ofac" / "sdn"
    directory.mkdir(parents=True, exist_ok=True)
    tmp_path = directory / f"_tmp_{result.sha256[:12]}.xml"
    tmp_path.write_bytes(result.body)

    info = parse_publish_info(tmp_path)
    publish_date_str = info.publish_date.isoformat() if info.publish_date else "unknown-date"
    final_path = directory / f"{publish_date_str}_{result.sha256[:8]}.xml"
    tmp_path.replace(final_path)

    print(
        f"Saved {final_path} ({info.record_count} declared records, publish date {publish_date_str})"
    )


if __name__ == "__main__":
    main()
