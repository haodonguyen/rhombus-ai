import uuid
from typing import Any

from django.db import models
from django.utils import timezone

from processing.file_types import FileType


class JobStatus(models.TextChoices):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


TERMINAL_STATUSES = frozenset({JobStatus.SUCCESS, JobStatus.FAILED})

# Statuses a job may move *from* to reach each target status; anything else is rejected.
# RUNNING -> RUNNING lets a task redelivered after a worker crash (acks_late) restart the
# job; the run overwrites its own output, so this is safe.
ALLOWED_SOURCE_STATUSES: dict[str, frozenset[str]] = {
    JobStatus.RUNNING: frozenset({JobStatus.QUEUED, JobStatus.RUNNING}),
    JobStatus.SUCCESS: frozenset({JobStatus.RUNNING}),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED, JobStatus.RUNNING}),
}


class TransformType(models.TextChoices):
    REGEX_REPLACE = "regex_replace", "Regex replace"


class JobQuerySet(models.QuerySet):
    def transition(self, job_id: Any, status: JobStatus, **fields: Any) -> bool:
        """Atomically move a job to `status` and set `fields`, if the current status allows.

        A single conditional UPDATE, so concurrent writers cannot race each other. Returns
        False and changes nothing when the transition is not allowed. This is the only
        place job status changes.
        """
        updated = self.filter(pk=job_id, status__in=ALLOWED_SOURCE_STATUSES[status]).update(
            status=status, updated_at=timezone.now(), **fields
        )
        return updated == 1

    def update_progress(self, job_id: Any, *, stage: str, progress: int) -> None:
        self.filter(pk=job_id, status=JobStatus.RUNNING).update(
            stage=stage, progress=progress, updated_at=timezone.now()
        )


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(
        max_length=16, choices=JobStatus.choices, default=JobStatus.QUEUED, db_index=True
    )
    stage = models.CharField(max_length=32, blank=True, default="")
    progress = models.PositiveSmallIntegerField(default=0)

    source_key = models.CharField(max_length=1024)
    file_type = models.CharField(max_length=8, choices=[(t.value, t.name) for t in FileType])
    target_columns = models.JSONField(default=list)
    transform_type = models.CharField(
        max_length=32, choices=TransformType.choices, default=TransformType.REGEX_REPLACE
    )
    pattern = models.TextField()
    replacement_value = models.TextField(blank=True, default="")

    result_path = models.CharField(max_length=1024, blank=True, default="")
    row_count = models.BigIntegerField(null=True, blank=True)
    matched_count = models.BigIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    celery_task_id = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    objects = JobQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Job {self.id} ({self.status})"
