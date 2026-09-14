import pytest

from processing.errors import ColumnNotFoundError
from processing.sampling import MAX_VALUE_LENGTH, sample_column_values


def test_samples_are_distinct_non_blank_and_capped(spark):
    df = spark.createDataFrame(
        [("a", "x"), ("a", None), (" ", "y"), ("b", "x"), ("c", "z")], ["First", "Second"]
    )

    samples = sample_column_values(df, ["Second", "First"], max_values=2)

    assert samples == {"Second": ["x", "y"], "First": ["a", "b"]}


def test_only_the_first_rows_are_read(spark):
    df = spark.createDataFrame([(str(i),) for i in range(50)], ["N"])

    samples = sample_column_values(df, ["N"], max_values=100, sample_rows=10)

    assert samples["N"] == [str(i) for i in range(10)]


def test_long_values_are_truncated(spark):
    df = spark.createDataFrame([("x" * 500,)], ["Text"])

    assert len(sample_column_values(df, ["Text"])["Text"][0]) == MAX_VALUE_LENGTH


def test_missing_column_raises(spark):
    df = spark.createDataFrame([("x",)], ["Text"])

    with pytest.raises(ColumnNotFoundError):
        sample_column_values(df, ["Other"])
