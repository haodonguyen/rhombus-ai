"""Redis cache of validated LLM suggestions, so identical inputs reach the model once.

The cache is an optimisation: if Redis is unreachable, lookups miss and writes are skipped
rather than failing the job.
"""

import hashlib
import logging
from typing import TypeVar

import pydantic
import redis
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=pydantic.BaseModel)


def normalize_description(description: str) -> str:
    """Collapse whitespace. Case is kept: it can matter to the answer the user wants."""
    return " ".join(description.split())


def cache_key(namespace: str, *parts: str) -> str:
    """A key over every input that shapes the answer: prompt version, model, user inputs."""
    material = "\x1f".join(parts)
    return f"llm:{namespace}:{hashlib.sha256(material.encode()).hexdigest()}"


def get_cached(key: str, output_type: type[ModelT]) -> ModelT | None:
    try:
        data = cache.get(key)
    except redis.RedisError:
        logger.warning("LLM cache lookup failed; continuing without cache", exc_info=True)
        return None
    if data is None:
        return None
    try:
        return output_type.model_validate(data)
    except pydantic.ValidationError:
        logger.warning("Ignoring malformed LLM cache entry %s", key)
        return None


def store(key: str, suggestion: pydantic.BaseModel) -> None:
    try:
        cache.set(key, suggestion.model_dump(), timeout=settings.LLM_CACHE_TTL)
    except redis.RedisError:
        logger.warning("LLM cache write failed; continuing without cache", exc_info=True)
