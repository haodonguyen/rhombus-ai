# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Technical assessment: **Distributed NL-to-Regex Data Processing Platform**.
Users pick a CSV/Excel file from S3, describe a pattern in natural language
("find email addresses"), an LLM turns it into a regex, and a Celery task applies
the replacement across target column(s) with PySpark. Results are shown paginated
with live job progress. Must hold up on **millions of rows**.

Good software design is weighted heavily — prefer clear layering and small,
well-named modules over clever code.

## Stack (fixed by the brief — do not substitute)

| Concern               | Technology                                          |
|-----------------------|-----------------------------------------------------|
| API / persistence     | Django + Django REST Framework, PostgreSQL          |
| Async tasks           | Celery                                              |
| Broker / results / cache | Redis (all three roles)                          |
| Data engine           | PySpark (DataFrame API, never row-by-row Python)    |
| Ingestion             | Amazon S3 → Spark DataFrame (`s3a://`), boto3 for listing |
| Frontend              | React (Vite + TypeScript)                           |
| LLM                   | Provider behind an interface; cache results in Redis |
| Observability         | Flower + structured logs + task metrics             |
| Local stack           | docker-compose, single command; MinIO/LocalStack for S3 in dev |

## Deliverables checklist

- [ ] GitHub repo with complete source
- [ ] `README.md`: setup/run, architecture + reasoning, **partitioning & parallelism
      choices**, trade-offs, embedded demo video (async job running to completion)
- [ ] `docker-compose up` brings up the whole stack
- [ ] Evidence the pipeline handles a sizeable dataset (benchmark script + numbers in README)
- [ ] Tests for the task and Spark layers
- [ ] Flower / worker monitoring and basic task metrics
- [ ] Public deployment with a working end-to-end URL
- [ ] Two **additional LLM-driven transformations** through the same async/Spark pipeline

## Target layout

```
backend/
  config/                 # settings (env-driven), urls, celery.py, wsgi/asgi
  apps/
    files/                # S3 browsing API: list files, preview schema/columns
    jobs/                 # Job model, serializers, views, urls, tasks.py
    llm/                  # client interface, prompts, Redis cache, regex validator
  processing/             # PURE data layer — no Django imports
    spark_session.py      # SparkSession factory (S3A config, tuning)
    readers.py            # CSV / Excel → DataFrame
    transforms/           # regex_replace.py + the two extra LLM transforms
    writers.py            # write results to Parquet
    progress.py           # stage + SparkStatusTracker progress reporting
  tests/
frontend/
  src/api/                # typed API client
  src/features/           # files/, jobs/, results/
  src/components/
docker-compose.yml
scripts/                  # dataset generator, benchmark, seed-bucket
```

### Layering rules

- **API layer** (views/serializers): validate input, create `Job`, enqueue task,
  return. No Spark, no LLM calls, no S3 reads of data.
- **Task layer** (`apps/jobs/tasks.py`): orchestration only — update job status,
  call LLM service, call `processing/`, handle retries/cancel.
- **Data layer** (`processing/`): pure functions `DataFrame -> DataFrame` plus
  read/write helpers. Must be importable and testable without Django.
- **LLM layer** (`apps/llm/`): prompt → structured output, validation, caching.
  Hide the provider behind a small interface so it can be mocked in tests.

## Domain model

`Job`:
- `id` (UUID), `created_at`, `updated_at`, `started_at`, `finished_at`
- `status`: `QUEUED | RUNNING | SUCCESS | FAILED` (exactly these four, per brief)
- `progress` (0–100 int) and `stage` (`LOADING`, `TRANSFORMING`, `FINALIZING`;
  Phase 2 adds `GENERATING_REGEX`)
- `source_key` (S3 key), `file_type` (`csv` | `xlsx`), `target_columns` (JSON list)
- `transform_type` (`regex_replace` | the two extra transforms)
- `pattern` (the regex applied), `replacement_value`; Phase 2 adds `nl_prompt`, `llm_cached`
- `result_path` (Parquet location), `row_count`, `matched_count`
- `error_code`, `error_message`, `celery_task_id`

Cancellation: mark `FAILED` with `error_code="CANCELLED"` (keeps the required
status set). Status transitions only go forward; enforce in one model method.

## API contract

