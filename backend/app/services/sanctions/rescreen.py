"""Integration point between sanctions list deltas and customer rescreening.

Dispatches rescreening for customers whose stored screening results may be affected
by changed sanctions entities. The Celery task and customer lookup this calls into
are introduced in Phase 5 (onboarding and case management), once the `customers`
table exists; until then there is nothing to rescreen.
"""

from __future__ import annotations


def enqueue_customer_rescreen(changed_entity_uids: list[int]) -> int:
    """Return the number of customers enqueued for rescreening against the given entities."""
    return 0
