"""Small samples of column values, used to show an LLM what the data looks like."""

from collections.abc import Sequence

from pyspark.sql import DataFrame

from processing.transforms.columns import quoted_column, require_columns

SAMPLE_ROWS = 1000
MAX_VALUES_PER_COLUMN = 20
MAX_VALUE_LENGTH = 200


def sample_column_values(
    df: DataFrame,
    columns: Sequence[str],
    max_values: int = MAX_VALUES_PER_COLUMN,
    sample_rows: int = SAMPLE_ROWS,
) -> dict[str, list[str]]:
    """Distinct, non-blank values per column, taken from the first `sample_rows` rows.

    Reading only the first rows keeps this a cheap Spark job on files of any size; the
    specification it informs is still applied to every row.
    """
    targets = require_columns(df, columns)
    rows = df.select(*(quoted_column(name) for name in targets)).limit(sample_rows).collect()
    samples: dict[str, list[str]] = {name: [] for name in targets}
    for row in rows:
        for name, value in zip(targets, row, strict=True):
            text = "" if value is None else str(value).strip()[:MAX_VALUE_LENGTH]
            values = samples[name]
            if text and len(values) < max_values and text not in values:
                values.append(text)
    return samples
