"""S3 access: client construction, URIs and translation of boto errors to domain errors."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from apps.files.connections import S3Connection
from apps.files.exceptions import (
    S3BucketNotFound,
    S3CredentialsInvalid,
    StorageUnavailable,
    StoredFileNotFound,
)
from processing.spark_session import s3a_uri

logger = logging.getLogger(__name__)

NOT_FOUND_ERROR_CODES = frozenset({"404", "NoSuchKey", "NotFound"})
# S3 answers with these when the key pair is wrong, or may not touch this bucket.
CREDENTIAL_ERROR_CODES = frozenset(
    {"InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied", "403", "InvalidToken"}
)
MISSING_BUCKET_ERROR_CODES = frozenset({"NoSuchBucket"})


def get_s3_client(connection: S3Connection):
    # Empty credentials fall through to boto3's default chain (e.g. an IAM role).
    return boto3.client(
        "s3",
        endpoint_url=connection.endpoint_url or None,
        region_name=connection.region or None,
        aws_access_key_id=connection.access_key_id or None,
        aws_secret_access_key=connection.secret_access_key or None,
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
        if error_code in CREDENTIAL_ERROR_CODES:
            # Logged without the bucket or key: the caller's own message is enough here.
            logger.info("S3 rejected the supplied credentials (%s)", error_code)
            raise S3CredentialsInvalid() from exc
        if error_code in MISSING_BUCKET_ERROR_CODES:
            raise S3BucketNotFound() from exc
        logger.warning("S3 request failed (%s)", error_code, exc_info=True)
        raise StorageUnavailable() from exc
    except BotoCoreError as exc:
        logger.warning("S3 request failed", exc_info=True)
        raise StorageUnavailable() from exc


def spark_uri(connection: S3Connection, key: str) -> str:
    return s3a_uri(connection.bucket, key)
