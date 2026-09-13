"""Regex find-and-replace across target columns.

Uses Spark's built-in `regexp_replace`/`rlike`, which run in the JVM per partition. There
are no Python UDFs, so throughput scales with partitions, not Python serialization. Spark
uses java.util.regex semantics, so patterns are validated against the JVM engine here.
"""

from collections.abc import Sequence
from functools import reduce
from operator import or_

from py4j.protocol import Py4JJavaError
from pyspark.errors.exceptions.captured import CapturedException
from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from processing.errors import ColumnNotFoundError, InvalidPatternError, describe_error
from processing.schema import MATCHED_COLUMN, find_missing_columns


def regex_replace(
    df: DataFrame, columns: Sequence[str], pattern: str, replacement: str
) -> DataFrame:
    """Replace every match of `pattern` in the target columns with the literal `replacement`.

    Adds MATCHED_COLUMN, true when any target column in the row matched. Nulls stay null.
    """
    targets = list(dict.fromkeys(columns))
    missing = find_missing_columns(df.columns, targets)
    if missing:
        raise ColumnNotFoundError(missing)
    ensure_java_pattern(df, pattern)

    literal_replacement = escape_replacement(replacement)
    target_set = set(targets)
    projection = [
        F.regexp_replace(_col(name).cast("string"), pattern, literal_replacement).alias(name)
        if name in target_set
        else _col(name)
        for name in df.columns
    ]
    matched = reduce(
        or_,
        (F.coalesce(_col(name).cast("string").rlike(pattern), F.lit(False)) for name in targets),
    )
    return df.select(*projection, matched.alias(MATCHED_COLUMN))


def escape_replacement(replacement: str) -> str:
    """Make `replacement` literal for java.util.regex, where `$` and `\\` are special."""
    return replacement.replace("\\", "\\\\").replace("$", "\\$")


def ensure_java_pattern(df: DataFrame, pattern: str) -> None:
    """Compile the pattern in the JVM so dialect errors fail fast with a clear message."""
    jvm = df.sparkSession.sparkContext._jvm
    try:
        jvm.java.util.regex.Pattern.compile(pattern)
    # PySpark converts most JVM exceptions into CapturedException subclasses.
    except (CapturedException, Py4JJavaError) as exc:
        raise InvalidPatternError(
            f"Pattern is not valid for Spark's Java regex engine: {describe_error(exc)}"
        ) from exc


def _col(name: str) -> Column:
    # Backtick-quote so names containing dots or spaces are not parsed as nested fields.
    return F.col(f"`{name.replace('`', '``')}`")
