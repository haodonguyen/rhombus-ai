import uuid
from unittest.mock import Mock

import pytest

from apps.jobs import services
from apps.jobs.models import Job, JobStatus
from tests.conftest import TEST_BUCKET

pytestmark = pytest.mark.django_db

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"


@pytest.fixture
def enqueue(monkeypatch) -> Mock:
    task = Mock()
    monkeypatch.setattr(services, "run_job", task)
    return task


@pytest.fixture
def people_csv(s3) -> str:
    key = "samples/people.csv"
    s3.put_object(Bucket=TEST_BUCKET, Key=key, Body=b"ID,Name,Email\n1,John Doe,john@example.com\n")
    return key


def payload(**overrides):
    return {
        # The demo connection: the bucket this deployment configures for itself.
        "connection_id": "demo",
        "source_key": "samples/people.csv",
        "target_columns": ["Email"],
        "pattern": EMAIL_PATTERN,
        "replacement_value": "REDACTED",
        **overrides,
    }


# --- submit -------------------------------------------------------------------------


def test_submit_returns_202_and_enqueues_after_commit(
    api_client, people_csv, enqueue, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post("/api/jobs/", payload(), format="json")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["error"] is None
    job = Job.objects.get(pk=body["id"])
    assert (job.file_type, job.target_columns, job.celery_task_id) == ("csv", ["Email"], body["id"])
    enqueue.apply_async.assert_called_once_with(args=[body["id"]], task_id=body["id"])


def test_submit_rejects_invalid_regex(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", payload(pattern="(unclosed"), format="json")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "Invalid regular expression" in error["details"]["pattern"][0]
    enqueue.apply_async.assert_not_called()


def test_submit_rejects_unsupported_file_type(api_client, s3, enqueue):
    response = api_client.post("/api/jobs/", payload(source_key="notes.txt"), format="json")

    assert response.status_code == 400
    assert "source_key" in response.json()["error"]["details"]


def test_submit_rejects_missing_file(api_client, s3, enqueue):
    response = api_client.post("/api/jobs/", payload(source_key="missing.csv"), format="json")

    assert response.status_code == 400
    assert "source_key" in response.json()["error"]["details"]
    assert not Job.objects.exists()


def test_submit_rejects_unknown_column(api_client, people_csv, enqueue):
    response = api_client.post(
        "/api/jobs/", payload(target_columns=["Email", "Phone"]), format="json"
    )

    assert response.status_code == 400
    assert "Phone" in response.json()["error"]["details"]["target_columns"][0]


def test_submit_rejects_reserved_column_names(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", payload(target_columns=["__row_id"]), format="json")

    assert response.status_code == 400


def test_submit_requires_at_least_one_column(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", payload(target_columns=[]), format="json")

    assert response.status_code == 400
    assert "target_columns" in response.json()["error"]["details"]


def test_submit_allows_empty_replacement(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", payload(replacement_value=""), format="json")

    assert response.status_code == 202


def test_submit_with_description_leaves_pattern_for_the_task(api_client, people_csv, enqueue):
    response = api_client.post(
        "/api/jobs/", payload(pattern="", nl_prompt="  find email addresses "), format="json"
    )

    assert response.status_code == 202
    job = Job.objects.get(pk=response.json()["id"])
    assert (job.nl_prompt, job.pattern) == ("find email addresses", "")
    assert response.json()["llm_cached"] is None


def test_submit_requires_a_description_or_a_pattern(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", payload(pattern=""), format="json")

    assert response.status_code == 400
    assert "Describe what to find" in response.json()["error"]["details"]["nl_prompt"][0]


def test_submit_rejects_description_and_pattern_together(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", payload(nl_prompt="emails"), format="json")

    assert response.status_code == 400
    assert "not both" in response.json()["error"]["details"]["nl_prompt"][0]


def test_submit_rejects_regex_syntax_java_cannot_run(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", payload(pattern=r"(?P<user>\w+)@"), format="json")

    assert response.status_code == 400
    assert "named groups" in response.json()["error"]["details"]["pattern"][0]


# --- detail -------------------------------------------------------------------------


def test_get_job(api_client, make_job):
    job = make_job(status=JobStatus.FAILED, error_code="COLUMN_NOT_FOUND", error_message="nope")

    response = api_client.get(f"/api/jobs/{job.id}/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["error"] == {"code": "COLUMN_NOT_FOUND", "message": "nope"}


def test_get_unknown_job_returns_404(api_client):
    response = api_client.get(f"/api/jobs/{uuid.uuid4()}/")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


# --- results ------------------------------------------------------------------------


@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.FAILED])
def test_results_before_success_returns_409(api_client, make_job, status):
    job = make_job(status=status)

    response = api_client.get(f"/api/jobs/{job.id}/results/")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_NOT_READY"


def test_results_returns_requested_page(api_client, make_job, write_result_parts):
    path = write_result_parts(
        [
            [(0, "John", "REDACTED", True), (1, "Jane", "none", False)],
            [(8589934592, "Al", "x", False)],
        ]
    )
    job = make_job(status=JobStatus.SUCCESS, result_path=path, row_count=3, matched_count=1)

    response = api_client.get(f"/api/jobs/{job.id}/results/", {"page": 2, "page_size": 2})

    assert response.status_code == 200
    assert response.json() == {
        "columns": ["Name", "Email"],
        "rows": [{"row_number": 3, "matched": False, "values": ["Al", "x"]}],
        "page": 2,
        "page_size": 2,
        "total_rows": 3,
        "total_pages": 2,
    }


def test_results_missing_output_returns_410(api_client, make_job, tmp_path):
    job = make_job(status=JobStatus.SUCCESS, result_path=str(tmp_path / "gone"), row_count=1)

    response = api_client.get(f"/api/jobs/{job.id}/results/")

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "RESULTS_UNAVAILABLE"


def test_submit_with_the_callers_own_connection_records_the_bucket(
    api_client, people_csv, s3_connection, enqueue, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(
            "/api/jobs/", payload(connection_id=s3_connection), format="json"
        )

    assert response.status_code == 202
    assert response.json()["source_bucket"] == TEST_BUCKET
    job = Job.objects.get(pk=response.json()["id"])
    assert job.connection_id == s3_connection
    # The keys stay in the cache; only the opaque id reaches the database.
    assert "secret" not in str(job.__dict__).lower()


def test_submit_with_an_expired_connection_is_rejected(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", payload(connection_id="gone"), format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "S3_CONNECTION_EXPIRED"
    enqueue.apply_async.assert_not_called()


# --- other transforms -----------------------------------------------------------------


def target(**overrides):
    return {
        "connection_id": "demo",
        "source_key": "samples/people.csv",
        "target_columns": ["Name", "Email"],
        **overrides,
    }


def test_submit_normalize_job(api_client, people_csv, enqueue, django_capture_on_commit_callbacks):
    body = target(transform_type="normalize_format", nl_prompt="lower-case emails")
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post("/api/jobs/", body, format="json")

    assert response.status_code == 202
    job = response.json()
    assert (job["transform_type"], job["nl_prompt"], job["pattern"], job["transform_spec"]) == (
        "normalize_format",
        "lower-case emails",
        "",
        None,
    )
    enqueue.apply_async.assert_called_once()


def test_normalize_job_requires_a_target_format(api_client, people_csv, enqueue):
    response = api_client.post(
        "/api/jobs/", target(transform_type="normalize_format"), format="json"
    )

    assert response.status_code == 400
    assert "Describe the target format" in response.json()["error"]["details"]["nl_prompt"][0]


def test_normalize_job_rejects_a_regex_or_replacement(api_client, people_csv, enqueue):
    response = api_client.post(
        "/api/jobs/", payload(transform_type="normalize_format", nl_prompt="ISO"), format="json"
    )

    assert response.status_code == 400
    assert "pattern" in response.json()["error"]["details"]


def test_submit_mask_pii_job(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", target(transform_type="mask_pii"), format="json")

    assert response.status_code == 202
    assert response.json()["transform_type"] == "mask_pii"


def test_mask_pii_job_takes_no_description(api_client, people_csv, enqueue):
    response = api_client.post(
        "/api/jobs/", target(transform_type="mask_pii", nl_prompt="emails"), format="json"
    )

    assert response.status_code == 400
    assert "transform_type" in response.json()["error"]["details"]


def test_unknown_transform_type_is_rejected(api_client, people_csv, enqueue):
    response = api_client.post("/api/jobs/", target(transform_type="translate"), format="json")

    assert response.status_code == 400
    assert "transform_type" in response.json()["error"]["details"]
