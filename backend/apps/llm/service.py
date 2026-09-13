from dataclasses import dataclass

from django.conf import settings

from apps.llm.cache import cache_key, get_cached_suggestion, store_suggestion
from apps.llm.client import get_regex_generator
from apps.llm.exceptions import PatternNotExpressible
from processing.regex_safety import validate_pattern, with_inline_flags


@dataclass(frozen=True)
class GeneratedPattern:
    pattern: str
    explanation: str
    cached: bool


def generate_pattern(description: str) -> GeneratedPattern:
    """Turn a description into a safe, validated pattern, consulting the cache first.

    Only feasible suggestions that pass the safety checks are cached. Cached suggestions
    are re-validated, so tightening the checks also applies to existing entries.
    """
    key = cache_key(description, settings.LLM_MODEL)
    suggestion = get_cached_suggestion(key)
    cached = suggestion is not None
    if suggestion is None:
        suggestion = get_regex_generator().generate(description)

    if not suggestion.feasible:
        raise PatternNotExpressible(suggestion.explanation or None)

    pattern = with_inline_flags(
        suggestion.pattern,
        case_insensitive=suggestion.case_insensitive,
        multiline=suggestion.multiline,
        dotall=suggestion.dotall,
    )
    validate_pattern(pattern)

    if not cached:
        store_suggestion(key, suggestion)
    return GeneratedPattern(pattern=pattern, explanation=suggestion.explanation, cached=cached)
