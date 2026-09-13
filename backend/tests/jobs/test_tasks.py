import pytest
from celery.exceptions import SoftTimeLimitExceeded

from apps.jobs import tasks
from apps.jobs.models import JobStatus
from apps.llm.exceptions import LLMRefused, LLMUnavailable
from apps.llm.service import GeneratedPattern
from processing.pipeline_stats import RunStats

pytestmark = pytest.mark.django_db


class Retrying(Exception):
    """Stands in for celery.exceptions.Retry."""


@pytest.fixture
def spark_ok(monkeypatch):
    calls = []

    def run_spark(job, pattern, output_path):
        calls.append(pattern)
        return RunStats(row_count=3, matched_count=2)

    monkeypatch.setattr(tasks, "_run_spark", run_spark)
    return calls


def fail_with(exc: BaseException):
    def raiser(*args, **kwargs):
        raise exc

    return raiser


# --- raw patterns -------------------------------------------------------------------


def test_raw_pattern_job_succeeds(make_job, spark_ok):
    job = make_job(pattern=r"@example\.com")

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert (job.status, job.row_count, job.matched_count) == (JobStatus.SUCCESS, 3, 2)
    assert spark_ok == [r"@example\.com"]
    assert job.llm_cached is None


def test_unsafe_raw_pattern_fails_before_spark(make_job, spark_ok):
    job = make_job(pattern=r"(a+)+b")

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
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

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
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

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert job.status == JobStatus.SUCCESS


def test_llm_errors_are_recorded_on_the_job(make_job, spark_ok, monkeypatch):
    monkeypatch.setattr(tasks, "generate_pattern", fail_with(LLMRefused()))
    job = make_job(pattern="", nl_prompt="something")

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert (job.status, job.error_code) == (JobStatus.FAILED, "LLM_REFUSED")
    assert job.stage == "GENERATING_REGEX"
    assert spark_ok == []


def test_llm_outage_schedules_a_retry(make_job, spark_ok, monkeypatch):
    monkeypatch.setattr(tasks, "generate_pattern", fail_with(LLMUnavailable()))
    retries = []

    def retry(**kwargs):
        retries.append(kwargs)
        return Retrying()

    monkeypatch.setattr(tasks.run_job, "retry", retry)
    job = make_job(pattern="", nl_prompt="something")

    result = tasks.run_job.apply(args=[str(job.id)])

    assert isinstance(result.result, Retrying)
    assert retries and retries[0]["max_retries"] == tasks.LLM_MAX_TASK_RETRIES
    job.refresh_from_db()
    assert job.status == JobStatus.RUNNING


def test_llm_outage_fails_the_job_once_retries_are_exhausted(make_job, spark_ok, monkeypatch):
    monkeypatch.setattr(tasks, "generate_pattern", fail_with(LLMUnavailable()))
    job = make_job(pattern="", nl_prompt="something")

    tasks.run_job.apply(args=[str(job.id)], retries=tasks.LLM_MAX_TASK_RETRIES)

    job.refresh_from_db()
    assert (job.status, job.error_code) == (JobStatus.FAILED, "LLM_UNAVAILABLE")


def test_llm_not_configured_without_api_key(make_job, spark_ok):
    job = make_job(pattern="", nl_prompt="find emails")

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert (job.status, job.error_code) == (JobStatus.FAILED, "LLM_NOT_CONFIGURED")


# --- general failures ---------------------------------------------------------------


def test_unexpected_errors_are_recorded_without_leaking_details(make_job, monkeypatch):
    monkeypatch.setattr(tasks, "_run_spark", fail_with(RuntimeError("secret internals")))
    job = make_job()

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.error_code == "INTERNAL_ERROR"
    assert "secret internals" not in job.error_message


def test_soft_time_limit_marks_job_timed_out(make_job, monkeypatch):
    monkeypatch.setattr(tasks, "_run_spark", fail_with(SoftTimeLimitExceeded()))
    job = make_job()

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert (job.status, job.error_code) == (JobStatus.FAILED, "TIMEOUT")


@pytest.mark.parametrize("status", [JobStatus.SUCCESS, JobStatus.FAILED])
def test_finished_jobs_are_not_rerun(make_job, monkeypatch, status):
    monkeypatch.setattr(tasks, "_run_spark", fail_with(AssertionError("must not run")))
    job = make_job(status=status, progress=100)

    tasks.run_job.apply(args=[str(job.id)])

    job.refresh_from_db()
    assert (job.status, job.started_at) == (status, None)


def test_result_path_is_scoped_to_the_job(settings):
    settings.RESULTS_PATH = "/data/results"

    assert tasks.result_path_for("abc") == "/data/results/jobs/abc"


def test_llm_retry_delay_backs_off():
    delays = [tasks.llm_retry_delay(n) for n in range(3)]

    assert 15 <= delays[0] < 20 and 30 <= delays[1] < 35 and 60 <= delays[2] < 65
