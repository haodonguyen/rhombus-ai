import pytest

from apps.jobs.models import Job, JobStatus

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        (JobStatus.QUEUED, JobStatus.RUNNING, True),
        (JobStatus.QUEUED, JobStatus.FAILED, True),
        (JobStatus.QUEUED, JobStatus.SUCCESS, False),
        (JobStatus.RUNNING, JobStatus.RUNNING, True),
        (JobStatus.RUNNING, JobStatus.SUCCESS, True),
        (JobStatus.RUNNING, JobStatus.FAILED, True),
        (JobStatus.SUCCESS, JobStatus.RUNNING, False),
        (JobStatus.SUCCESS, JobStatus.FAILED, False),
        (JobStatus.FAILED, JobStatus.RUNNING, False),
        (JobStatus.FAILED, JobStatus.SUCCESS, False),
    ],
)
def test_transition_rules(make_job, current, target, allowed):
    job = make_job(status=current)

    assert Job.objects.transition(job.id, target) is allowed

    job.refresh_from_db()
    assert job.status == (target if allowed else current)


def test_transition_sets_extra_fields(make_job):
    job = make_job()

    Job.objects.transition(job.id, JobStatus.FAILED, error_code="TIMEOUT")

    job.refresh_from_db()
    assert job.error_code == "TIMEOUT"


def test_progress_updates_only_running_jobs(make_job):
    running = make_job(status=JobStatus.RUNNING)
    finished = make_job(status=JobStatus.SUCCESS, progress=100)

    Job.objects.update_progress(running.id, stage="TRANSFORMING", progress=30)
    Job.objects.update_progress(finished.id, stage="TRANSFORMING", progress=30)

    running.refresh_from_db()
    finished.refresh_from_db()
    assert (running.stage, running.progress) == ("TRANSFORMING", 30)
    assert (finished.stage, finished.progress) == ("", 100)
