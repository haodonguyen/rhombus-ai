import uuid
from unittest.mock import Mock

import pytest

from apps.jobs import services
from apps.jobs.models import Job, JobStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def revoke(monkeypatch) -> Mock:
    mock = Mock()
    monkeypatch.setattr(services, "revoke_task", mock)
    return mock


def test_cancelling_a_queued_job_fails_it_immediately(api_client, make_job, revoke):
    job = make_job(celery_task_id="task-1")

    response = api_client.post(f"/api/jobs/{job.id}/cancel/")

    assert response.status_code == 202
    body = response.json()
    assert (body["status"], body["error"]["code"], body["cancel_requested"]) == (
        "FAILED",
        "CANCELLED",
        True,
    )
    revoke.assert_called_once_with("task-1")


def test_cancelling_a_running_job_flags_it_for_the_worker(api_client, make_job, revoke):
    job = make_job(status=JobStatus.RUNNING)

    response = api_client.post(f"/api/jobs/{job.id}/cancel/")

    assert response.status_code == 202
    assert (response.json()["status"], response.json()["cancel_requested"]) == ("RUNNING", True)
    assert Job.objects.is_cancel_requested(job.id)
    revoke.assert_not_called()


def test_cancelling_a_running_job_twice_keeps_the_first_request(api_client, make_job, revoke):
    job = make_job(status=JobStatus.RUNNING)
    api_client.post(f"/api/jobs/{job.id}/cancel/")
    job.refresh_from_db()
    first_requested_at = job.cancel_requested_at

    response = api_client.post(f"/api/jobs/{job.id}/cancel/")

    assert response.status_code == 202
    job.refresh_from_db()
    assert job.cancel_requested_at == first_requested_at


@pytest.mark.parametrize("status", [JobStatus.SUCCESS, JobStatus.FAILED])
def test_finished_jobs_cannot_be_cancelled(api_client, make_job, revoke, status):
    job = make_job(status=status)

    response = api_client.post(f"/api/jobs/{job.id}/cancel/")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_NOT_CANCELLABLE"


def test_cancelling_an_unknown_job_returns_404(api_client, revoke):
    response = api_client.post(f"/api/jobs/{uuid.uuid4()}/cancel/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_broker_errors_while_revoking_do_not_fail_the_request(api_client, make_job, monkeypatch):
    monkeypatch.setattr(
        services.celery_app.control, "revoke", Mock(side_effect=ConnectionError("broker down"))
    )
    job = make_job(celery_task_id="task-1")

    response = api_client.post(f"/api/jobs/{job.id}/cancel/")

    assert response.status_code == 202
    assert response.json()["error"]["code"] == "CANCELLED"
