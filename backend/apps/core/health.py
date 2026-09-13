"""Dependency health checks backing the /api/health/ endpoint."""

import logging

import redis
from django.conf import settings
from django.db import DatabaseError, connection

logger = logging.getLogger(__name__)

OK = "ok"
ERROR = "error"


def check_database() -> str:
    try:
        connection.ensure_connection()
    except DatabaseError:
        logger.warning("Database health check failed", exc_info=True)
        return ERROR
    return OK


def check_redis() -> str:
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
        )
        client.ping()
    except redis.RedisError:
        logger.warning("Redis health check failed", exc_info=True)
        return ERROR
    return OK


def run_health_checks() -> dict[str, str]:
    return {"db": check_database(), "redis": check_redis()}
