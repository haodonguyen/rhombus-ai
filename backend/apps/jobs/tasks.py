"""Celery tasks. Orchestration only: status changes, progress, cancellation, retries and
error mapping. Spark work lives in `processing/`, LLM calls in `apps/llm/`, and the Spark
transformation for each job type in `apps/jobs/transform_builders.py`.
"""

import logging
import random
from pathlib import Path
from uuid import UUID

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.core.spark import spark_config_from_settings
from apps.files.storage import spark_uri
from apps.jobs.cancellation import JobCancelled, raise_if_cancel_requested
from apps.jobs.models import (
    CANCELLED_ERROR_CODE,
    CANCELLED_MESSAGE,
    Job,
    JobStatus,
    TransformType,
)
from apps.llm.exceptions import LLMError
from apps.llm.service import generate_pattern
from processing.errors import InvalidPatternError, ProcessingError
from processing.file_types import FileType
from processing.pipeline_stats import RunStats
from processing.progress import ProgressTracker, SparkJobMonitor
from processing.regex_safety import validate_pattern
from processing.spark_session import get_spark_session

logger = logging.getLogger(__name__)

# Task-level retries for transient failures (LLM or storage outages), on top of the client
# libraries' own short retries.
MAX_TRANSIENT_RETRIES = 3


def result_path_for(job_id: UUID | str) -> str:
    return str(Path(settings.RESULTS_PATH) / "jobs" / str(job_id))


def retry_delay(retries_so_far: int) -> float:
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
    progress = ProgressTracker(
        lambda stage, percent: Job.objects.update_progress(job.id, stage=stage, progress=percent)
    )
    try:
        raise_if_cancel_requested(job_id)
        # Find and replace resolves its pattern before any data is read; the other
        # transforms generate their specification from a sample, inside the Spark run.
        pattern = (
            _resolve_pattern(job, progress)
            if job.transform_type == TransformType.REGEX_REPLACE
            else None
        )
        raise_if_cancel_requested(job_id)
        stats = _run_spark(job, pattern, output_path, progress)
    except Exception as exc:
        _handle_failure(self, job_id, exc)
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


def _handle_failure(task, job_id: str, exc: Exception) -> None:
    """Record why a job failed, or schedule a retry for transient failures."""
    if isinstance(exc, JobCancelled) or Job.objects.is_cancel_requested(job_id):
        # Any failure after a cancel request (typically Spark's "job group cancelled"
        # error) is the cancellation taking effect.
        logger.info("Job %s cancelled", job_id)
        _fail(job_id, CANCELLED_ERROR_CODE, CANCELLED_MESSAGE)
    elif isinstance(exc, SoftTimeLimitExceeded):
        logger.warning("Job %s exceeded its time limit", job_id)
        _cancel_spark_work(job_id)
        _fail(job_id, "TIMEOUT", "The job exceeded its time limit.")
    elif isinstance(exc, ProcessingError | LLMError):
        if exc.retryable and task.request.retries < MAX_TRANSIENT_RETRIES:
            logger.warning("Job %s: transient failure (%s); scheduling retry", job_id, exc.code)
            raise task.retry(
                exc=exc,
                countdown=retry_delay(task.request.retries),
                max_retries=MAX_TRANSIENT_RETRIES,
            ) from exc
        logger.info("Job %s failed: %s", job_id, exc)
        _fail(job_id, exc.code, str(exc))
    else:
        logger.error("Job %s failed unexpectedly", job_id, exc_info=exc)
        _fail(job_id, "INTERNAL_ERROR", "An unexpected error occurred while processing the job.")


def _resolve_pattern(job: Job, progress: ProgressTracker) -> str:
    """The pattern to apply: the stored one if present, otherwise generated from the
    description and saved, so a retried job never calls the LLM twice.
    """
    if job.pattern:
        return validate_pattern(job.pattern)
    if not job.nl_prompt:
        raise InvalidPatternError("The job has neither a pattern nor a description.")

    progress.enter_stage("GENERATING_REGEX")
    generated = generate_pattern(job.nl_prompt)
    Job.objects.filter(pk=job.id).update(
        pattern=generated.pattern,
        pattern_explanation=generated.explanation,
        llm_cached=generated.cached,
    )
    return generated.pattern


def _run_spark(
    job: Job, pattern: str | None, output_path: str, progress: ProgressTracker
) -> RunStats:
    # Imported lazily: PySpark exists only in the worker image, while the web process
    # imports this module to enqueue tasks.
    from apps.jobs.transform_builders import builder_for
    from processing.pipeline import run_transform

    spark = get_spark_session(spark_config_from_settings())
    job_group = str(job.id)
    monitor = SparkJobMonitor(
        spark.sparkContext,
        job_group=job_group,
        on_fraction=progress.update_fraction,
        should_cancel=lambda: Job.objects.is_cancel_requested(job_group),
        # The monitor thread uses its own database connection; close it when it stops.
        on_thread_exit=lambda: connection.close(),
    )
    with monitor:
        return run_transform(
            spark,
            source_uri=spark_uri(job.source_key),
            file_type=FileType(job.file_type),
            output_path=output_path,
            build=builder_for(job, pattern=pattern, progress=progress),
            on_stage=progress.enter_stage,
            job_group=job_group,
        )


def _cancel_spark_work(job_id: str) -> None:
    """Stop Spark jobs still running for this job, e.g. after a soft time limit."""
    try:
        from pyspark import SparkContext
    except ImportError:
        return
    context = SparkContext._active_spark_context
    if context is not None:
        context.cancelJobGroup(job_id)


def _fail(job_id: str, code: str, message: str) -> None:
    Job.objects.transition(
        job_id,
        JobStatus.FAILED,
        finished_at=timezone.now(),
        error_code=code,
        error_message=message,
    )
