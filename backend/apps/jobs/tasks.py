"""Celery tasks. Orchestration only: status changes, error mapping and retries. Spark work
lives in `processing/`, LLM calls in `apps/llm/`.
"""

import logging
import random
from pathlib import Path
from uuid import UUID

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from apps.core.spark import spark_config_from_settings
from apps.files.storage import spark_uri
from apps.jobs.models import Job, JobStatus
from apps.llm.exceptions import LLMError, LLMUnavailable
from apps.llm.service import generate_pattern
from processing.errors import InvalidPatternError, ProcessingError
from processing.file_types import FileType
from processing.regex_safety import validate_pattern
from processing.spark_session import get_spark_session

logger = logging.getLogger(__name__)

# Coarse progress reported at each stage boundary.
STAGE_PROGRESS = {"GENERATING_REGEX": 5, "LOADING": 10, "TRANSFORMING": 30, "FINALIZING": 90}
# Task-level retries for LLM outages, on top of the SDK's own short retries.
LLM_MAX_TASK_RETRIES = 3


def result_path_for(job_id: UUID | str) -> str:
    return str(Path(settings.RESULTS_PATH) / "jobs" / str(job_id))


def llm_retry_delay(retries_so_far: int) -> float:
    """Exponential backoff with jitter: roughly 15s, 30s, 60s."""
    return 15 * 2**retries_so_far + random.uniform(0, 5)


@shared_task(bind=True, name="jobs.run_job")
def run_job(self, job_id: str) -> None:
    started = Job.objects.transition(
        job_id,
        JobStatus.RUNNING,
        started_at=timezone.now(),
        stage="",
        progress=0,
        error_code="",
        error_message="",
    )
    if not started:
        logger.info("Job %s is not runnable in its current state; skipping", job_id)
        return

    job = Job.objects.get(pk=job_id)
    output_path = result_path_for(job.id)
    try:
        pattern = _resolve_pattern(job)
        stats = _run_spark(job, pattern, output_path)
    except LLMUnavailable as exc:
        if self.request.retries < LLM_MAX_TASK_RETRIES:
            logger.warning("Job %s: LLM unavailable, scheduling retry", job_id)
            raise self.retry(
                exc=exc,
                countdown=llm_retry_delay(self.request.retries),
                max_retries=LLM_MAX_TASK_RETRIES,
            ) from exc
        _fail(job_id, exc.code, str(exc))
    except (ProcessingError, LLMError) as exc:
        logger.info("Job %s failed: %s", job_id, exc)
        _fail(job_id, exc.code, str(exc))
    except SoftTimeLimitExceeded:
        logger.warning("Job %s exceeded its time limit", job_id)
        _fail(job_id, "TIMEOUT", "The job exceeded its time limit.")
    except Exception:
        logger.exception("Job %s failed unexpectedly", job_id)
        _fail(job_id, "INTERNAL_ERROR", "An unexpected error occurred while processing the job.")
    else:
        Job.objects.transition(
            job_id,
            JobStatus.SUCCESS,
            progress=100,
            finished_at=timezone.now(),
            result_path=output_path,
            row_count=stats.row_count,
            matched_count=stats.matched_count,
        )
        logger.info(
            "Job %s succeeded: %d rows, %d matched", job_id, stats.row_count, stats.matched_count
        )


def _resolve_pattern(job: Job) -> str:
    """The pattern to apply: the stored one if present, otherwise generated from the
    description and saved, so a retried job never calls the LLM twice.
    """
    if job.pattern:
        return validate_pattern(job.pattern)
    if not job.nl_prompt:
        raise InvalidPatternError("The job has neither a pattern nor a description.")

    Job.objects.update_progress(
        job.id, stage="GENERATING_REGEX", progress=STAGE_PROGRESS["GENERATING_REGEX"]
    )
    generated = generate_pattern(job.nl_prompt)
    Job.objects.filter(pk=job.id).update(
        pattern=generated.pattern,
        pattern_explanation=generated.explanation,
        llm_cached=generated.cached,
    )
    return generated.pattern


def _run_spark(job: Job, pattern: str, output_path: str):
    # Imported lazily: PySpark exists only in the worker image, while the web process
    # imports this module to enqueue tasks.
    from processing.pipeline import RegexReplaceSpec, run_regex_replace

    spec = RegexReplaceSpec(
        source_uri=spark_uri(job.source_key),
        file_type=FileType(job.file_type),
        columns=tuple(job.target_columns),
        pattern=pattern,
        replacement=job.replacement_value,
        output_path=output_path,
    )
    spark = get_spark_session(spark_config_from_settings())
    return run_regex_replace(
        spark,
        spec,
        on_stage=lambda stage: Job.objects.update_progress(
            job.id, stage=stage, progress=STAGE_PROGRESS[stage]
        ),
    )


def _fail(job_id: str, code: str, message: str) -> None:
    Job.objects.transition(
        job_id,
        JobStatus.FAILED,
        finished_at=timezone.now(),
        error_code=code,
        error_message=message,
    )
