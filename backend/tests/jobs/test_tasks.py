import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from apps.jobs import tasks
from apps.jobs.models import Job, JobStatus
from apps.llm.exceptions import LLMUnavailable, PatternNotExpressible
from apps.llm.service import GeneratedPattern
from processing.errors import SourceUnavailableError
from processing.pipeline_stats import RunStats

pytestmark = pytest.mark.django_db


class Retrying(Exception):
    """Stands in for celery.exceptions.Retry."""


@pytest.fixture
def spark_ok(monkeypatch):
    calls = []

    def run_spark(job, pattern, output_path, progress):
        calls.append(pattern)
        return RunStats(row_count=3, matched_count=2)

    monkeypatch.setattr(tasks, "_run_spark", run_spark)
    return calls


@pytest.fixture
def scheduled_retries(monkeypatch):
    scheduled = []

    def retry(**kwargs):
        scheduled.append(kwargs)
        return Retrying()

    monkeypatch.setattr(tasks.run_job, "retry", retry)
    return scheduled


def fail_with(exc: BaseException):
    def raiser(*args, **kwargs):
        raise exc

    return raiser


def run(job, **options) -> None:
    tasks.run_job.apply(args=[str(job.id)], **options)
    job.refresh_from_db()


# --- raw patterns -------------------------------------------------------------------


def test_raw_pattern_job_succeeds(make_job, spark_ok):
    job = make_job(pattern=r"@example\.com")

    run(job)

    assert (job.status, job.progress, job.row_count, job.matched_count) == (
        JobStatus.SUCCESS,
        100,
        3,
        2,
    )
    assert spark_ok == [r"@example\.com"]
    assert job.llm_cached is None


def test_unsafe_raw_pattern_fails_before_spark(make_job, spark_ok):
    job = make_job(pattern=r"(a+)+b")

    run(job)

    assert (job.status, job.error_code) == (JobStatus.FAILED, "INVALID_PATTERN")
    assert spark_ok == []


# --- natural-language patterns ------------------------------------------------------


def test_description_is_turned_into_a_pattern_and_saved(make_job, spark_ok, monkeypatch):
    monkeypatch.setattr(
        tasks,
        "generate_pattern",
        lambda description: GeneratedPattern(r"(?i)\bvip\b", "Matches VIP.", cached=True),
    )
    job = make_job(pattern="", nl_prompt="the word vip")

    run(job)

    assert job.status == JobStatus.SUCCESS
    assert (job.pattern, job.pattern_explanation, job.llm_cached) == (
        r"(?i)\bvip\b",
        "Matches VIP.",
        True,
    )
    assert spark_ok == [r"(?i)\bvip\b"]


def test_stored_pattern_is_reused_instead_of_calling_the_llm(make_job, spark_ok, monkeypatch):
    monkeypatch.setattr(tasks, "generate_pattern", fail_with(AssertionError("must not call")))
    job = make_job(pattern=r"@example\.com", nl_prompt="emails at example.com")

    run(job)

    assert job.status == JobStatus.SUCCESS


def test_llm_errors_are_recorded_on_the_job(make_job, spark_ok, monkeypatch):
    monkeypatch.setattr(tasks, "generate_pattern", fail_with(PatternNotExpressible()))
    job = make_job(pattern="", nl_prompt="angry comments")

    run(job)

    assert (job.status, job.error_code, job.stage) == (
        JobStatus.FAILED,
        "PATTERN_NOT_EXPRESSIBLE",
        "GENERATING_REGEX",
    )
    assert spark_ok == []


def test_llm_not_configured_without_server_url(make_job, spark_ok):
    job = make_job(pattern="", nl_prompt="find emails")

    run(job)

    assert (job.status, job.error_code) == (JobStatus.FAILED, "LLM_NOT_CONFIGURED")


# --- transient failures -------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "error"),
    [
        ("generate_pattern", LLMUnavailable()),
        ("_run_spark", SourceUnavailableError("minio unreachable")),
    ],
)
def test_transient_failures_schedule_a_retry(
    make_job, spark_ok, scheduled_retries, monkeypatch, target, error
):
    job = make_job(pattern="" if target == "generate_pattern" else r"@example\.com")
    if target == "generate_pattern":
        job.nl_prompt = "something"
        job.save()
    monkeypatch.setattr(tasks, target, fail_with(error))

    run(job)

    assert len(scheduled_retries) == 1
    assert scheduled_retries[0]["max_retries"] == tasks.MAX_TRANSIENT_RETRIES
    assert job.status == JobStatus.RUNNING


