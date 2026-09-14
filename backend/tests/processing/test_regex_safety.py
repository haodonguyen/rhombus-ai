import pytest

from processing import regex_safety
from processing.errors import InvalidPatternError
from processing.regex_safety import (
    MAX_PATTERN_LENGTH,
    check_syntax,
    validate_pattern,
    with_inline_flags,
)

SAFE_PATTERNS = [
    pytest.param(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b", id="email-from-brief"),
    pytest.param(r"\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", id="us-phone"),
    pytest.param(r"\b\d{4}-\d{2}-\d{2}\b", id="iso-date"),
    pytest.param(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", id="ipv4-bounded-repeat"),
    pytest.param(r"https?://(?:[\w-]+\.)+[A-Za-z]{2,}(?:/[\w./?%&=-]*)?", id="url-separated"),
    pytest.param(r"\d+(?:,\d+)*", id="comma-separated-numbers"),
    pytest.param(r"(?i)\bvip customer\b", id="inline-case-flag"),
    pytest.param(r"\b(?:com|org|net)\b", id="disjoint-alternation"),
    pytest.param(r"(?:\w+\s+)*done", id="words-with-mandatory-spaces"),
    pytest.param(r"(?:a+)++b", id="possessive-outer"),
    pytest.param(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", id="uuid"),
]


@pytest.mark.parametrize("pattern", SAFE_PATTERNS)
def test_common_patterns_are_accepted(pattern):
    assert validate_pattern(pattern) == pattern


UNSAFE_PATTERNS = [
    pytest.param("", "empty", id="empty"),
    pytest.param("a" * (MAX_PATTERN_LENGTH + 1), "longer than", id="too-long"),
    pytest.param("(unclosed", "Invalid regular expression", id="syntax-error"),
    pytest.param(r"(?P<user>\w+)@", "Python-style named groups", id="python-named-group"),
    pytest.param(r"(?<user>\w+)@", "Named groups are not supported", id="java-named-group"),
    pytest.param(r"(a)?(?(1)b|c)", "Conditional groups", id="conditional"),
    pytest.param(r"(?#note)abc", "Inline comments", id="comment"),
    pytest.param(r"(a+)+b", "catastrophic backtracking", id="nested-plus"),
    pytest.param(r"(\w+\s?)*!", "catastrophic backtracking", id="optional-separator"),
    pytest.param(r"(.*a){20}", "catastrophic backtracking", id="wide-bounded-outer"),
    # Single-character alternatives are merged into a class by Python's parser and cannot
    # be detected (see the module docstring), so this uses multi-character branches.
    pytest.param(r"(?:a\w|\wb|cd)+x", "catastrophic backtracking", id="overlapping-alternation"),
    pytest.param(r"x(a|a)*y", "catastrophic backtracking", id="duplicate-alternation"),
    pytest.param(r"\d*", "empty text", id="matches-empty"),
    pytest.param(r"^$", "empty text", id="anchors-only"),
    pytest.param(r"(?=abc)", "empty text", id="lookahead-only"),
]


@pytest.mark.parametrize(("pattern", "reason"), UNSAFE_PATTERNS)
def test_unsafe_patterns_are_rejected_with_a_reason(pattern, reason):
    with pytest.raises(InvalidPatternError, match=reason):
        validate_pattern(pattern)


def test_lookbehind_is_not_mistaken_for_a_named_group():
    check_syntax(r"(?<=\$)\d+")
    check_syntax(r"(?<!-)\d+")


@pytest.mark.parametrize(
    "pattern",
    [
        r"^\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})$",
        r"\(?#\d+\)?",
        r"\\\(?(\d+)",
    ],
    ids=["optional-paren-then-group", "optional-paren-then-hash", "escaped-backslash-and-paren"],
)
def test_escaped_parentheses_are_not_mistaken_for_special_groups(pattern):
    check_syntax(pattern)


def test_group_after_an_escaped_backslash_is_still_checked():
    with pytest.raises(InvalidPatternError, match="Conditional groups"):
        check_syntax(r"\\(?(1)a|b)")


def test_check_syntax_does_not_run_structural_checks():
    check_syntax(r"(a+)+b")  # cheap request-time check only; validate_pattern rejects it


def test_behavioural_check_catches_slow_patterns_the_structure_check_misses(monkeypatch):
    monkeypatch.setattr(regex_safety, "_find_backtracking_risk", lambda parsed: None)

    with pytest.raises(InvalidPatternError, match="too slow"):
        validate_pattern(r"(a+)+b")


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({}, r"\d+"),
        ({"case_insensitive": True}, r"(?i)\d+"),
        ({"case_insensitive": True, "multiline": True, "dotall": True}, r"(?ims)\d+"),
    ],
)
def test_with_inline_flags(flags, expected):
    assert with_inline_flags(r"\d+", **flags) == expected


def test_flagged_patterns_still_validate():
    validate_pattern(with_inline_flags(r"\bvip\b", case_insensitive=True))
