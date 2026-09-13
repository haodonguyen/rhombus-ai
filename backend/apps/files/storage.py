"""S3 access: client construction, URIs and translation of boto errors to domain errors."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from apps.files.exceptions import StorageUnavailable, StoredFileNotFound
from processing.spark_session import s3a_uri

logger = logging.getLogger(__name__)

NOT_FOUND_ERROR_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


def get_s3_client():
    # Empty credentials fall through to boto3's default chain (e.g. an IAM role).
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        config=Config(
            connect_timeout=3, read_timeout=10, retries={"max_attempts": 2, "mode": "standard"}
        ),
    )


@contextmanager
def translate_s3_errors(key: str | None = None) -> Iterator[None]:
    """Raise StoredFileNotFound for a missing `key`, StorageUnavailable for anything else."""
    try:
        yield
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if key is not None and error_code in NOT_FOUND_ERROR_CODES:
            raise StoredFileNotFound(f"File not found: {key}") from exc
        logger.warning("S3 request failed (%s)", error_code, exc_info=True)
        raise StorageUnavailable() from exc
    except BotoCoreError as exc:
        logger.warning("S3 request failed", exc_info=True)
        raise StorageUnavailable() from exc


def spark_uri(key: str) -> str:
    return s3a_uri(settings.S3_BUCKET, key)
