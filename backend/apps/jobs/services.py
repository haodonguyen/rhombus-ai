"""Job use cases for the API layer. Submission does no heavy work: it validates, persists
and enqueues, then returns.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.files import services as file_services
from apps.files.exceptions import PreviewUnavailable, StoredFileNotFound
from apps.jobs.exceptions import InvalidJobRequest, JobNotCancellable, JobNotFound, JobNotReady
from apps.jobs.models import CANCELLED_ERROR_CODE, CANCELLED_MESSAGE, Job, JobStatus
from apps.jobs.results import ResultsPage, read_results_page
from apps.jobs.tasks import run_job
from config.celery import app as celery_app
from processing.schema import find_missing_columns

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobRequest:
    """A validated submission; which optional fields apply depends on the transform type."""

    transform_type: str
    source_key: str
    target_columns: list[str]
    nl_prompt: str = ""
    pattern: str = ""
    replacement_value: str = ""


def submit_job(request: JobRequest) -> Job:
    file_type = file_services.get_file_type(request.source_key)
    validate_source(request.source_key, request.target_columns)

    job = Job.objects.create(
        transform_type=request.transform_type,
        source_key=request.source_key,
        file_type=file_type,
        target_columns=request.target_columns,
        nl_prompt=request.nl_prompt,
        pattern=request.pattern,
        replacement_value=request.replacement_value,
    )
    # The task id is the job id, so cancellation can revoke by job id.
    job.celery_task_id = str(job.id)
    job.save(update_fields=["celery_task_id"])
    # Enqueue only after commit, so the worker never looks up a job that isn't saved yet.
    transaction.on_commit(lambda: run_job.apply_async(args=[str(job.id)], task_id=str(job.id)))
    return job


def validate_source(key: str, columns: list[str]) -> None:
    """Reject missing files and unknown columns up front, using the cheap preview reader.

    Files too large to preview are not checked here; the Spark job checks them again anyway.
    """
    try:
        preview = file_services.get_file_preview(key)
    except StoredFileNotFound as exc:
        raise InvalidJobRequest(details={"source_key": [exc.message]}) from exc
    except PreviewUnavailable:
        return

    missing = find_missing_columns(preview.columns, columns)
    if missing:
        raise InvalidJobRequest(
            details={"target_columns": [f"Column(s) not found in file: {', '.join(missing)}"]}
        )


def get_job(job_id: UUID) -> Job:
    try:
        return Job.objects.get(pk=job_id)
    except Job.DoesNotExist as exc:
        raise JobNotFound() from exc


def cancel_job(job_id: UUID) -> Job:
    """Cancel a job.

    A queued job is failed as cancelled immediately. A running job is flagged, and the
    worker stops its Spark work within a few seconds. Finished jobs cannot be cancelled.
    """
    job = get_job(job_id)
    now = timezone.now()
    cancelled_while_queued = Job.objects.transition(
        job.id,
        JobStatus.FAILED,
        only_from=[JobStatus.QUEUED],
        finished_at=now,
        cancel_requested_at=now,
        error_code=CANCELLED_ERROR_CODE,
        error_message=CANCELLED_MESSAGE,
    )
    if cancelled_while_queued:
        # The worker only starts QUEUED jobs, so it would skip this one anyway; revoking
        # also removes the message from the queue.
        revoke_task(job.celery_task_id)
    elif not Job.objects.request_cancel(job.id):
        raise JobNotCancellable()
    job.refresh_from_db()
    return job


def revoke_task(task_id: str) -> None:
    if not task_id:
        return
    try:
        celery_app.control.revoke(task_id)
    except Exception:
        # The database already records the cancellation; a broker hiccup must not fail it.
        logger.warning("Could not revoke Celery task %s", task_id, exc_info=True)


def get_job_results(job_id: UUID, page: int, page_size: int) -> ResultsPage:
    job = get_job(job_id)
    if job.status != JobStatus.SUCCESS:
        raise JobNotReady()
    return read_results_page(job.result_path, job.row_count or 0, page, page_size)
