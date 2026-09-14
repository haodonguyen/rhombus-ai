"""LLM use cases: turn user intent, and samples of the data, into validated specifications.

Every use case takes the same path. It builds a cache key from the prompt version, model and
inputs, then reuses a cached suggestion or asks the LLM once. It validates the suggestion and
caches it only if valid. Cached suggestions are validated again on read, so tightening the
validation also applies to existing entries.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import pydantic
from django.conf import settings

from apps.llm import cache
from apps.llm.client import get_llm
from apps.llm.exceptions import (
    LLMInvalidResponse,
    NormalizationNotPossible,
    PatternNotExpressible,
)
from apps.llm.prompts import normalize as normalize_prompt
from apps.llm.prompts import pii as pii_prompt
from apps.llm.prompts import regex as regex_prompt
from apps.llm.schemas import (
    NormalizationSuggestion,
    PiiClassificationSuggestion,
    RegexSuggestion,
)
from processing.regex_safety import validate_pattern, with_inline_flags
from processing.specs import (
    DateNormalization,
    NormalizationSpec,
    PiiMaskingSpec,
    PiiType,
    RewriteRule,
    RuleNormalization,
    validate_date_normalization,
    validate_rule_normalization,
)

ModelT = TypeVar("ModelT", bound=pydantic.BaseModel)
SpecT = TypeVar("SpecT")

# Sample values per column, as shown to the LLM.
Samples = Mapping[str, Sequence[str]]


@dataclass(frozen=True)
class GeneratedPattern:
    pattern: str
    explanation: str
    cached: bool


@dataclass(frozen=True)
class GeneratedSpec(Generic[SpecT]):
    spec: SpecT
    # The raw suggestion, saved on the job so a retry rebuilds the spec without the LLM.
    suggestion: dict[str, Any]
    explanation: str
    cached: bool


# --- find and replace -----------------------------------------------------------------


def generate_pattern(description: str) -> GeneratedPattern:
    """Turn a description into a safe, validated regex pattern."""
    key = cache.cache_key(
        "regex",
        regex_prompt.PROMPT_VERSION,
        settings.LLM_MODEL,
        cache.normalize_description(description),
    )
    pattern, suggestion, cached = _complete(
        key,
        RegexSuggestion,
        regex_prompt.SYSTEM_PROMPT,
        regex_prompt.build_user_message(description),
        pattern_from_suggestion,
    )
    return GeneratedPattern(pattern=pattern, explanation=suggestion.explanation, cached=cached)


def pattern_from_suggestion(suggestion: RegexSuggestion) -> str:
    if not suggestion.feasible:
        raise PatternNotExpressible(suggestion.explanation or None)
    pattern = with_inline_flags(
        suggestion.pattern,
        case_insensitive=suggestion.case_insensitive,
        multiline=suggestion.multiline,
        dotall=suggestion.dotall,
    )
    return validate_pattern(pattern)


# --- format normalization -------------------------------------------------------------


def generate_normalization(description: str, samples: Samples) -> GeneratedSpec[NormalizationSpec]:
    """Turn a target-format description and sample values into a normalization spec."""
    key = cache.cache_key(
        "normalize",
        normalize_prompt.PROMPT_VERSION,
        settings.LLM_MODEL,
        cache.normalize_description(description),
        _fingerprint(samples),
    )
    spec, suggestion, cached = _complete(
        key,
        NormalizationSuggestion,
        normalize_prompt.SYSTEM_PROMPT,
        normalize_prompt.build_user_message(description, samples),
        normalization_spec_from_suggestion,
    )
    return GeneratedSpec(spec, suggestion.model_dump(), suggestion.explanation, cached)


def normalization_spec_from_suggestion(
    suggestion: NormalizationSuggestion | Mapping[str, Any],
) -> NormalizationSpec:
    parsed = _parse(NormalizationSuggestion, suggestion)
    if not parsed.feasible:
        raise NormalizationNotPossible(parsed.explanation or None)
    if parsed.kind == "date":
        return validate_date_normalization(
            DateNormalization(tuple(parsed.input_formats), parsed.output_format)
        )
    return validate_rule_normalization(
        RuleNormalization(tuple(RewriteRule(r.pattern, r.replacement) for r in parsed.rules))
    )


# --- PII masking ----------------------------------------------------------------------


def classify_pii(samples: Samples) -> GeneratedSpec[PiiMaskingSpec]:
    """Decide from sample values which columns hold which kinds of personal data."""
    columns = list(samples)
    key = cache.cache_key(
        "pii", pii_prompt.PROMPT_VERSION, settings.LLM_MODEL, _fingerprint(samples)
    )
    spec, suggestion, cached = _complete(
        key,
        PiiClassificationSuggestion,
        pii_prompt.SYSTEM_PROMPT,
        pii_prompt.build_user_message(samples),
        lambda parsed: pii_spec_from_suggestion(parsed, columns),
    )
    return GeneratedSpec(spec, suggestion.model_dump(), suggestion.explanation, cached)


def pii_spec_from_suggestion(
    suggestion: PiiClassificationSuggestion | Mapping[str, Any],
    allowed_columns: Sequence[str],
) -> PiiMaskingSpec:
    """Keep only requested columns that hold personal data; ignore any the model invented."""
    parsed = _parse(PiiClassificationSuggestion, suggestion)
    allowed = set(allowed_columns)
    columns: dict[str, frozenset[PiiType]] = {}
    for item in parsed.columns:
        types = frozenset(PiiType(name) for name in item.pii_types if name != "none")
        if item.column in allowed and types:
            columns[item.column] = columns.get(item.column, frozenset()) | types
    return PiiMaskingSpec(columns=columns)


# --- shared ---------------------------------------------------------------------------


def _complete(
    key: str,
    output_type: type[ModelT],
    system: str,
    user: str,
    interpret: Callable[[ModelT], SpecT],
) -> tuple[SpecT, ModelT, bool]:
    suggestion = cache.get_cached(key, output_type)
    cached = suggestion is not None
    if suggestion is None:
        suggestion = get_llm().complete(system, user, output_type)
    result = interpret(suggestion)
    if not cached:
        cache.store(key, suggestion)
    return result, suggestion, cached


def _parse(output_type: type[ModelT], value: ModelT | Mapping[str, Any]) -> ModelT:
    if isinstance(value, output_type):
        return value
    try:
        return output_type.model_validate(value)
    except pydantic.ValidationError as exc:
        raise LLMInvalidResponse() from exc


def _fingerprint(samples: Samples) -> str:
    return json.dumps({column: list(values) for column, values in samples.items()}, sort_keys=True)
