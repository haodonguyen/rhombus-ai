"""User-supplied S3 connections.

The browser sends an access key and secret key once. They are encrypted with a key derived
from Django's SECRET_KEY, held in Redis under a random connection id with a short lifetime,
and never written to the database or the logs. Every later request — listing files,
previewing one, running a job — carries only the opaque id.

The demo connection is the one exception: it is the bucket configured in the environment
(MinIO in development), so the app can be tried without creating AWS credentials.
"""

import base64
import hashlib
import json
import logging
import secrets
from dataclasses import asdict, dataclass

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.cache import cache

from apps.files.exceptions import S3ConnectionExpired

logger = logging.getLogger(__name__)

DEMO_CONNECTION_ID = "demo"
CACHE_PREFIX = "s3conn:"
ID_BYTES = 24


@dataclass(frozen=True)
class S3Connection:
    """Everything needed to reach one bucket. Treat as secret."""

    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str
    endpoint_url: str = ""

    def __repr__(self) -> str:  # pragma: no cover - defensive, keeps keys out of tracebacks
        return f"S3Connection(bucket={self.bucket!r}, region={self.region!r})"


def _fernet() -> Fernet:
    digest = hashlib.sha256(f"s3-connection:{settings.SECRET_KEY}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def store(connection: S3Connection) -> str:
    """Encrypt a connection into the cache and return its id."""
    connection_id = secrets.token_urlsafe(ID_BYTES)
    token = _fernet().encrypt(json.dumps(asdict(connection)).encode())
    cache.set(CACHE_PREFIX + connection_id, token.decode(), timeout=settings.S3_CONNECTION_TTL)
    return connection_id


def load(connection_id: str) -> S3Connection:
    """The connection for an id, or S3ConnectionExpired if it is unknown or has expired."""
    if connection_id == DEMO_CONNECTION_ID:
        demo = demo_connection()
        if demo is None:
            raise S3ConnectionExpired("The demo bucket is not available on this deployment.")
        return demo

    token = cache.get(CACHE_PREFIX + connection_id)
    if not token:
        raise S3ConnectionExpired()
    try:
        data = json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError) as exc:
        # Only reachable if SECRET_KEY changed or the entry was tampered with.
        logger.warning("Stored S3 connection could not be decrypted")
        raise S3ConnectionExpired() from exc
    return S3Connection(**data)


def forget(connection_id: str) -> None:
    if connection_id != DEMO_CONNECTION_ID:
        cache.delete(CACHE_PREFIX + connection_id)


def demo_connection() -> S3Connection | None:
    """The environment's own bucket, when the deployment offers it as a demo."""
    if not settings.S3_DEMO_ENABLED or not settings.S3_BUCKET:
        return None
    return S3Connection(
        bucket=settings.S3_BUCKET,
        region=settings.AWS_REGION,
        access_key_id=settings.AWS_ACCESS_KEY_ID,
        secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        endpoint_url=settings.S3_ENDPOINT_URL,
    )
