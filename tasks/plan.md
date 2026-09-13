# Implementation Plan: Distributed NL-to-Regex Data Processing Platform

## Overview

A Django + React app where users pick a CSV/Excel file from S3, describe a pattern in
natural language, and a Celery task uses PySpark to replace matches across target
columns. The regex comes from an LLM, is checked before use, and is cached in Redis.
Jobs run asynchronously with live progress, results are paginated, and the stack must
hold up on millions of rows. Everything ships via docker-compose to a public URL, with
a README and a demo video. `CLAUDE.md` is the source of truth for architecture and
conventions.

## Architecture Decisions

- **Python 3.11 in Docker images, Spark 3.5.x, Java 17.** Spark 3.5 has mature
  `hadoop-aws` (S3A) and `spark-excel` builds. Python 3.11 rather than 3.12 is the
  safest pairing for PySpark 3.5. The local Python 3.13 is only for tooling, and all
  runtime work happens in containers.
  - **Confirmed by T4:** PySpark 3.5.9, Hadoop 3.3.4 (bundled), `hadoop-aws:3.3.4`,
    `aws-java-sdk-bundle:1.12.262`, `spark-excel_2.12:3.5.1_0.20.4`, OpenJDK 17.0.20,
    Python 3.11.16, Django 5.2. Jars are resolved with Ivy at image build and loaded
    through `spark.jars`. No SLF4J/log4j conflicts were seen.
  - `hadoop-aws` is pinned automatically to PySpark's bundled Hadoop version in
    `backend/docker/fetch_spark_jars.py`.
  - The MinIO image comes from `quay.io` because Docker Hub no longer publishes it.
  - Observed: the 1000-row XLSX read produced 8 partitions, while the CSV produced 1.
    Revisit in T16/T19.
- **Build the pipeline first, then add the LLM.** Phase 1 runs jobs with a
  user-supplied raw regex, so the risky parts (S3A, Spark, Celery, pagination) are
  proven before any LLM work. The LLM step later slots in ahead of the same pipeline.
- **`processing/` stays free of Django.** It is pure `DataFrame -> DataFrame` code,
  tested with a local SparkSession.
- **Results are written as Parquet with a row index.** The API reads pages with
  DuckDB/pyarrow and never starts a SparkSession in the web process.
- **The LLM writes a spec, and Spark runs it.** No LLM calls per row, for the regex
  step or for the two extra transforms.
- **Transforms use a registry (strategy pattern).** `regex_replace` plus two
  LLM-driven transforms share one Celery task and one Job model.
- **Status stays at the four required values.** Cancellation is recorded as
  `FAILED` + `error_code=CANCELLED`.
- **Dev uses MinIO as the S3 stand-in, production uses real S3.** Only the
  endpoint URL and credentials change.

## Dependency Graph

```
Compose skeleton (web, postgres, redis)          [T1]
 ├── Celery worker + Flower                      [T2]
 │    └── Spark-in-worker S3A spike (+Excel)     [T4]  ← highest risk, do early
 │         └── processing/ regex_replace         [T7]
 │              └── Job model + submit/poll task [T8]
 │                   ├── Job UI (submit + poll)  [T9]  ← needs T3, T6
 │                   ├── Paginated results       [T10]
 │                   ├── Progress reporting      [T13]
 │                   ├── Cancellation            [T14]
 │                   └── Retries / errors        [T15]
 ├── Frontend skeleton                           [T3]
 └── S3 file listing (API + UI)                  [T5]
      └── Column preview (API + UI)              [T6]

Regex validator (pure)          [T11] ──┐
LLM client + cache              [T12] ──┴── needs T8, T11
Transform registry + extra #1   [T17] ── needs T12
Extra transform #2              [T18] ── needs T17
Excel support                   [T16] ── needs T7 (spike result from T4)
Benchmark + tuning              [T19] ── needs T10, T13
Observability                   [T20] ── needs T8
Deploy                          [T21] ── needs all features
README + demo                   [T22] ── needs T19, T21
```

## Task List

### Phase 0: Walking Skeleton and Risk Spike