| Method | Path                               | Purpose                                     |
|--------|------------------------------------|---------------------------------------------|
| GET    | `/api/files/`                      | List CSV/XLSX objects in the bucket (paginate S3 listing) |
| GET    | `/api/files/columns/?key=`         | Column names + small sample for the picker  |
| POST   | `/api/jobs/`                       | Submit job → **202 + `{id}` immediately**   |
| GET    | `/api/jobs/{id}/`                  | Poll status, stage, progress, error         |
| GET    | `/api/jobs/{id}/results/?page=&page_size=` | Paginated processed rows          |
| POST   | `/api/jobs/{id}/cancel/`           | Revoke task and cancel Spark job group      |
| GET    | `/api/health/`                     | Liveness (DB, Redis reachable)              |

- Cap `page_size` (e.g. max 500). Never return a whole dataset.
- Results are served from the Parquet output with **pyarrow/DuckDB** in the web
  process — never start a SparkSession inside Django request handling.
- Errors use a consistent shape: `{"error": {"code": "...", "message": "..."}}`.

## Pipeline (Celery task)

1. Mark `RUNNING`, stage `GENERATING_REGEX`.
2. LLM service: normalize prompt → check Redis cache → call LLM on miss →
   validate pattern → cache. Fail fast with `error_code="INVALID_PATTERN"`.
3. Stage `LOADING`: read `s3a://bucket/key` into a DataFrame.
4. Stage `TRANSFORMING`: apply `regexp_replace` on each target column (single
   `select`/`withColumn` pass). Compute `matched_count` with `rlike` in the same job
   where practical.
5. Stage `WRITING`: write Parquet to result location; record `row_count`.
6. Mark `SUCCESS` (100%) or `FAILED` with a code and a user-safe message.

Rules:
- Use `sc.setJobGroup(job_id, ..., interruptOnCancel=True)` so cancel can call
  `sc.cancelJobGroup(job_id)`; cancel also does `celery revoke`.
- Retries: `autoretry_for` only transient errors (S3/network, LLM rate limits,
  Redis) with exponential backoff + jitter and `max_retries`. Never retry invalid
  regex or bad user input.
- Set `acks_late=True`, `task_reject_on_worker_lost=True`, soft/hard time limits.
- Tasks must be idempotent: re-running a job overwrites its own result path.
- Progress: coarse stage weights plus `SparkStatusTracker` completed/total tasks
  during `TRANSFORMING`; write to DB (throttled, e.g. ≤1 update/sec).

## Spark guidance

- Use built-in functions (`regexp_replace`, `rlike`, `when`) — **no Python UDFs**
  for the core path; they serialize every row through Python and kill throughput.
