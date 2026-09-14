"""Column helpers shared by the transforms."""

from collections.abc import Callable, Sequence
from functools import reduce
from operator import or_

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from processing.errors import ColumnNotFoundError
from processing.schema import MATCHED_COLUMN, find_missing_columns

# Given a column's name and its value cast to string: (new value, whether the value matched).
ColumnRewrite = Callable[[str, Column], tuple[Column, Column]]


def quoted_column(name: str) -> Column:
    # Backtick-quote so names containing dots or spaces are not parsed as nested fields.
    return F.col(f"`{name.replace('`', '``')}`")


def require_columns(df: DataFrame, columns: Sequence[str]) -> list[str]:
    """The requested columns without duplicates; raises if any is missing from `df`."""
    targets = list(dict.fromkeys(columns))
    missing = find_missing_columns(df.columns, targets)
    if missing:
        raise ColumnNotFoundError(missing)
    return targets


def rewrite_columns(df: DataFrame, targets: Sequence[str], rewrite: ColumnRewrite) -> DataFrame:
    """Rewrite target columns in place and append MATCHED_COLUMN.

    Other columns and the column order are kept. MATCHED_COLUMN is true when any target
    column in the row matched; a null match result counts as no match.
    """
    rewritten = {name: rewrite(name, quoted_column(name).cast("string")) for name in targets}
    projection = [
        rewritten[name][0].alias(name) if name in rewritten else quoted_column(name)
        for name in df.columns
    ]
    matched = reduce(
        or_,
        (F.coalesce(match, F.lit(False)) for _, match in rewritten.values()),
        F.lit(False),
    )
    return df.select(*projection, matched.alias(MATCHED_COLUMN))
