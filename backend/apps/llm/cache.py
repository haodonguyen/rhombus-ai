"""Redis cache of validated suggestions, so an identical description reaches the LLM once.

The cache is an optimisation: if Redis is unreachable, lookups miss and writes are skipped
rather than failing the job.
"""

import hashlib
import logging

import pydantic
import redis
from django.conf import settings
from django.core.cache import cache

from apps.llm.prompts.regex import PROMPT_VERSION
from apps.llm.schemas import RegexSuggestion

logger = logging.getLogger(__name__)


def normalize_description(description: str) -> str:
    """Collapse whitespace. Case is kept: it can matter to the pattern the user wants."""
    return " ".join(description.split())


def cache_key(description: str, model: str) -> str:
    material = "\x1f".join([PROMPT_VERSION, model, normalize_description(description)])
    return f"llm:regex:{hashlib.sha256(material.encode()).hexdigest()}"


def get_cached_suggestion(key: str) -> RegexSuggestion | None:
    try:
        data = cache.get(key)
    except redis.RedisError:
        logger.warning("Regex cache lookup failed; continuing without cache", exc_info=True)
        return None
    if data is None:
        return None
    try:
        return RegexSuggestion.model_validate(data)
    except pydantic.ValidationError:
        logger.warning("Ignoring malformed regex cache entry %s", key)
        return None


def store_suggestion(key: str, suggestion: RegexSuggestion) -> None:
    try:
        cache.set(key, suggestion.model_dump(), timeout=settings.LLM_CACHE_TTL)
    except redis.RedisError:
        logger.warning("Regex cache write failed; continuing without cache", exc_info=True)
