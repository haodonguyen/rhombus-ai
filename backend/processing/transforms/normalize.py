"""Rewrite values in target columns into one format, following a validated specification.

Dates are parsed with Spark's `to_date` against each input format and rendered again with
`date_format`. Other values are rewritten by the first rule whose pattern matches. Values that
no format or rule recognises are left unchanged. Everything runs as built-in Spark functions.
"""

from collections.abc import Sequence
from functools import reduce
from operator import or_

from py4j.protocol import Py4JJavaError
from pyspark.errors.exceptions.captured import CapturedException
from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from processing.errors import InvalidSpecError, describe_error
from processing.specs import DateNormalization, NormalizationSpec, RuleNormalization
from processing.transforms.columns import require_columns, rewrite_columns
from processing.transforms.regex_replace import ensure_java_pattern


def normalize_format(df: DataFrame, columns: Sequence[str], spec: NormalizationSpec) -> DataFrame:
    """Normalize the target columns. Adds MATCHED_COLUMN, true when any value was rewritten."""
    targets = require_columns(df, columns)
    if isinstance(spec, DateNormalization):
        ensure_java_date_formats(df, (*spec.input_formats, spec.output_format))
        return rewrite_columns(df, targets, lambda _name, value: _normalize_date(value, spec))
    for rule in spec.rules:
        ensure_java_pattern(df, rule.pattern)
    return rewrite_columns(df, targets, lambda _name, value: _apply_rules(value, spec))


def ensure_java_date_formats(df: DataFrame, formats: Sequence[str]) -> None:
    """Compile each date pattern in the JVM so invalid ones fail before any data is read."""
    jvm = df.sparkSession.sparkContext._jvm
    for date_format in formats:
        try:
            jvm.java.time.format.DateTimeFormatter.ofPattern(date_format)
        except (CapturedException, Py4JJavaError) as exc:
            raise InvalidSpecError(
                f"Date format {date_format!r} is not valid: {describe_error(exc)}"
            ) from exc


def _normalize_date(value: Column, spec: DateNormalization) -> tuple[Column, Column]:
    trimmed = F.trim(value)
    # Unparseable input yields null (spark.sql.legacy.timeParserPolicy=CORRECTED), so the
    # first format that fits wins.
    parsed = F.coalesce(*(F.to_date(trimmed, fmt) for fmt in spec.input_formats))
    recognised = parsed.isNotNull()
    rendered = F.when(recognised, F.date_format(parsed, spec.output_format)).otherwise(value)
    return rendered, recognised


def _apply_rules(value: Column, spec: RuleNormalization) -> tuple[Column, Column]:
    matches = [value.rlike(rule.pattern) for rule in spec.rules]
    first, *rest = spec.rules
    rewritten = F.when(matches[0], F.regexp_replace(value, first.pattern, first.replacement))
    for matched, rule in zip(matches[1:], rest, strict=True):
        rewritten = rewritten.when(matched, F.regexp_replace(value, rule.pattern, rule.replacement))
    return rewritten.otherwise(value), reduce(or_, matches)
