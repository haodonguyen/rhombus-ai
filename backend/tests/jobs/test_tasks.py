import pytest
from celery.exceptions import SoftTimeLimitExceeded

from apps.jobs import tasks
from apps.jobs.models import JobStatus

pytestmark = pytest.mark.django_db


def failing_execute(exc: BaseException):
    def execute(job, output_path):
        raise exc

    return execute


def test_unexpected_errors_are_recorded_without_leaking_details(make_job, monkeypatch):
    monkeypatch.setattr(tasks, "_execute", failing_execute(RuntimeError("secret internals")))
    job = make_job()

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.error_code == "INTERNAL_ERROR"
    assert "secret internals" not in job.error_message


def test_soft_time_limit_marks_job_timed_out(make_job, monkeypatch):
    monkeypatch.setattr(tasks, "_execute", failing_execute(SoftTimeLimitExceeded()))
    job = make_job()

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert (job.status, job.error_code) == (JobStatus.FAILED, "TIMEOUT")


@pytest.mark.parametrize("status", [JobStatus.SUCCESS, JobStatus.FAILED])
def test_finished_jobs_are_not_rerun(make_job, monkeypatch, status):
    monkeypatch.setattr(tasks, "_execute", failing_execute(AssertionError("must not run")))
    job = make_job(status=status, progress=100)

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert (job.status, job.started_at) == (status, None)


def test_result_path_is_scoped_to_the_job(settings):
    settings.RESULTS_PATH = "/data/results"

    assert tasks.result_path_for("abc") == "/data/results/jobs/abc"
