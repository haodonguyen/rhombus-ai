import pytest
import redis
from django.core.cache import cache

from apps.llm import service
from apps.llm.cache import cache_key
from apps.llm.exceptions import (
    LLMInvalidResponse,
    NormalizationNotPossible,
    PatternNotExpressible,
)
from apps.llm.schemas import (
    NormalizationSuggestion,
    PiiClassificationSuggestion,
    RewriteRuleSuggestion,
)
from processing.errors import InvalidPatternError, InvalidSpecError
from processing.specs import (
    MAX_DATE_FORMATS,
    MAX_RULES,
    DateNormalization,
    PiiType,
    RewriteRule,
    RuleNormalization,
)
from tests.llm_fakes import (
    DATE_FORMATS,
    EMAIL_PATTERN,
    make_date_normalization,
    make_pii_classification,
    make_suggestion,
)

DATE_SAMPLES = {"SignupDate": ["2020-04-24", "25/10/2018", "Nov 22, 2021"]}

# --- cache keys -----------------------------------------------------------------------


def test_cache_key_changes_with_every_part():
    base = cache_key("regex", "v1", "qwen2.5-coder:3b", "find emails")

    assert cache_key("regex", "v2", "qwen2.5-coder:3b", "find emails") != base
    assert cache_key("regex", "v1", "llama3.2:3b", "find emails") != base
    assert cache_key("regex", "v1", "qwen2.5-coder:3b", "find EMAILS") != base
    assert cache_key("normalize", "v1", "qwen2.5-coder:3b", "find emails") != base


# --- find and replace -----------------------------------------------------------------


def test_cache_miss_calls_the_model_and_stores_the_result(fake_llm):
    result = service.generate_pattern("find email addresses")

    assert (result.pattern, result.cached) == (EMAIL_PATTERN, False)
    assert result.explanation == "Matches email addresses."
    [(_, user, _)] = fake_llm.calls
    assert user == "Description: find email addresses"


def test_identical_description_is_served_from_cache(fake_llm):
    service.generate_pattern("find email addresses")

    result = service.generate_pattern("  find   email addresses ")

    assert result.cached is True
    assert result.pattern == EMAIL_PATTERN
    assert len(fake_llm.calls) == 1


def test_changing_the_prompt_version_misses_the_cache(fake_llm, monkeypatch):
    service.generate_pattern("find email addresses")
    monkeypatch.setattr(service.regex_prompt, "PROMPT_VERSION", "regex-v999")

    assert service.generate_pattern("find email addresses").cached is False


def test_flags_are_applied_as_inline_prefix(fake_llm):
    fake_llm.respond_with(make_suggestion(pattern=r"\bvip\b", case_insensitive=True))

    assert service.generate_pattern("the word vip").pattern == r"(?i)\bvip\b"


def test_infeasible_description_raises_with_the_model_explanation(fake_llm):
    fake_llm.respond_with(
        make_suggestion(
            feasible=False, pattern="", explanation="Sentiment cannot be matched by a regex."
        )
    )

    with pytest.raises(PatternNotExpressible, match="Sentiment cannot be matched"):
        service.generate_pattern("angry comments")


def test_unsafe_generated_pattern_is_rejected_and_not_cached(fake_llm):
    fake_llm.respond_with(make_suggestion(pattern=r"(a+)+b"))

    with pytest.raises(InvalidPatternError, match="catastrophic backtracking"):
        service.generate_pattern("lots of a then b")

    fake_llm.respond_with(make_suggestion())
    assert service.generate_pattern("lots of a then b").cached is False


def test_malformed_cache_entry_is_treated_as_a_miss(fake_llm, settings):
    key = cache_key(
        "regex", service.regex_prompt.PROMPT_VERSION, settings.LLM_MODEL, "find email addresses"
    )
    cache.set(key, {"unexpected": True})

    assert service.generate_pattern("find email addresses").cached is False


def test_cache_outage_does_not_fail_generation(fake_llm, monkeypatch):
    def unavailable(*args, **kwargs):
        raise redis.ConnectionError("redis down")

    monkeypatch.setattr(cache, "get", unavailable)
    monkeypatch.setattr(cache, "set", unavailable)

    assert service.generate_pattern("find email addresses").pattern == EMAIL_PATTERN


# --- format normalization -------------------------------------------------------------


def test_date_normalization_becomes_a_validated_spec(fake_llm):
    fake_llm.respond_with(make_date_normalization())

    generated = service.generate_normalization("dates as YYYY-MM-DD", DATE_SAMPLES)

    assert generated.spec == DateNormalization(tuple(DATE_FORMATS), "yyyy-MM-dd")
    assert (generated.cached, generated.explanation) == (False, "Writes dates as YYYY-MM-DD.")
    assert generated.suggestion["kind"] == "date"
    [(_, user, output_type)] = fake_llm.calls
    assert output_type is NormalizationSuggestion
    assert "Target format: dates as YYYY-MM-DD" in user
    assert '"Nov 22, 2021"' in user


