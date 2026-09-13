from pathlib import Path

import pytest

from apps.jobs import tasks
from apps.jobs.models import JobStatus
from tests.spark.conftest import BRIEF_CSV, EMAIL_PATTERN

pytestmark = pytest.mark.django_db


@pytest.fixture
def local_source(monkeypatch, settings, tmp_path, write_csv) -> str:
    """Point the task at a local CSV instead of S3 and write results under tmp_path."""
    settings.RESULTS_PATH = str(tmp_path / "results")
    path = write_csv(BRIEF_CSV)
    monkeypatch.setattr(tasks, "spark_uri", lambda key: path)
    return path


def test_run_job_succeeds_and_records_stats(spark, local_source, make_job):
    job = make_job(pattern=EMAIL_PATTERN)

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert job.status == JobStatus.SUCCESS, job.error_message
    assert (job.progress, job.stage, job.row_count, job.matched_count) == (
        100,
        "FINALIZING",
        3,
        3,
    )
    assert job.started_at is not None and job.finished_at is not None
    assert Path(job.result_path, "_SUCCESS").exists()


def test_run_job_records_processing_errors(spark, local_source, make_job):
    job = make_job(target_columns=["Phone"])

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.error_code == "COLUMN_NOT_FOUND"
    assert "Phone" in job.error_message
    assert job.finished_at is not None
