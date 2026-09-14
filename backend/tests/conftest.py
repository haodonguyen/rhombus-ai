import importlib.util

import boto3
import pytest
from moto import mock_aws
from rest_framework.test import APIClient

# PySpark is installed only in the worker image. Without it, skip the Spark suite; run the
# full suite with `docker compose exec worker pytest`.
if importlib.util.find_spec("pyspark") is None:
    collect_ignore = ["spark"]

TEST_BUCKET = "test-bucket"


@pytest.fixture(autouse=True)
def isolated_services(settings):
    """Every test gets an empty in-memory cache and no LLM server."""
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.LLM_BASE_URL = ""
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def make_job(db):
    # Imported lazily: this conftest loads before pytest-django configures Django.
    from apps.jobs.models import Job

    def factory(**overrides) -> Job:
        fields = {
            "source_key": "samples/people.csv",
            "file_type": "csv",
            "target_columns": ["Email"],
            "pattern": r"@example\.com",
            "replacement_value": "REDACTED",
            **overrides,
        }
        return Job.objects.create(**fields)

    return factory


@pytest.fixture
def s3(settings):
    """An in-memory S3 (moto) with an empty bucket, wired into Django settings."""
    settings.S3_ENDPOINT_URL = None
    settings.S3_BUCKET = TEST_BUCKET
    settings.AWS_REGION = "us-east-1"
    settings.AWS_ACCESS_KEY_ID = "testing"
    settings.AWS_SECRET_ACCESS_KEY = "testing"
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=TEST_BUCKET)
        yield client
