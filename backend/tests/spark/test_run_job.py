from pathlib import Path

import pytest

from apps.jobs import tasks
from apps.jobs.models import JobStatus, TransformType
from processing.schema import ROW_ID_COLUMN
from tests.llm_fakes import make_date_normalization, make_pii_classification
from tests.spark.conftest import BRIEF_CSV, EMAIL_PATTERN

pytestmark = pytest.mark.django_db

CUSTOMERS_CSV = (
    "ID,Name,Email,SignupDate\n"
    "1,John Doe,john.doe@example.com,2020-04-24\n"
    "2,Jane Smith,jane_smith@domain.com,25/10/2018\n"
    '3,Alice Brown,alice.brown@website.org,"Nov 22, 2021"\n'
)


@pytest.fixture
def local_source(monkeypatch, settings, tmp_path, write_csv):
    """Point the task at a local CSV instead of S3 and write results under tmp_path."""
    settings.RESULTS_PATH = str(tmp_path / "results")

    def use(content: str) -> str:
        path = write_csv(content)
        monkeypatch.setattr(tasks, "spark_uri", lambda connection, key: path)
        return path

    return use


def run(job):
    tasks.run_job.apply(args=[str(job.id)])
    job.refresh_from_db()
    return job


def output_values(spark, job, column):
    rows = spark.read.parquet(job.result_path).orderBy(ROW_ID_COLUMN).collect()
    return [row[column] for row in rows]


# --- find and replace -----------------------------------------------------------------


def test_run_job_succeeds_and_records_stats(spark, local_source, make_job):
    local_source(BRIEF_CSV)

    job = run(make_job(pattern=EMAIL_PATTERN))

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
    local_source(BRIEF_CSV)

    job = run(make_job(target_columns=["Phone"]))

    assert job.status == JobStatus.FAILED
    assert job.error_code == "COLUMN_NOT_FOUND"
    assert "Phone" in job.error_message
    assert job.finished_at is not None


# --- format normalization -------------------------------------------------------------


def make_normalize_job(make_job, **overrides):
    fields = {
        "transform_type": TransformType.NORMALIZE_FORMAT,
        "target_columns": ["SignupDate"],
        "pattern": "",
        "replacement_value": "",
        "nl_prompt": "dates as YYYY-MM-DD",
        **overrides,
    }
    return make_job(**fields)


def test_normalize_job_asks_the_llm_once_and_saves_the_spec(
    spark, local_source, make_job, fake_llm
):
    local_source(CUSTOMERS_CSV)
    fake_llm.respond_with(make_date_normalization())

    job = run(make_normalize_job(make_job))

    assert job.status == JobStatus.SUCCESS, job.error_message
    assert output_values(spark, job, "SignupDate") == ["2020-04-24", "2018-10-25", "2021-11-22"]
    assert (job.matched_count, job.llm_cached) == (3, False)
    assert job.transform_spec["input_formats"] == make_date_normalization().input_formats
    assert job.pattern_explanation == "Writes dates as YYYY-MM-DD."
    [(_, user, _)] = fake_llm.calls
    assert '"25/10/2018"' in user


def test_retried_job_reuses_its_saved_spec(spark, local_source, make_job, fake_llm):
    local_source(CUSTOMERS_CSV)

    job = run(make_normalize_job(make_job, transform_spec=make_date_normalization().model_dump()))

    assert job.status == JobStatus.SUCCESS, job.error_message
    assert fake_llm.calls == []


def test_infeasible_normalization_fails_the_job(spark, local_source, make_job, fake_llm):
    local_source(CUSTOMERS_CSV)
    fake_llm.respond_with(
        make_date_normalization(feasible=False, explanation="Needs exchange rates.")
    )

    job = run(make_normalize_job(make_job, nl_prompt="prices in euros"))

    assert (job.status, job.error_code, job.stage) == (
        JobStatus.FAILED,
        "NORMALIZATION_NOT_POSSIBLE",
        "GENERATING_SPEC",
    )
    assert "exchange rates" in job.error_message


# --- PII masking ----------------------------------------------------------------------


def test_mask_pii_job_masks_the_detected_columns(spark, local_source, make_job, fake_llm):
    local_source(CUSTOMERS_CSV)
    fake_llm.respond_with(
        make_pii_classification({"ID": ["none"], "Name": ["person_name"], "Email": ["email"]})
    )

    job = run(
        make_job(
            transform_type=TransformType.MASK_PII,
            target_columns=["ID", "Name", "Email"],
            pattern="",
            replacement_value="",
        )
    )

    assert job.status == JobStatus.SUCCESS, job.error_message
    assert output_values(spark, job, "ID") == ["1", "2", "3"]
    assert output_values(spark, job, "Name") == ["J. D.", "J. S.", "A. B."]
    assert output_values(spark, job, "Email") == [
        "j***@example.com",
        "j***@domain.com",
        "a***@website.org",
    ]
    assert job.matched_count == 3
    assert job.transform_spec["columns"][1] == {"column": "Name", "pii_types": ["person_name"]}


# --- credentials --------------------------------------------------------------------


def test_expired_connection_fails_the_job_with_its_own_code(local_source, make_job):
    local_source(BRIEF_CSV)
    job = make_job(pattern=r"@example\.com", connection_id="no-longer-stored")

    run(job)

    assert job.status == JobStatus.FAILED
    assert job.error_code == "S3_CONNECTION_EXPIRED"
    assert "Connect again" in job.error_message


def test_the_jobs_own_credentials_reach_spark(local_source, make_job, monkeypatch):
    from apps.files import connections

    connection_id = connections.store(
        connections.S3Connection(
            bucket="customer-bucket",
            region="ap-southeast-2",
            access_key_id="AKIAUSER",
            secret_access_key="user-secret",
        )
    )
    applied = {}
    monkeypatch.setattr(
        tasks,
        "apply_s3_credentials",
        lambda spark, config: applied.update(
            key=config.aws_access_key_id,
            secret=config.aws_secret_access_key,
            region=config.aws_region,
        ),
    )
    local_source(BRIEF_CSV)
    job = make_job(pattern=r"@example\.com", connection_id=connection_id)

    run(job)

    assert job.status == JobStatus.SUCCESS
    assert applied == {"key": "AKIAUSER", "secret": "user-secret", "region": "ap-southeast-2"}
