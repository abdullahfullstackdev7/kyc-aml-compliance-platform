"""Conditional-GET fetcher for OFAC sanctions list exports.

Uses ETag / Last-Modified for a cheap 304 short-circuit, and falls back to a
SHA-256 body comparison because the publisher does not always honor conditional
headers reliably. See PROJECT_PLAN.md section 5.1 and Phase 1, asset `ofac_sdn_raw`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import httpx

_TIMEOUT = httpx.Timeout(180.0, connect=60.0)


@dataclass
class FetchResult:
    status: str  # "not_modified" | "unchanged" | "fetched"
    body: bytes | None
    sha256: str | None
    etag: str | None
    last_modified: str | None


def fetch_with_conditional_get(
    url: str,
    *,
    previous_etag: str | None,
    previous_last_modified: str | None,
    previous_sha256: str | None,
) -> FetchResult:
    headers = {}
    if previous_etag:
        headers["If-None-Match"] = previous_etag
    if previous_last_modified:
        headers["If-Modified-Since"] = previous_last_modified

    with httpx.Client(follow_redirects=True, timeout=_TIMEOUT) as client:
        response = client.get(url, headers=headers)

    if response.status_code == 304:
        return FetchResult(
            status="not_modified",
            body=None,
            sha256=previous_sha256,
            etag=previous_etag,
            last_modified=previous_last_modified,
        )

    response.raise_for_status()
    body = response.content
    sha256 = hashlib.sha256(body).hexdigest()
    etag = response.headers.get("etag")
    last_modified = response.headers.get("last-modified")

    if previous_sha256 and sha256 == previous_sha256:
        return FetchResult(
            status="unchanged", body=None, sha256=sha256, etag=etag, last_modified=last_modified
        )

    return FetchResult(
        status="fetched", body=body, sha256=sha256, etag=etag, last_modified=last_modified
    )


def save_raw_file(body: bytes, directory: str | Path, publish_date_str: str, sha256: str) -> str:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    file_path = directory / f"{publish_date_str}_{sha256[:8]}.xml"
    file_path.write_bytes(body)
    return str(file_path)
