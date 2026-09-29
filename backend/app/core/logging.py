"""Structured logging with a PII-masking processor.

See PROJECT_PLAN.md Phase 4.3: PII masking in logs via a structlog processor;
no PII in URLs or query strings. Field names are masked by key, not by
guessing content, since a value-pattern guess (e.g. "looks like a name")
is unreliable and a known key name is not.
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

MASKED_FIELD_NAMES = {
    "password",
    "full_name",
    "dob",
    "date_of_birth",
    "id_number",
    "address",
    "email",
    "phone",
    "ssn",
    "passport_number",
    "national_id",
    "access_token",
    "refresh_token",
    "authorization",
    "mfa_code",
    "totp_code",
    "recovery_code",
    "secret",
    "password_hash",
}

MASK = "***"


def mask_pii(
    _logger: object, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        if key.casefold() in MASKED_FIELD_NAMES:
            event_dict[key] = MASK
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    logging.basicConfig(level=log_level, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            mask_pii,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(*args: object, **kwargs: object) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(*args, **kwargs)