def test_rule_normalization_becomes_a_validated_spec(fake_llm):
    rule = RewriteRuleSuggestion(
        pattern=r"^\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})$", replacement="$1-$2-$3"
    )
    fake_llm.respond_with(
        make_date_normalization(kind="rules", input_formats=[], output_format="", rules=[rule])
    )

    spec = service.generate_normalization("phones as 555-123-4567", {"Phone": ["816.227.4257"]})

    assert spec.spec == RuleNormalization((RewriteRule(rule.pattern, "$1-$2-$3"),))


def test_normalization_cache_depends_on_the_samples(fake_llm):
    fake_llm.respond_with(make_date_normalization())
    service.generate_normalization("ISO dates", DATE_SAMPLES)

    assert service.generate_normalization("ISO dates", DATE_SAMPLES).cached is True
    assert (
        service.generate_normalization("ISO dates", {"SignupDate": ["2020-04-24"]}).cached is False
    )


def test_infeasible_normalization_raises_with_the_model_explanation(fake_llm):
    fake_llm.respond_with(
        make_date_normalization(feasible=False, explanation="Needs exchange rates.")
    )

    with pytest.raises(NormalizationNotPossible, match="exchange rates"):
        service.generate_normalization("prices in euros", {"Price": ["$10"]})


def test_invalid_normalization_is_rejected_and_not_cached(fake_llm):
    fake_llm.respond_with(make_date_normalization(input_formats=["YYYY-ww"]))

    with pytest.raises(InvalidSpecError):
        service.generate_normalization("ISO dates", DATE_SAMPLES)

    fake_llm.respond_with(make_date_normalization())
    assert service.generate_normalization("ISO dates", DATE_SAMPLES).cached is False


def test_repeated_date_formats_are_tried_once(fake_llm):
    fake_llm.respond_with(
        make_date_normalization(input_formats=["yyyy-MM-dd", "dd/MM/yyyy", "dd/MM/yyyy"])
    )

    spec = service.generate_normalization("ISO dates", DATE_SAMPLES).spec

    assert spec.input_formats == ("yyyy-MM-dd", "dd/MM/yyyy")


def test_suggestion_schema_bounds_every_list_so_decoding_cannot_loop():
    # Seen live: the model repeated "dd/MM/yyyy" in input_formats until the request timed out.
    schema = NormalizationSuggestion.model_json_schema()
    pii_schema = PiiClassificationSuggestion.model_json_schema()

    assert schema["properties"]["input_formats"]["maxItems"] == MAX_DATE_FORMATS
    assert schema["properties"]["rules"]["maxItems"] == MAX_RULES
    assert pii_schema["$defs"]["ColumnPiiSuggestion"]["properties"]["pii_types"]["maxItems"] > 0


def test_saved_normalization_suggestion_is_rebuilt_and_revalidated():
    saved = make_date_normalization().model_dump()

    assert isinstance(service.normalization_spec_from_suggestion(saved), DateNormalization)
    with pytest.raises(LLMInvalidResponse):
        service.normalization_spec_from_suggestion({"kind": "date"})


# --- PII masking ----------------------------------------------------------------------


def test_pii_classification_keeps_requested_columns_with_personal_data(fake_llm):
    fake_llm.respond_with(
        make_pii_classification(
            {
                "ID": ["none"],
                "Email": ["email"],
                "Notes": ["phone", "email", "none"],
                "Invented": ["email"],
            }
        )
    )
    samples = {"ID": ["1"], "Email": ["a@example.com"], "Notes": ["Call 816.227.4257"]}

    generated = service.classify_pii(samples)

    assert generated.spec.columns == {
        "Email": frozenset({PiiType.EMAIL}),
        "Notes": frozenset({PiiType.PHONE, PiiType.EMAIL}),
    }
    [(_, user, output_type)] = fake_llm.calls
    assert output_type is PiiClassificationSuggestion
    assert '- Notes: ["Call 816.227.4257"]' in user


def test_pii_classification_is_cached_per_sample(fake_llm):
    fake_llm.respond_with(make_pii_classification({"Email": ["email"]}))
    samples = {"Email": ["a@example.com"]}
    service.classify_pii(samples)

    assert service.classify_pii(samples).cached is True
    assert len(fake_llm.calls) == 1


def test_saved_pii_suggestion_is_limited_to_the_job_columns():
    saved = make_pii_classification({"Email": ["email"], "Name": ["person_name"]}).model_dump()

    spec = service.pii_spec_from_suggestion(saved, ["Email"])

    assert spec.columns == {"Email": frozenset({PiiType.EMAIL})}