#### Task 1: Compose skeleton with Django health endpoint
**Description:** Create `backend/` as a Django + DRF project with env-driven settings,
a Postgres database and Redis. `docker compose up` starts `web`, `postgres` and
`redis`, and `/api/health/` reports whether the DB and Redis are reachable.
**Acceptance criteria:**
- [ ] `docker compose up --build` starts web, postgres and redis, all healthy
- [ ] `GET /api/health/` returns 200 with `{"db": "ok", "redis": "ok"}`
- [ ] `.env.example` lists every variable, and `.gitignore` excludes `.env`, data and output
**Verification:**
- [ ] `docker compose exec web pytest` passes (health test)
- [ ] `curl localhost:8000/api/health/`
**Dependencies:** None
**Files:** `docker-compose.yml`, `backend/Dockerfile`, `backend/config/settings.py`, `backend/config/urls.py`, `.env.example`
**Scope:** M

#### Task 2: Celery worker and Flower
**Description:** Add `config/celery.py`, a `worker` service (image includes Java 17 +
PySpark) and a `flower` service, using separate Redis DBs for broker, results and
cache. A `ping` task proves the round trip.
**Acceptance criteria:**
- [ ] Worker and Flower containers start, and Flower shows the worker online
- [ ] `ping.delay().get()` returns `"pong"` from the web container
- [ ] `acks_late`, `task_reject_on_worker_lost` and time limits set globally
**Verification:**
- [ ] `docker compose exec web python manage.py shell -c "..."` round trip
- [ ] Flower UI at `localhost:5555`
**Dependencies:** T1
**Files:** `backend/config/celery.py`, `backend/config/__init__.py`, `backend/Dockerfile` (worker target), `docker-compose.yml`
**Scope:** S

#### Task 3: Frontend skeleton
**Description:** Vite + React + TypeScript (strict) app with ESLint/Prettier, TanStack
Query, a typed API client and an nginx-served production build. The home page shows
the backend health status.
**Acceptance criteria:**
- [ ] `frontend` service serves the built app, and `/api` is proxied to `web`
- [ ] Page shows "Backend: ok" from `/api/health/`
**Verification:**
- [ ] `npm run lint && npm run build && npm test` pass
- [ ] Manual: open `localhost:3000`
**Dependencies:** T1
**Files:** `frontend/package.json`, `frontend/vite.config.ts`, `frontend/src/api/client.ts`, `frontend/Dockerfile`, `frontend/nginx.conf`
**Scope:** M

#### Task 4: Spike: Spark in the worker reads S3 via S3A (CSV and Excel)
**Description:** Add a `minio` service and a one-shot seeding job that uploads sample
CSV and XLSX files. Inside the worker, a throwaway task builds a SparkSession with
`hadoop-aws` + `spark-excel` packages, reads both files from `s3a://` and writes
Parquet. Confirm the jar and Python versions are compatible, and that Spark packages
are baked into the image rather than downloaded at runtime.
**Acceptance criteria:**
- [ ] CSV and XLSX from MinIO load into DataFrames with correct row counts
- [ ] Parquet output is written to `RESULTS_PATH`
- [ ] Working version matrix recorded in `tasks/plan.md` (Spark, hadoop-aws, spark-excel)
**Verification:**
- [ ] Run spike task, then inspect output with DuckDB
**Dependencies:** T2
**Files:** `docker-compose.yml`, `backend/Dockerfile` (worker target), `backend/processing/spark_session.py`, `scripts/seed_bucket.py`
**Scope:** M

### Checkpoint: Foundation
- [ ] Whole skeleton comes up with one command, and all tests and builds pass
- [ ] S3A + Spark + Excel versions confirmed (otherwise decide the fallback now, see Risks)
- [ ] Human review before feature work

### Phase 1: Core Pipeline (raw regex, no LLM)

#### Task 5: Browse S3 files (API + UI)
**Description:** `apps/files` exposes `GET /api/files/`, which lists `.csv/.xlsx/.xls`
objects with S3 listing pagination through boto3. The UI shows a selectable file list
with loading, empty and error states.
**Acceptance criteria:**
- [ ] Only supported extensions returned, with key, size and last modified
- [ ] Empty bucket and S3 errors are shown clearly in the UI
**Verification:**
- [ ] API tests with moto/stubbed boto3, plus a component test for the list states
- [ ] Manual: seeded files appear
**Dependencies:** T3, T4
**Files:** `backend/apps/files/{services,views,urls}.py`, `backend/tests/files/test_api.py`, `frontend/src/features/files/FileList.tsx`
**Scope:** M

