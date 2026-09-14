"""Regex find-and-replace across target columns.

Uses Spark's built-in `regexp_replace`/`rlike`, which run in the JVM per partition. There
are no Python UDFs, so throughput scales with partitions, not Python serialization. Spark
uses java.util.regex semantics, so patterns are validated against the JVM engine here.
"""

from collections.abc import Sequence

from py4j.protocol import Py4JJavaError
from pyspark.errors.exceptions.captured import CapturedException
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from processing.errors import InvalidPatternError, describe_error
from processing.transforms.columns import require_columns, rewrite_columns


def regex_replace(
    df: DataFrame, columns: Sequence[str], pattern: str, replacement: str
) -> DataFrame:
    """Replace every match of `pattern` in the target columns with the literal `replacement`.

    Adds MATCHED_COLUMN, true when any target column in the row matched. Nulls stay null.
    """
    targets = require_columns(df, columns)
    ensure_java_pattern(df, pattern)
    literal_replacement = escape_replacement(replacement)
    return rewrite_columns(
        df,
        targets,
        lambda _name, value: (
            F.regexp_replace(value, pattern, literal_replacement),
            value.rlike(pattern),
        ),
    )


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
