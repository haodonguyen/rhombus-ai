"""Column conventions shared by the Spark writer and the API reader. No PySpark imports."""

from collections.abc import Sequence

# Stable, monotonically increasing per-row id assigned at read time; defines result order.
ROW_ID_COLUMN = "__row_id"
# True when any target column in the row matched the pattern.
MATCHED_COLUMN = "__matched"

RESERVED_COLUMNS = frozenset({ROW_ID_COLUMN, MATCHED_COLUMN})


def find_missing_columns(available: Sequence[str], requested: Sequence[str]) -> list[str]:
    """Requested columns that are absent from `available` (reserved names never count)."""
    present = set(available) - RESERVED_COLUMNS
    return [column for column in requested if column not in present]
