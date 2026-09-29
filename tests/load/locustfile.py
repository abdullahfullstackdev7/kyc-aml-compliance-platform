"""Load scenario for the screening engine (PROJECT_PLAN.md Phase 10.6):
50 concurrent reviewers issuing ad-hoc searches, roughly 20 screenings per
second in aggregate. Targets POST /api/v1/screening/search directly (no
auth required on that endpoint currently - see docs/performance.md for the
finding that it should be permission-gated).

Usage:
    uv run locust -f tests/load/locustfile.py --host http://localhost:8000 \
        --users 50 --spawn-rate 10 --run-time 1m --headless \
        --csv docs/performance/locust
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task

# A mix of names that will and will not match anything in the SDN corpus,
# so candidate-generation cost (the expensive path) is exercised alongside
# the cheap short-circuit for obvious misses.
SAMPLE_NAMES = [
    "Mohammed Al-Rashid",
    "Vladimir Petrov",
    "Jane Smith",
    "Carlos Fernandez Garcia",
    "Ahmed Hassan Ibrahim",
    "Li Wei",
    "Olga Ivanova",
    "John Doe",
    "Ana Maria Rodriguez",
    "Yusuf Karimov",
]


class ReviewerUser(HttpUser):
    """Simulates a reviewer running ad-hoc screening searches, per the
    Phase 8.4 "ad-hoc single search" console feature."""

    wait_time = between(0.5, 2.0)

    @task
    def search(self):
        name = random.choice(SAMPLE_NAMES)
        self.client.post(
            "/api/v1/screening/search",
            json={"full_name": name, "top_n": 10},
            name="/api/v1/screening/search",
        )
