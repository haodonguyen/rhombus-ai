# TODO: NL-to-Regex Data Processing Platform

Details, acceptance criteria and verification for each task are in `tasks/plan.md`.

## Phase 0: Walking Skeleton and Risk Spike
- [x] T1: Compose skeleton with Django health endpoint (web, postgres, redis) · M
- [x] T2: Celery worker (Java + PySpark image) and Flower · S · deps T1
- [x] T3: Frontend skeleton (Vite + React + TS, nginx, health check) · M · deps T1
- [x] T4: Spike: Spark reads CSV + XLSX from MinIO via S3A, writes Parquet · M · deps T2
- [ ] **Checkpoint: Foundation**
  - [x] One-command stack: `docker compose up --build`, all services healthy
  - [x] Tests and builds pass: backend pytest 10/10 + ruff; frontend lint, 3/3 tests, build
  - [x] Versions confirmed (see Architecture Decisions in plan.md)
  - [ ] Human review before Phase 1

## Phase 1: Core Pipeline (raw regex, no LLM)
- [x] T5: Browse S3 files (API + UI) · M · deps T3, T4
- [x] T6: Column preview (API + UI) · S · deps T5
- [x] T7: Spark `regex_replace` transform + readers/writers + Spark tests · M · deps T4
- [x] T8: Job model + submit (202) / poll API + `run_job` Celery task · M · deps T7
- [x] T9: Job UI: submit form + status polling with backoff · M · deps T6, T8
- [x] T10: Paginated results via DuckDB over Parquet (API + table UI) · M · deps T8, T9
- [ ] **Checkpoint: Core Pipeline**
  - [x] Browser flow end to end: file → Email column → brief regex → SUCCESS → paginated table
  - [x] Tests pass: backend 82 (incl. Spark + tasks, in worker) + ruff; frontend 20 + lint + tsc
  - [x] API run: submit 202 in 160 ms; 1000 rows / 1000 matched; Java-only regex → INVALID_PATTERN
  - [ ] Human review before Phase 2

## Phase 2: LLM Integration
- [x] T11: Regex validator (Java compat, ReDoS, empty match, timeout) · S · deps none
- [x] T12: NL → regex LLM service + Redis cache, wired into task and UI · M · deps T8, T11
- [ ] **Checkpoint: LLM**
  - [x] Tests pass offline with a mocked LLM client: backend 153 + ruff; frontend 23 + lint + tsc
  - [x] Without a key, description jobs fail as LLM_NOT_CONFIGURED; raw regex jobs still succeed;
        unsafe raw regex is rejected in the worker as INVALID_PATTERN
  - [x] Live run with local Ollama via the API: description → regex → Spark, and a repeated
        description is served from the cache (0.9 s job); the browser check is still to do
  - [ ] Human review before Phase 3

## Phase 3: Robustness
- [x] T13: Live progress (stages + SparkStatusTracker, throttled) + progress bar · S · deps T8
- [x] T14: Cancellation (revoke + cancelJobGroup) API + button · S · deps T13
- [x] T15: Retries, time limits, domain exceptions → error codes, UI error states · M · deps T12
- [x] T16: Excel support in pipeline (spark-excel) · S · deps T7, T15
- [ ] **Checkpoint: Robustness**
  - [x] Tests: backend 184 (incl. real Spark job-group cancel, XLSX = CSV, corrupt XLSX) + ruff;
        frontend 26 + lint + tsc
  - [x] 3M-row CSV: progress 10 → 50 → 85 → 90 → 100 in 6 s; running cancel stops in 1.3 s;
        queued cancel is immediate; finished job cancel → 409
  - [x] Cancel button and cancelled notice verified in the browser (queued 3M-row job →
        CANCELLED badge + notice, button removed)
  - [ ] Human review before Phase 4

## Phase 4: Additional LLM Transformations
- [ ] T17: Transform registry + format normalization transform · M · deps T12
- [ ] T18: PII detection & partial masking transform · M · deps T17
- [ ] **Checkpoint: Transformations** (all three run via same pipeline)

## Phase 5: Scale and Observability
- [ ] T19: 5M-row dataset generator, benchmark, partition/AQE tuning · M · deps T10, T13, T16
- [ ] T20: Structured logs with job_id, per-job metrics, Flower auth · S · deps T8
- [ ] **Checkpoint: Scale**

## Phase 6: Ship
- [ ] T21: Production config + public deployment + smoke test · M · deps T19, T20
- [ ] T22: README (architecture, partitioning, benchmarks, trade-offs) + demo video · S · deps T21
- [ ] **Checkpoint: Complete** (CLAUDE.md deliverables checklist all ticked)

## Open Questions (answer before T12 / T21)
- [x] LLM provider: local Ollama in docker-compose (no API key)
- [ ] Deployment target
- [ ] Production S3 bucket + credentials
- [ ] Confirm the two extra transforms