- **Regex dialect gotcha:** Spark evaluates regex with **Java** `java.util.regex`,
  while the LLM/validator works in Python. Validate for Java compatibility
  (reject Python-only syntax like `(?P<name>...)`, `\Z`; escape `$` and `\` in
  replacement strings for Java — use `Matcher.quoteReplacement` semantics).
- Partitioning: repartition by size (target ~128 MB/partition, or row-count based),
  set `spark.sql.shuffle.partitions` from cluster cores, enable AQE
  (`spark.sql.adaptive.enabled=true`). Document the choices in README.
- Excel: Spark has no native reader. Use `com.crealytics:spark-excel` for large
  files; note the trade-off (XLSX is not splittable — single-task read) in README.
- CSV: `header=true`, explicit `inferSchema=false` (read target columns as string),
  handle malformed rows via `mode=PERMISSIVE` + corrupt record column.
- Cast target columns to string; null values stay null after replacement.
- Cache the source DataFrame only if it is reused across actions; unpersist after.
- Write output with a stable row order (add a row index at read time) so pagination
  is deterministic.

## LLM integration

- Output must be **structured** (JSON: `pattern`, `flags`, `explanation`), parsed
  and schema-validated. Never `eval` or trust free text.
- Cache key: `sha256(normalized_prompt + transform_type + model + PROMPT_VERSION)`;
  TTL configurable. Bump `PROMPT_VERSION` whenever prompts change.
- Prompts live in `apps/llm/prompts/` with few-shot examples covering varied
  phrasings (emails, phone numbers, dates, URLs, IDs, postcodes).
- Keep API keys in env vars only; never log prompts containing user data at INFO.

### Regex validation (required before applying)

1. Length limit (e.g. ≤ 500 chars) and compile check (Python `re` + Java-compat rules).
2. Reject catastrophic-backtracking shapes: nested quantifiers `(a+)+`, `(a*)*`,
   overlapping alternations under a quantifier `(a|a)*`, excessive nesting depth.
3. Empirical check: run against adversarial strings in a subprocess/thread with a
   hard timeout (or the `regex` module's `timeout=`); reject if it exceeds budget.
4. Reject patterns that match the empty string (would replace between every char).

### Two additional LLM transformations

The LLM generates a **specification once**, and Spark executes it — never call the
LLM per row. Candidate choices (pick two, document in README):
- **Format normalization** — "standardize dates to ISO 8601" → LLM emits a list of
  `(regex, replacement)` / `to_date` format rules applied with Spark functions.
- **PII detection & masking** — LLM classifies which columns contain PII from a
  sample of rows, then masks via generated patterns (partial masking, e.g. `***@domain`).
- **Value categorization** — LLM emits a mapping/rule set applied via `when`/join.

## Frontend

- Flow: select file → pick column(s) (from `/files/columns`) → NL prompt +
  replacement → submit → job view with live progress → paginated results table.
- Poll `/api/jobs/{id}/` with backoff (e.g. 1s → 5s) and stop on terminal status;
  use TanStack Query or equivalent. Cancel button while running.
- Show the generated regex and whether it came from cache.
- Handle explicitly: loading, empty bucket, empty results / zero matches,
  validation errors, failed and cancelled jobs, network errors. Never block the UI.
- Server-side pagination for results; virtualize rows if page size is large.

## Configuration

All settings via environment variables (`.env.example` committed, `.env` ignored):
`DJANGO_SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`,
`CELERY_RESULT_BACKEND`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_REGION`, `S3_BUCKET`, `S3_ENDPOINT_URL` (MinIO in dev), `RESULTS_PATH`,
`LLM_API_KEY`, `LLM_MODEL`, `LLM_CACHE_TTL`, `SPARK_MASTER`, `SPARK_DRIVER_MEMORY`.

Use separate Redis DB numbers for broker, result backend and cache.

## docker-compose services

`web` (Django/gunicorn), `worker` (Celery + PySpark, Java runtime), `redis`,
`postgres`, `flower`, `frontend` (built static via nginx), `minio` + a one-shot
bucket seeding job for dev. Optional: `spark-master`/`spark-worker` to show
distributed mode. Add healthchecks and `depends_on: condition: service_healthy`.

## Commands

```bash
docker compose up --build                 # whole stack (web runs migrations on start)
docker compose exec worker pytest         # full backend suite (Spark tests need the worker)
docker compose exec web ruff check .      # backend lint
docker compose exec web python manage.py shell -c "from apps.core.tasks import spark_smoke_test as t; print(t.delay().get(timeout=600))"
cd frontend && npm run dev                # Vite dev server, proxies /api to :8000
cd frontend && npm run lint && npm test && npm run build
```
Ports: frontend 3000, API 8000, Flower 5555 (admin:admin), MinIO 9000 / console 9001.

## Testing

- `processing/`: pytest with a session-scoped local `SparkSession` fixture
  (`local[2]`); small in-memory DataFrames; cover nulls, multiple columns, unicode,
  no matches, special chars in replacement (`$`, `\`).
- Regex validator: table-driven tests for valid, invalid, ReDoS, empty-match cases.
- LLM layer: mock the provider; test cache hit/miss and malformed LLM output.
- Tasks: run Celery eagerly (`task_always_eager`) with mocked LLM + local Spark;
  assert status/progress transitions, retry on transient errors, cancellation.
- API: DRF tests for 202-on-submit, pagination bounds, error shapes.
- Frontend: component tests for job status states and paginated table.

## Coding conventions

- Python: type hints everywhere, `ruff` + `black`, docstrings on public functions.
- TypeScript strict mode, ESLint + Prettier; API types in one place.
- Small focused modules; no business logic in views or React components.
- Raise domain exceptions (`InvalidPatternError`, `SourceFileError`) and map them to
  error codes in one place.
- Log with job_id in every task log line; expose task duration/row metrics.
- Don't commit datasets, `.env`, or Spark output.