#### Task 6: Column preview (API + UI)
**Description:** `GET /api/files/columns/?key=` returns column names and a small
sample of rows, reading only the first few lines through a lightweight reader without
Spark. The UI lets the user multi-select target columns.
**Acceptance criteria:**
- [ ] Returns columns + ≤10 sample rows for CSV and XLSX
- [ ] Unknown key → 404 with the standard error shape
**Verification:**
- [ ] API tests; component test for the column selector
**Dependencies:** T5
**Files:** `backend/apps/files/services.py`, `backend/apps/files/views.py`, `frontend/src/features/files/ColumnPicker.tsx`
**Scope:** S

#### Task 7: Spark regex_replace transform (data layer)
**Description:** Pure `processing/` code: CSV reader (all columns as string,
PERMISSIVE mode), adding a stable row index, `regex_replace(df, columns, pattern,
replacement)` built on `regexp_replace` and `rlike` for the match count, and a
Parquet writer. No Django imports.
**Acceptance criteria:**
- [ ] Replaces across multiple columns in a single pass, and nulls stay null
- [ ] Replacement containing `$` or `\` is inserted literally
- [ ] Returns `matched_count`, and row order is stable through the row index
**Verification:**
- [ ] `pytest backend/tests/processing` with a `local[2]` SparkSession fixture (unicode, no matches, multi-column cases)
**Dependencies:** T4
**Files:** `backend/processing/{readers,writers}.py`, `backend/processing/transforms/regex_replace.py`, `backend/tests/processing/conftest.py`, `backend/tests/processing/test_regex_replace.py`
**Scope:** M

#### Task 8: Job model, submit/poll API and orchestration task
**Description:** `Job` model per CLAUDE.md with a single method that enforces status
transitions. `POST /api/jobs/` validates input, creates a QUEUED job, enqueues
`run_job` and returns 202 + id. `GET /api/jobs/{id}/` returns status. `run_job`
calls the T7 functions and records `result_path`, `row_count` and `matched_count`.
**Acceptance criteria:**
- [ ] Submit returns 202 in under 200 ms, and no Spark runs in the web process
- [ ] Job moves QUEUED → RUNNING → SUCCESS, or FAILED with `error_code`
- [ ] Invalid input (missing columns, bad key) → 400 with the standard error shape
**Verification:**
- [ ] DRF tests + eager-Celery task test with local Spark
- [ ] Manual: submit via curl and poll to SUCCESS
**Dependencies:** T7
**Files:** `backend/apps/jobs/{models,serializers,views,urls,tasks}.py`, `backend/apps/jobs/migrations/0001_initial.py`, `backend/tests/jobs/`
**Scope:** M

#### Task 9: Job UI: submit form and status polling
**Description:** Form with the selected file, target columns, pattern (raw regex for
now) and replacement value. On submit it navigates to a job view that polls with
backoff and stops at a terminal status.
**Acceptance criteria:**
- [ ] Polling backs off from 1s to 5s and stops on SUCCESS/FAILED
- [ ] Errors are shown inline, and the UI never freezes
**Verification:**
- [ ] Component tests for QUEUED/RUNNING/SUCCESS/FAILED rendering
- [ ] Manual: full flow in browser
**Dependencies:** T6, T8
**Files:** `frontend/src/features/jobs/{JobForm,JobStatus}.tsx`, `frontend/src/api/jobs.ts`
**Scope:** M

#### Task 10: Paginated results (API + UI)
**Description:** `GET /api/jobs/{id}/results/?page=&page_size=` reads a page of the
job's Parquet output with DuckDB, ordered by row index, with `page_size` capped at 500.
The UI renders a paginated table.
**Acceptance criteria:**
- [ ] Correct page slices and total count, `page_size` > 500 is clamped, and non-SUCCESS jobs → 409
- [ ] Zero-row and zero-match results show an empty state
**Verification:**
- [ ] API tests with a fixture Parquet file; component test for the table
- [ ] Manual: sample email scenario from the brief shows REDACTED
**Dependencies:** T8, T9
**Files:** `backend/apps/jobs/results.py`, `backend/apps/jobs/views.py`, `frontend/src/features/results/ResultsTable.tsx`
**Scope:** M

### Checkpoint: Core Pipeline
- [x] Browser flow works end to end: pick file → columns → raw regex → progress → paginated results
- [x] All backend, Spark and frontend tests pass
- [ ] Human review before adding the LLM

**Phase 1 implementation notes (differences from the plan above):**
- Supported types are `.csv` and `.xlsx` only; `.xls` was dropped because openpyxl cannot
  preview it.
- XLSX reading is already wired into `processing/readers.py`. That reduces T16 to tests,
  corrupt-file handling and partitioning notes.
- Stages are `LOADING → TRANSFORMING → FINALIZING`. Transform and write are one Spark
  action, so a separate WRITING stage would be misleading.
- Row order uses `monotonically_increasing_id()` as `__row_id`, with no `zipWithIndex` and
  therefore no Python round trip. Pages use a two-step DuckDB query: LIMIT/OFFSET on the
  id column, then BETWEEN.
- Java regex compatibility is checked in the JVM (`Pattern.compile`) before the transform,
  so Python-only syntax fails as `INVALID_PATTERN`.
- Known trade-off: Spark's CSV reader turns empty fields into `null`, and they show as
  `null` in results. Revisit in T15/T16 (e.g. render as empty, or set `emptyValue`).
- The standard error shape and domain exceptions (planned for T15) were introduced now,
  because the files and jobs APIs needed them.

### Phase 2: LLM Integration

#### Task 11: Regex validator
**Description:** `apps/llm/validation.py` enforces a length limit, a Python compile
check, rejection of Java-incompatible syntax, static detection of catastrophic
backtracking (nested or overlapping quantifiers), an empirical timeout on adversarial
input, and rejection of patterns that match the empty string.
**Acceptance criteria:**
- [ ] Rejects `(a+)+`, `(a|a)*`, `(?P<x>..)`, `""` and patterns over 500 chars, each with a specific reason
- [ ] Accepts the brief's email regex and common patterns (phone, date, URL)
**Verification:**
- [ ] Table-driven `pytest backend/tests/llm/test_validation.py`
**Dependencies:** None (can run in parallel with Phase 1)
**Files:** `backend/apps/llm/validation.py`, `backend/tests/llm/test_validation.py`
**Scope:** S

#### Task 12: NL → regex via LLM with Redis cache
**Description:** Provider interface + implementation, a versioned prompt with few-shot
examples, structured JSON output validated against a schema, and a Redis cache keyed
by `sha256(normalized prompt + transform + model + PROMPT_VERSION)`. `run_job` gains a
`GENERATING_REGEX` stage and fails with `INVALID_PATTERN` when validation fails. The
form switches to a natural-language input, and the job view shows the pattern and
whether it came from cache.
**Acceptance criteria:**
- [ ] The same prompt twice → second job has `llm_cached=true` with no provider call
- [ ] Malformed LLM output or an invalid pattern → FAILED with a clear message
- [ ] Brief's example ("Find email addresses… replace with 'REDACTED'") works end to end
**Verification:**
- [ ] Tests with a mocked provider (hit/miss, malformed JSON, invalid pattern)
- [ ] Manual: live LLM run with 5+ varied phrasings
**Dependencies:** T8, T11
**Files:** `backend/apps/llm/{client,service,cache}.py`, `backend/apps/llm/prompts/regex.py`, `backend/apps/jobs/tasks.py`, `frontend/src/features/jobs/JobForm.tsx`
**Scope:** M

### Checkpoint: LLM
- [ ] NL prompt → regex → Spark replacement works in the browser, and a repeat prompt hits the cache
- [ ] Tests pass with no network access (provider mocked)

### Phase 3: Robustness

#### Task 13: Live progress reporting
**Description:** Stage weights plus `SparkStatusTracker` completed/total task counts
during TRANSFORMING, polled on a background thread and written to the Job at most
once per second. The UI shows a progress bar and the current stage.
**Acceptance criteria:**
- [ ] Progress never goes backwards, reaches 100 on SUCCESS, and DB writes are throttled
**Verification:**
- [ ] Unit test for progress math and throttling; manual run on a 1M-row file
**Dependencies:** T8
**Files:** `backend/processing/progress.py`, `backend/apps/jobs/tasks.py`, `frontend/src/features/jobs/JobStatus.tsx`
**Scope:** S

#### Task 14: Cancellation
**Description:** `POST /api/jobs/{id}/cancel/` revokes the Celery task and calls
`cancelJobGroup(job_id)`, since `run_job` sets a Spark job group. Job becomes FAILED
with `CANCELLED`. The UI shows a cancel button while the job is running.
**Acceptance criteria:**
- [ ] Cancelling a running job stops Spark work within a few seconds
- [ ] Cancelling a terminal job → 409; cancelling a queued job never starts Spark
**Verification:**
- [ ] Task test for cancel-before-start; manual cancel mid-run on a large file (Flower shows revoked)
**Dependencies:** T13
**Files:** `backend/apps/jobs/{views,tasks,services}.py`, `frontend/src/features/jobs/JobStatus.tsx`
**Scope:** S

#### Task 15: Retries, time limits and error mapping
**Description:** Domain exceptions (`InvalidPatternError`, `SourceFileError`,
`LLMUnavailableError`…) mapped to error codes in one place. `autoretry_for` covers
transient S3, LLM and Redis errors with exponential backoff + jitter. Soft time limit
→ FAILED `TIMEOUT`. Consistent API error shape via a DRF exception handler. The UI
handles every error code.
**Acceptance criteria:**
- [ ] Transient error retried up to N times then FAILED, while user errors are never retried
- [ ] Every failure path produces `error_code` + a user-safe message
**Verification:**
- [ ] Task tests simulating transient/permanent errors and soft timeout
**Dependencies:** T12
**Files:** `backend/apps/jobs/{exceptions,tasks}.py`, `backend/config/exception_handler.py`, `frontend/src/features/jobs/JobStatus.tsx`
**Scope:** M

#### Task 16: Excel support in the pipeline
**Description:** `readers.py` dispatches by file type and reads XLSX through
`spark-excel`, using the version matrix confirmed in T4. Document that XLSX cannot be
split (read in a single task) and repartition after reading.
**Acceptance criteria:**
- [ ] XLSX job produces identical results to the same data as CSV
- [ ] Unsupported/corrupt file → FAILED `SOURCE_FILE_ERROR`
**Verification:**
- [ ] Spark test comparing CSV vs XLSX fixture output
**Dependencies:** T7, T15
**Files:** `backend/processing/readers.py`, `backend/tests/processing/test_readers.py`, `backend/tests/fixtures/sample.xlsx`
**Scope:** S

### Checkpoint: Robustness
- [ ] Progress, cancel, retry, timeout, Excel, empty and error states all verified in the browser
- [ ] Human review

### Phase 4: Additional LLM Transformations

#### Task 17: Transform registry and extra transform #1 (format normalization)
**Description:** Registry mapping `transform_type` → (prompt, spec schema, Spark
executor). Refactor `regex_replace` into it. Add **format normalization** (e.g.
"standardize dates to ISO 8601"): the LLM returns a list of rules, which are
validated and applied with Spark functions. The UI gets a transform-type selector with
per-type fields.
**Acceptance criteria:**
- [ ] Existing regex_replace behaviour unchanged (tests still green)
- [ ] Mixed date formats normalize to `YYYY-MM-DD`, and unparseable values are left as-is
**Verification:**
- [ ] Spark tests for the executor + mocked-LLM task test
**Dependencies:** T12
**Files:** `backend/processing/transforms/{registry,normalize}.py`, `backend/apps/llm/prompts/normalize.py`, `backend/apps/jobs/tasks.py`, `frontend/src/features/jobs/JobForm.tsx`
**Scope:** M

#### Task 18: Extra transform #2 (PII detection and masking)
**Description:** The LLM classifies which columns contain PII from a sample of rows,
and returns a masking spec (pattern + partial-mask strategy). Spark applies it to the
detected columns. The UI shows which columns were detected before the results.
**Acceptance criteria:**
- [ ] Detects email/phone/name columns in the sample dataset and masks partially (e.g. `j***@domain.com`)
- [ ] Generated patterns go through the T11 validator
**Verification:**
- [ ] Spark tests for masking + mocked-LLM detection test
**Dependencies:** T17
**Files:** `backend/processing/transforms/pii_mask.py`, `backend/apps/llm/prompts/pii.py`, `backend/tests/processing/test_pii_mask.py`, `frontend/src/features/jobs/JobStatus.tsx`
**Scope:** M

### Checkpoint: Transformations
- [ ] All three transforms run through the same async/Spark pipeline from the UI

### Phase 5: Scale and Observability

#### Task 19: Large dataset benchmark and partition tuning
**Description:** `scripts/generate_dataset.py` (5M+ rows with emails, phones, dates)
uploads to the bucket. `scripts/benchmark.py` times each stage. Tune partition size
(~128 MB), `shuffle.partitions` and AQE, and optionally add spark-master/worker
services to show distributed mode. Record the numbers.
**Acceptance criteria:**
- [ ] 5M-row job completes without worker memory errors, and the UI stays responsive
- [ ] Benchmark table (rows, partitions, duration per stage) saved for the README
**Verification:**
- [ ] Run benchmark twice; results reproducible within ~20%
**Dependencies:** T10, T13, T16
**Files:** `scripts/generate_dataset.py`, `scripts/benchmark.py`, `backend/processing/spark_session.py`, `docker-compose.yml`
**Scope:** M

#### Task 20: Observability
**Description:** Structured JSON logs with `job_id` on every task log line. Per-job
metrics (stage durations, rows, matches, cache hit) stored on the Job and logged. Flower
with basic auth. Celery events enabled.
**Acceptance criteria:**
- [ ] A single job can be traced across web and worker logs by `job_id`
- [ ] Flower shows task history, and job detail API exposes duration metrics
**Verification:**
- [ ] Manual: run a job, grep logs by id, check Flower
**Dependencies:** T8
**Files:** `backend/config/logging.py`, `backend/apps/jobs/{tasks,serializers}.py`, `docker-compose.yml`
**Scope:** S

### Checkpoint: Scale
- [ ] Sizeable-dataset evidence captured and all tests green

### Phase 6: Ship

#### Task 21: Production configuration and public deployment
**Description:** Production settings (DEBUG off, gunicorn, allowed hosts, CORS/CSRF,
static via nginx), a `docker-compose.prod.yml` override using real S3, and healthchecks.
Deploy to the chosen host with HTTPS, and run an end-to-end smoke test on the public URL.
**Acceptance criteria:**
- [ ] Public URL runs the brief's email scenario end to end
- [ ] No secrets in the repo, and Flower is not publicly open without auth
**Verification:**
- [ ] Smoke script against the public URL; manual browser run
**Dependencies:** T19, T20
**Files:** `docker-compose.prod.yml`, `backend/config/settings.py`, `frontend/nginx.conf`, `scripts/smoke_test.sh`
**Scope:** M

#### Task 22: README and demo video
**Description:** README covering setup/run, an architecture diagram and reasoning,
partitioning and parallelism choices, benchmark results, LLM + validation design,
the extra transforms, trade-offs and known limits. Record a short demo of an async job
running to completion and embed it.
**Acceptance criteria:**
- [ ] A fresh clone plus the README instructions brings the stack up
- [ ] Demo video embedded and shows progress → results
**Verification:**
- [ ] Follow README from a clean checkout
**Dependencies:** T21
**Files:** `README.md`, `docs/architecture.md` (optional)
**Scope:** S

### Checkpoint: Complete
- [ ] Every item in the CLAUDE.md deliverables checklist is ticked
- [ ] Final human review before submission

## Parallelization Opportunities

- **Parallel after T1:** T2 (worker), T3 (frontend skeleton), T11 (validator, pure Python).
- **Parallel after T8:** T10 (results), T13 (progress), T20 (observability).
- **Contract first:** agree the API shapes in CLAUDE.md before splitting frontend and backend work on T9/T10.
- **Sequential:** Job model migrations (T8 → T12 → T17/T20 add fields); keep migrations on one branch.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `hadoop-aws` / `spark-excel` / Python version mismatch | High | T4 spike first; pin versions in the worker image; fallback: read XLSX with pandas/openpyxl → Parquet → Spark |
| XLSX not splittable, so large Excel files are slow or exhaust memory | Med | Size limit for XLSX, convert to Parquet first, document in README |
| Java regex vs Python regex dialect differences | High | Validator rejects Python-only syntax; Spark tests run the real `regexp_replace` |
| ReDoS pattern runs inside Spark (no timeout) | High | Validate before use (static + timed empirical check); task soft time limit as last resort |
| LLM produces wrong or overly broad regex | Med | Few-shot prompts, reject empty-match patterns, show the pattern to the user, cache only validated results |
| Progress tracking inaccurate with lazy Spark evaluation | Low | Stage weights + StatusTracker counts; honest coarse progress |
| Deployment host too small for Spark (memory) | Med | Size VM ≥ 8 GB RAM; tune executor/driver memory; limit concurrent jobs per worker to 1 |
| LLM costs/rate limits during testing | Low | Redis cache, mocked provider in tests, retries with backoff |

## Open Questions

1. **LLM provider:** Claude (Anthropic API), or another provider or key you already have?
2. **Deployment target:** a single VM (e.g. AWS EC2/Lightsail) running docker-compose, or something else?
3. **S3:** do you have an AWS bucket and credentials for production, or should the deployment also use MinIO?
4. **Extra transforms:** are format normalization + PII masking OK, or do you prefer others (e.g. value categorization)?
5. **Deadline:** does it affect scope (e.g. drop the spark-master/worker services from T19)?