@pytest.mark.parametrize(
    ("target", "error", "code"),
    [
        ("generate_pattern", LLMUnavailable(), "LLM_UNAVAILABLE"),
        ("_run_spark", SourceUnavailableError("minio unreachable"), "STORAGE_UNAVAILABLE"),
    ],
)
def test_transient_failures_fail_the_job_once_retries_are_exhausted(
    make_job, spark_ok, monkeypatch, target, error, code
):
    job = make_job(pattern="" if target == "generate_pattern" else r"@example\.com")
    if target == "generate_pattern":
        job.nl_prompt = "something"
        job.save()
    monkeypatch.setattr(tasks, target, fail_with(error))

    run(job, retries=tasks.MAX_TRANSIENT_RETRIES)

    assert (job.status, job.error_code) == (JobStatus.FAILED, code)


def test_retry_delay_backs_off():
    delays = [tasks.retry_delay(n) for n in range(3)]

    assert 15 <= delays[0] < 20 and 30 <= delays[1] < 35 and 60 <= delays[2] < 65


# --- cancellation and time limits ---------------------------------------------------


def test_cancel_requested_before_work_starts_skips_spark(make_job, spark_ok):
    job = make_job(cancel_requested_at=timezone.now())

    run(job)

    assert (job.status, job.error_code) == (JobStatus.FAILED, "CANCELLED")
    assert spark_ok == []


def test_spark_failure_after_a_cancel_request_is_reported_as_cancelled(make_job, monkeypatch):
    def cancelled_mid_run(job, pattern, output_path, progress):
        Job.objects.filter(pk=job.id).update(cancel_requested_at=timezone.now())
        raise RuntimeError("Job 3 cancelled part of cancelled job group")

    monkeypatch.setattr(tasks, "_run_spark", cancelled_mid_run)
    job = make_job()

    run(job)

    assert (job.status, job.error_code) == (JobStatus.FAILED, "CANCELLED")


def test_soft_time_limit_times_out_and_cancels_spark_work(make_job, monkeypatch):
    cancelled_groups = []
    monkeypatch.setattr(tasks, "_run_spark", fail_with(SoftTimeLimitExceeded()))
    monkeypatch.setattr(tasks, "_cancel_spark_work", cancelled_groups.append)
    job = make_job()

    run(job)

    assert (job.status, job.error_code) == (JobStatus.FAILED, "TIMEOUT")
    assert cancelled_groups == [str(job.id)]


# --- general failures ---------------------------------------------------------------


def test_unexpected_errors_are_recorded_without_leaking_details(make_job, monkeypatch):
    monkeypatch.setattr(tasks, "_run_spark", fail_with(RuntimeError("secret internals")))
    job = make_job()

    run(job)

    assert (job.status, job.error_code) == (JobStatus.FAILED, "INTERNAL_ERROR")
    assert "secret internals" not in job.error_message


@pytest.mark.parametrize("status", [JobStatus.SUCCESS, JobStatus.FAILED])
def test_finished_jobs_are_not_rerun(make_job, monkeypatch, status):
    monkeypatch.setattr(tasks, "_run_spark", fail_with(AssertionError("must not run")))
    job = make_job(status=status, progress=100)

    run(job)

    assert (job.status, job.started_at) == (status, None)


def test_result_path_is_scoped_to_the_job(settings):
    settings.RESULTS_PATH = "/data/results"

    assert tasks.result_path_for("abc") == "/data/results/jobs/abc"


@pytest.mark.parametrize("transform_type", ["normalize_format", "mask_pii"])
def test_spec_transforms_do_not_resolve_a_regex(make_job, spark_ok, monkeypatch, transform_type):
    monkeypatch.setattr(tasks, "generate_pattern", fail_with(AssertionError("must not call")))
    job = make_job(
        transform_type=transform_type, pattern="", replacement_value="", nl_prompt="ISO dates"
    )

    run(job)

    assert job.status == JobStatus.SUCCESS
    assert spark_ok == [None]
