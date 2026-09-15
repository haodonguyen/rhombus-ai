import pytest

from processing.errors import InvalidPatternError, InvalidSpecError
from processing.specs import (
    MAX_DATE_FORMATS,
    MAX_RULES,
    DateNormalization,
    RewriteRule,
    RuleNormalization,
    validate_date_normalization,
    validate_replacement,
    validate_rule_normalization,
)

# --- date normalization ---------------------------------------------------------------


@pytest.mark.parametrize(
    "formats",
    [
        ("yyyy-MM-dd",),
        ("dd/MM/yyyy", "MMM d, yyyy"),
        ("d MMMM yyyy",),
        ("yyyy-MM-dd'T'HH:mm:ss",),
    ],
)
def test_supported_date_formats(formats):
    spec = DateNormalization(formats, "yyyy-MM-dd")

    assert validate_date_normalization(spec) is spec


@pytest.mark.parametrize(
    ("input_formats", "output_format", "message"),
    [
        ((), "yyyy-MM-dd", "no input date formats"),
        (("yyyy-MM-dd",) * (MAX_DATE_FORMATS + 1), "yyyy-MM-dd", "more than"),
        (("YYYY-ww",), "yyyy-MM-dd", "Unsupported date format"),
        (("yyyy-MM-dd",), "", "Unsupported date format"),
        (("yyyy-MM-dd;DROP",), "yyyy-MM-dd", "Unsupported date format"),
        (("EEE, d MMM yyyy",), "yyyy-MM-dd", "Weekday names"),
    ],
)
def test_invalid_date_normalizations(input_formats, output_format, message):
    with pytest.raises(InvalidSpecError, match=message):
        validate_date_normalization(DateNormalization(input_formats, output_format))


# --- rule normalization ---------------------------------------------------------------

PATTERN = r"^(\d{3})[.-](\d{4})$"


@pytest.mark.parametrize("replacement", ["$1-$2", "($1) $2", "unknown", ""])
def test_valid_replacements(replacement):
    validate_replacement(RewriteRule(PATTERN, replacement))


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("$3", "group the pattern does not have"),
        ("$1\\n", "backslashes"),
        ("costs $", "must be followed by a group number"),
        ("$12", "ambiguous group reference"),
        ("x" * 201, "longer than"),
    ],
)
def test_invalid_replacements(replacement, message):
    with pytest.raises(InvalidSpecError, match=message):
        validate_replacement(RewriteRule(PATTERN, replacement))


def test_rule_patterns_go_through_the_regex_safety_checks():
    with pytest.raises(InvalidPatternError, match="catastrophic backtracking"):
        validate_rule_normalization(RuleNormalization((RewriteRule(r"(a+)+b", "x"),)))


def test_rule_count_limits():
    with pytest.raises(InvalidSpecError, match="no rewrite rules"):
        validate_rule_normalization(RuleNormalization(()))

    too_many = tuple(RewriteRule(PATTERN, "$1") for _ in range(MAX_RULES + 1))
    with pytest.raises(InvalidSpecError, match="more than"):
        validate_rule_normalization(RuleNormalization(too_many))


def test_weekday_names_are_allowed_when_writing_dates():
    spec = DateNormalization(("yyyy-MM-dd", "'Week of' d MMM yyyy"), "EEE, d MMM yyyy")

    assert validate_date_normalization(spec) is spec
