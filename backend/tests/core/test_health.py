import pytest
import redis

from apps.core import health


@pytest.mark.django_db
def test_health_ok_when_all_dependencies_reachable(api_client, monkeypatch):
    monkeypatch.setattr(health, "check_redis", lambda: health.OK)

    response = api_client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}


@pytest.mark.django_db
def test_health_degraded_returns_503(api_client, monkeypatch):
    monkeypatch.setattr(health, "check_redis", lambda: health.ERROR)

    response = api_client.get("/api/health/")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": "ok", "redis": "error"}


def test_check_redis_reports_error_on_connection_failure(monkeypatch):
    def unreachable(*args, **kwargs):
        raise redis.ConnectionError("connection refused")

    monkeypatch.setattr(redis.Redis, "ping", unreachable)

    assert health.check_redis() == health.ERROR
