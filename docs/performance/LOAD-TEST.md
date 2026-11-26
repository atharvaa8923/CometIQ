# CometIQ load test and hardening report

Measured on 2026-11-26 on a 4-core Linux container. The load generator, PostgreSQL 16 and the app shared those 4 cores,
so these numbers understate what a dedicated server would do.

## Setup

- **Data:** 1,500 students with transcripts and evidence, 400 job postings, 40 analyzed syllabi, plus the full demo catalog. Seeded by `backend/scripts/perf_profile.py`.
- **Server:** uvicorn on PostgreSQL. Job sync, retention and AI were off (built-in engine). Rate limits were off for the capacity runs.
- **Tool:** `backend/scripts/load_test.py`.
  - A closed loop with no think time, so it measures capacity, not a realistic arrival rate.
  - Each virtual user signs in as its own account. The mix is 60% students, 25% faculty and 15% employers.
  - Students load job matches, their plan, recommendations, badges, notifications and search. Faculty load syllabi, a gap report, the scorecard, the program map, the knowledge graph and the simulator. Employers load talent search, candidates and student search.
- **Run length:** 30 s per concurrency level.

To reproduce:

```bash
cd backend
DATABASE_URL=postgresql+psycopg://… python scripts/perf_profile.py --runs 1      # seed
RATE_LIMITS_ENABLED=false uvicorn app.main:app --port 8811 --workers 3 &
python scripts/load_test.py --base http://127.0.0.1:8811 --concurrency 20 50 --seconds 30
```

## Results

| Run | Users | Requests | Throughput | p50 | p95 | p99 | 5xx |
|---|---:|---:|---:|---:|---:|---:|---:|
| Before, 1 worker | 20 | 559 | 18.1 req/s | 863 ms | 2,596 ms | 3,622 ms | 0 |
| Before, 1 worker | 50 | 566 | 17.3 req/s | 2,583 ms | 5,198 ms | 6,249 ms | 0 |
| After code fixes, 1 worker | 20 | 1,145 | 37.5 req/s | 418 ms | 1,219 ms | 2,116 ms | 0 |
| After code fixes, 1 worker | 50 | 1,099 | 34.8 req/s | 1,315 ms | 2,731 ms | 3,521 ms | 0 |
| **After, 3 workers** | **20** | **3,169** | **104.7 req/s** | **136 ms** | **515 ms** | **767 ms** | **0** |
| **After, 3 workers** | **50** | **3,178** | **103.6 req/s** | **413 ms** | **1,024 ms** | **1,457 ms** | **0** |
| After, 3 workers, rate limits on | 20 | 3,525 | 116.2 req/s | 122 ms | 464 ms | 710 ms | 0 (53 × 429) |

Throughput went up 5.8× (18 to 104 req/s). At 20 users, p95 fell from 2.6 s to 0.5 s. Not one request failed in any run.

From 20 to 50 users, throughput stays flat and latency grows. On these 4 shared cores, about 100 req/s is the ceiling. Beyond it, requests queue rather than fail.

Raw results are in `load-before.json` and `load-after-3-workers.json`.

## What changed

The fixes came from profiling the live server under load with `py-spy`.

| Hotspot (share of server CPU) | Fix |
|---|---|
| Student job list, 17%: rebuilt 400 postings and their skills as ORM objects on every request | `match.open_jobs()` caches a read-only index of open postings. It is rebuilt only when a posting or the organization's data changes. |
| Catalog graph, 11%: reloaded courses, prerequisites and course skills on every planning request | `path.load_graph()` is cached as plain data (`CourseInfo`) and invalidated the same way. |
| Syllabus list, 6%: loaded every analysis, with its full result JSON, to show the latest score | A single query for the latest analysis's columns per syllabus. |
| One process, so one core (Python GIL) | Several worker processes: uvicorn reads `WEB_CONCURRENCY`, and the Dockerfile defaults to 2. This is now safe because tasks are claimed with `FOR UPDATE SKIP LOCKED`, the nightly sync and retention use lock rows, and first-start seeding takes an advisory lock. Pool size per process is 8 + 12. Keep `workers × 20` below PostgreSQL `max_connections`. |

The earlier round removed N+1 queries and added cached views (see `perf_profile.py`). For example, ranking candidates went from 4,968 queries to 12.

## Rate limits

Expensive endpoints have a per-user budget per minute. Requests over the budget get 429 in the standard error format, with `Retry-After`. The limits are listed in `app/limits.py`:

- `/api/ask`: 20
- syllabus copilot: 30
- analyze: 20
- CometForge generate: 10
- AI explanation: 20
- simulator: 30
- what-if: 60
- scorecard, program map, candidates, talent search, knowledge graph: 60 each
- search: 120
- exports: 30

`RATE_LIMIT_MULTIPLIER` scales all of them, and `RATE_LIMITS_ENABLED=false` turns them off.

In the rate-limited run, every virtual employer shared one account. That account went over its talent-search and candidates budget (53 × 429), while students and faculty were unaffected.

The counters are kept in each process's memory, so with N workers a user can get up to N × the budget. For strict limits across several instances, move the counters to Redis.

## Hardening

**Property tests** (`tests/test_properties.py`, Hypothesis, 1,500 random cases per property):

- the gap score stays within 0–100;
- more mentions never lower the score;
- teaching every skill scores 100 and teaching none scores 0;
- the reviewed score and counts stay in range;
- the match fit stays within 0–100, and the bonus stays within its cap and equals the sum of its items;
- learning a skill never lowers fit;
- simulator coverage stays within 0–100;
- the semester-comparison parts add up to the total.

**Bug found:** the comparison rounded each part separately. With random inputs, the displayed parts did not add up to the displayed total in 25% of cases. `versions.attribute()` now rounds so that they always do.

**Concurrent decisions:** a partial unique index (migration 0007) allows one active decision per course and skill. The previous decision is locked and retired before the new one is inserted. When four threads decide at once, exactly one active decision remains, and the losers get 409. Tested on PostgreSQL and SQLite.

**Duplicate submissions:**
- The frontend sends an `Idempotency-Key` with every write. A repeat returns the stored first response, marked `Idempotent-Replayed: true`. A repeat that arrives while the first is still running gets 409. Keys are kept for 24 h and removed by retention.
- Proposal numbers retry inside a savepoint when two proposals are opened at once.
- Badge and stack-completion inserts tolerate a concurrent issue.

**Task queue:** workers on PostgreSQL claim tasks with `FOR UPDATE SKIP LOCKED`. A task that keeps killing its worker is marked failed after 3 attempts.

**One error format:** every error, including validation errors, unknown API paths, database conflicts and timeouts, returns:

```json
{"error": {"status": 422, "code": "validation_error", "message": "...", "fields": [...]}, "detail": "...", "request_id": "..."}
```
