"""Transformation specifications that the LLM layer produces and Spark executes.

Pure Python and importable without PySpark: the LLM layer validates a specification before
any Spark work starts, and the task layer reloads saved specifications on retries.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from processing.errors import InvalidSpecError
from processing.regex_safety import validate_pattern

MAX_RULES = 10
MAX_DATE_FORMATS = 10
MAX_DATE_FORMAT_LENGTH = 40
MAX_REPLACEMENT_LENGTH = 200

# Datetime pattern letters Spark 3 supports, separators and quoted literals. Week-based letters
# (Y, w, u, e, c) are rejected by Spark 3, so here too. Weekday names (E) can be rendered but
# not parsed: Spark raises DATETIME_PATTERN_RECOGNITION when `to_date` is given an E pattern.
_OUTPUT_FORMAT = re.compile(r"(?:[yMdEaHhmsS]+|'[^']*'|[ ,./:-])+")
_INPUT_FORMAT = re.compile(r"(?:[yMdaHhmsS]+|'[^']*'|[ ,./:-])+")
_QUOTED_LITERAL = re.compile(r"'[^']*'")
_GROUP_REFERENCE = re.compile(r"\$(\d)")


@dataclass(frozen=True)
class RewriteRule:
    pattern: str
    replacement: str


@dataclass(frozen=True)
class DateNormalization:
    """Parse each value with the first input format that fits; render it as the output."""

    input_formats: tuple[str, ...]
    output_format: str


@dataclass(frozen=True)
class RuleNormalization:
    """Rewrite each value with the first rule whose pattern matches it."""

    rules: tuple[RewriteRule, ...]


NormalizationSpec = DateNormalization | RuleNormalization


class PiiType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    PERSON_NAME = "person_name"
    CREDIT_CARD = "credit_card"
    IDENTIFIER = "identifier"
    ADDRESS = "address"
    OTHER = "other"


@dataclass(frozen=True)
class PiiMaskingSpec:
    """Kinds of personal data found per column. Columns without any are left out."""

    columns: Mapping[str, frozenset[PiiType]]


def validate_date_normalization(spec: DateNormalization) -> DateNormalization:
    if not spec.input_formats:
        raise InvalidSpecError("The specification lists no input date formats.")
    if len(spec.input_formats) > MAX_DATE_FORMATS:
        raise InvalidSpecError(
            f"The specification lists more than {MAX_DATE_FORMATS} input date formats."
        )
    for date_format in spec.input_formats:
        if "E" in _QUOTED_LITERAL.sub("", date_format):
            raise InvalidSpecError(
                f"Weekday names (E) cannot be used to read dates: {date_format!r}."
            )
        _check_date_format(date_format, _INPUT_FORMAT)
    _check_date_format(spec.output_format, _OUTPUT_FORMAT)
    return spec


def _check_date_format(date_format: str, allowed: re.Pattern[str]) -> None:
    if len(date_format) > MAX_DATE_FORMAT_LENGTH or not allowed.fullmatch(date_format):
        raise InvalidSpecError(f"Unsupported date format: {date_format!r}.")


def validate_rule_normalization(spec: RuleNormalization) -> RuleNormalization:
    if not spec.rules:
        raise InvalidSpecError("The specification lists no rewrite rules.")
    if len(spec.rules) > MAX_RULES:
        raise InvalidSpecError(f"The specification lists more than {MAX_RULES} rewrite rules.")
    for rule in spec.rules:
        validate_pattern(rule.pattern)
        validate_replacement(rule)
    return spec


def validate_replacement(rule: RewriteRule) -> None:
    """Allow literal text plus `$n` references to groups that exist in the rule's pattern.

    Spark's Java regex engine treats `\\` and `$` specially in replacements, so any other use
    of them is rejected rather than guessed at.
    """
    replacement = rule.replacement
    if len(replacement) > MAX_REPLACEMENT_LENGTH:
        raise InvalidSpecError(f"A replacement is longer than {MAX_REPLACEMENT_LENGTH} characters.")
    if "\\" in replacement:
        raise InvalidSpecError("Replacements may not contain backslashes.")
    if "$" in _GROUP_REFERENCE.sub("", replacement):
        raise InvalidSpecError("A '$' in a replacement must be followed by a group number.")
    groups = re.compile(rule.pattern).groups
    for match in _GROUP_REFERENCE.finditer(replacement):
        if int(match.group(1)) > groups:
            raise InvalidSpecError(
                f"Replacement {replacement!r} refers to a group the pattern does not have."
            )
        if replacement[match.end() : match.end() + 1].isdigit():
            raise InvalidSpecError(f"Replacement {replacement!r} has an ambiguous group reference.")
