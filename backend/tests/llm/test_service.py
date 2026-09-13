import pytest
import redis
from django.core.cache import cache

from apps.llm import cache as llm_cache
from apps.llm.cache import cache_key
from apps.llm.exceptions import PatternNotExpressible
from apps.llm.service import generate_pattern
from processing.errors import InvalidPatternError
from tests.llm.conftest import EMAIL_PATTERN, make_suggestion


def test_cache_miss_calls_the_model_and_stores_the_result(fake_generator):
    result = generate_pattern("find email addresses")

    assert (result.pattern, result.cached) == (EMAIL_PATTERN, False)
    assert result.explanation == "Matches email addresses."
    assert fake_generator.descriptions == ["find email addresses"]


def test_identical_description_is_served_from_cache(fake_generator):
    generate_pattern("find email addresses")

    result = generate_pattern("  find   email addresses ")

    assert result.cached is True
    assert result.pattern == EMAIL_PATTERN
    assert len(fake_generator.descriptions) == 1


def test_different_model_or_prompt_version_uses_a_different_key(monkeypatch):
    base = cache_key("find emails", "claude-opus-5")

    assert cache_key("find emails", "claude-sonnet-5") != base
    monkeypatch.setattr(llm_cache, "PROMPT_VERSION", "regex-v999")
    assert cache_key("find emails", "claude-opus-5") != base


def test_case_is_significant_in_the_cache_key():
    assert cache_key("find VIP", "m") != cache_key("find vip", "m")


def test_flags_are_applied_as_inline_prefix(fake_generator):
    fake_generator.suggestion = make_suggestion(pattern=r"\bvip\b", case_insensitive=True)

    assert generate_pattern("the word vip").pattern == r"(?i)\bvip\b"


def test_infeasible_description_raises_with_the_model_explanation(fake_generator):
    fake_generator.suggestion = make_suggestion(
        feasible=False, pattern="", explanation="Sentiment cannot be matched by a regex."
    )

    with pytest.raises(PatternNotExpressible, match="Sentiment cannot be matched"):
        generate_pattern("angry comments")


def test_unsafe_generated_pattern_is_rejected_and_not_cached(fake_generator):
    fake_generator.suggestion = make_suggestion(pattern=r"(a+)+b")

    with pytest.raises(InvalidPatternError, match="catastrophic backtracking"):
        generate_pattern("lots of a then b")

    fake_generator.suggestion = make_suggestion()
    assert generate_pattern("lots of a then b").cached is False


def test_malformed_cache_entry_is_treated_as_a_miss(fake_generator, settings):
    cache.set(cache_key("find email addresses", settings.LLM_MODEL), {"unexpected": True})

    assert generate_pattern("find email addresses").cached is False


def test_cache_outage_does_not_fail_generation(fake_generator, monkeypatch):
    def unavailable(*args, **kwargs):
        raise redis.ConnectionError("redis down")

    monkeypatch.setattr(cache, "get", unavailable)
    monkeypatch.setattr(cache, "set", unavailable)

    assert generate_pattern("find email addresses").pattern == EMAIL_PATTERN
