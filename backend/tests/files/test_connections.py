"""Storing, reading and expiring a caller's S3 credentials."""

import pytest
from django.core.cache import cache

from apps.files import connections
from apps.files.exceptions import S3ConnectionExpired

pytestmark = pytest.mark.django_db

CREDENTIALS = connections.S3Connection(
    bucket="customer-bucket",
    region="ap-southeast-2",
    access_key_id="AKIAEXAMPLE",
    secret_access_key="secret-value",
)


def test_stored_connection_is_returned_unchanged():
    connection_id = connections.store(CREDENTIALS)

    assert connections.load(connection_id) == CREDENTIALS


def test_ids_are_unguessable_and_unique():
    first = connections.store(CREDENTIALS)
    second = connections.store(CREDENTIALS)

    assert first != second
    assert len(first) >= 32


def test_keys_are_not_readable_in_the_cache():
    connection_id = connections.store(CREDENTIALS)

    stored = cache.get(connections.CACHE_PREFIX + connection_id)

    assert "secret-value" not in stored
    assert "AKIAEXAMPLE" not in stored


def test_repr_does_not_leak_the_secret():
    assert "secret-value" not in repr(CREDENTIALS)


def test_unknown_id_is_reported_as_expired():
    with pytest.raises(S3ConnectionExpired):
        connections.load("never-stored")


def test_forgotten_connection_cannot_be_loaded():
    connection_id = connections.store(CREDENTIALS)

    connections.forget(connection_id)

    with pytest.raises(S3ConnectionExpired):
        connections.load(connection_id)


def test_entry_written_with_another_secret_key_is_rejected(settings):
    connection_id = connections.store(CREDENTIALS)
    settings.SECRET_KEY = "a-different-secret-key"

    with pytest.raises(S3ConnectionExpired):
        connections.load(connection_id)


def test_connection_expires_after_the_configured_lifetime(settings, monkeypatch):
    settings.S3_CONNECTION_TTL = 60
    captured = {}
    original = cache.set
    monkeypatch.setattr(
        cache, "set", lambda key, value, timeout=None: captured.update(timeout=timeout)
    )

    connections.store(CREDENTIALS)

    assert captured["timeout"] == 60
    assert original is not None


def test_demo_connection_uses_the_configured_bucket(settings):
    settings.S3_DEMO_ENABLED = True
    settings.S3_BUCKET = "datasets"

    demo = connections.load(connections.DEMO_CONNECTION_ID)

    assert demo.bucket == "datasets"


def test_demo_connection_can_be_switched_off(settings):
    settings.S3_DEMO_ENABLED = False

    assert connections.demo_connection() is None
    with pytest.raises(S3ConnectionExpired):
        connections.load(connections.DEMO_CONNECTION_ID)
