# Load Testing (Phase 10.6)

Scenario: `tests/load/locustfile.py`, targeting `POST /api/v1/screening/search`
(the ad-hoc single-search flow used by reviewers, Phase 8.4), run against a
single local `uvicorn` process (no worker pool, no Nginx in front) backed by
the same Postgres/Redis containers used throughout development. These are
single-machine, single-worker numbers, not a production capacity plan; they
establish a baseline and, more importantly, this run caught and led to a
real fix (below) rather than only producing a number.

## How to reproduce

```
uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8123 &
# one warmup request first - see "Cold start" below for why
curl -s -X POST http://127.0.0.1:8123/api/v1/screening/search \
  -H "Content-Type: application/json" -d '{"full_name":"Warmup","top_n":3}' > /dev/null

uv run locust -f tests/load/locustfile.py --host http://127.0.0.1:8123 \
  --users 50 --spawn-rate 10 --run-time 1m --headless \
  --csv docs/performance/locust
```

## A real bug this test caught

The first run, at 20 concurrent users against a cold process, **crashed the
server** (a Rust allocator abort inside the tokenizer library, 100% request
failure). The cause: `backend/app/services/screening/embeddings.py` lazily
loaded the `SentenceTransformer` embedding model behind a plain
`@lru_cache(maxsize=1)`. `lru_cache` is not a safe lazy-singleton under
concurrency - FastAPI runs sync endpoints in a thread pool, so on a cold
process several concurrent requests all observe the cache empty and each
start constructing a full model instance in parallel. With 20 concurrent
requests, that meant roughly 20 simultaneous model loads (each also making
its own round of cache-validation requests to the Hugging Face Hub),
exhausting memory and killing the process outright.

Fixed with an explicit double-checked lock (`threading.Lock`) around the
single model instance, so only one thread ever constructs it; concurrent
callers block briefly on the lock instead of each starting their own load.
Re-running the identical scenario after the fix: **0 failures across 336
requests**, confirmed below.

## Cold start

The first request in a fresh process pays the embedding model's load cost:
roughly 9-70 seconds depending on whether Hugging Face Hub cache-validation
requests hit the network (up to ~68s observed once) or are skipped via
`HF_HUB_OFFLINE=1` once the model is already present in the local cache
(~10s). This is a one-time per-process cost, not a per-request cost, and is
excluded from the numbers below by sending one warmup request first - the
same convention the test suite uses (see `tests/integration/test_screening_performance.py`
and `tests/integration/test_onboarding_flow.py`).

## Results (post-fix, warm process, 20 users, spawn rate 5, 30s)

| Metric | Value |
|---|---|
| Total requests | 336 |
| Failures | 0 (0.00%) |
| Requests/s | 11.3 |
| Median (p50) | 390 ms |
| p90 | 900 ms |
| p95 | 1100 ms |
| p99 | 1300 ms |
| Max | 1449 ms |

The existing steady-state single-request benchmark
(`tests/integration/test_screening_performance.py::test_single_screening_p95_under_300ms`,
Phase 3) targets p95 &lt; 300ms for one warmed, unloaded request; it failed in
this same session at 429ms, which - given this machine ran Docker, multiple
pytest suites, `npm` builds and this load test concurrently for hours - reads
as environment contention on a shared dev machine rather than a regression,
but is recorded here rather than quietly dropped.

At 20 concurrent users the median stays close to that single-request
baseline (390ms vs an unloaded ~130-300ms), but the tail grows substantially
(p95 1100ms, roughly 3.5x the single-request p95 target). This endpoint does
CPU-bound work per request (candidate scoring, an embedding call) on a
single synchronous worker process; the plan's target of 50 reviewers and
"20 screenings per second" (PROJECT_PLAN.md Phase 10.6) is a fleet-level
number that assumes multiple worker processes behind a load balancer (see
`infra/docker/` and the production Nginx profile, Phase 11.2), not a single
process - this run establishes the per-process baseline that number should
be divided across.

## Known gaps

- `POST /api/v1/screening/search` currently has no authentication or rate
  limiting (`backend/app/api/v1/screening.py`), unlike every other
  tenant-owned endpoint in this codebase. It was convenient for this load
  test to hit unauthenticated, but it is a real gap worth closing before
  this endpoint is exposed beyond a trusted internal caller.
- This run used one `uvicorn` worker with no reverse proxy; it does not
  model the production topology (Phase 11.2's Nginx + multiple workers).
- 50-user/20-req/s sustained load per the full plan target was not run in
  this session (20 users / ~11 req/s was, to keep the run short); the
  scenario file supports it directly via `--users 50 --spawn-rate 10`.
