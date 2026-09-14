"""Cooperative cancellation: long-running work checks for a cancel request between steps."""

from uuid import UUID

from apps.jobs.models import Job


class JobCancelled(Exception):
    """Raised between steps once the user has asked to cancel the job."""


def raise_if_cancel_requested(job_id: UUID | str) -> None:
    if Job.objects.is_cancel_requested(job_id):
        raise JobCancelled()
