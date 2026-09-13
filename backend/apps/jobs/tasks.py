"""Celery tasks. Orchestration only: status changes and error mapping. Spark work lives in
`processing/`.
"""

import logging
from pathlib import Path
from uuid import UUID

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from apps.core.spark import spark_config_from_settings
from apps.files.storage import spark_uri
from apps.jobs.models import Job, JobStatus
from processing.errors import ProcessingError
from processing.file_types import FileType
from processing.spark_session import get_spark_session

logger = logging.getLogger(__name__)

# Coarse progress reported at each stage boundary.
STAGE_PROGRESS = {"LOADING": 10, "TRANSFORMING": 30, "FINALIZING": 90}


def result_path_for(job_id: UUID | str) -> str:
    return str(Path(settings.RESULTS_PATH) / "jobs" / str(job_id))


@shared_task(name="jobs.run_job")
def run_job(job_id: str) -> None:
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
        stats = _execute(job, output_path)
    except ProcessingError as exc:
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


def _execute(job: Job, output_path: str):
    # Imported lazily: PySpark exists only in the worker image, while the web process
    # imports this module to enqueue tasks.
    from processing.pipeline import RegexReplaceSpec, run_regex_replace

    spec = RegexReplaceSpec(
        source_uri=spark_uri(job.source_key),
        file_type=FileType(job.file_type),
        columns=tuple(job.target_columns),
        pattern=job.pattern,
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
