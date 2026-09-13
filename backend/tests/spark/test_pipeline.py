from dataclasses import replace

import pytest

from processing.errors import ColumnNotFoundError, SourceReadError
from processing.file_types import FileType
from processing.pipeline import RegexReplaceSpec, RunStats, Stage, run_regex_replace
from processing.schema import MATCHED_COLUMN, ROW_ID_COLUMN
from tests.spark.conftest import BRIEF_CSV, EMAIL_PATTERN


@pytest.fixture
def output_path(tmp_path) -> str:
    return str(tmp_path / "output")


def make_spec(source_uri: str, output_path: str) -> RegexReplaceSpec:
    return RegexReplaceSpec(
        source_uri=source_uri,
        file_type=FileType.CSV,
        columns=("Email",),
        pattern=EMAIL_PATTERN,
        replacement="REDACTED",
        output_path=output_path,
    )


def test_brief_example_end_to_end(spark, write_csv, output_path):
    stages: list[Stage] = []

    stats = run_regex_replace(
        spark, make_spec(write_csv(BRIEF_CSV), output_path), on_stage=stages.append
    )

    assert stats == RunStats(row_count=3, matched_count=3)
    assert stages == [Stage.LOADING, Stage.TRANSFORMING, Stage.FINALIZING]
    output = spark.read.parquet(output_path)
    assert output.columns == [ROW_ID_COLUMN, "ID", "Name", "Email", MATCHED_COLUMN]
    rows = output.orderBy(ROW_ID_COLUMN).collect()
    assert [(r["ID"], r["Name"], r["Email"]) for r in rows] == [
        ("1", "John Doe", "REDACTED"),
        ("2", "Jane Smith", "REDACTED"),
        ("3", "Alice Brown", "REDACTED"),
    ]


def test_row_ids_follow_source_order_across_partitions(spark, write_csv, output_path, tmp_path):
    content = "ID,Email\n" + "".join(f"{i},user{i}@example.com\n" for i in range(5000))
    spark.conf.set("spark.sql.files.maxPartitionBytes", "16k")
    try:
        stats = run_regex_replace(spark, make_spec(write_csv(content), output_path))
    finally:
        spark.conf.unset("spark.sql.files.maxPartitionBytes")

    assert len(list((tmp_path / "output").glob("part-*.parquet"))) > 1
    ids = [row["ID"] for row in spark.read.parquet(output_path).orderBy(ROW_ID_COLUMN).collect()]
    assert ids == [str(i) for i in range(5000)]
    assert stats == RunStats(row_count=5000, matched_count=5000)


def test_counts_only_rows_that_matched(spark, write_csv, output_path):
    source = write_csv("ID,Email\n1,a@example.com\n2,not an email\n3,\n")

    stats = run_regex_replace(spark, make_spec(source, output_path))

    assert stats == RunStats(row_count=3, matched_count=1)


def test_header_only_file_produces_empty_output(spark, write_csv, output_path):
    stats = run_regex_replace(spark, make_spec(write_csv("ID,Email\n"), output_path))

    assert stats == RunStats(row_count=0, matched_count=0)


def test_missing_source_raises_source_read_error(spark, tmp_path, output_path):
    with pytest.raises(SourceReadError, match="Could not read the source file"):
        run_regex_replace(spark, make_spec(str(tmp_path / "missing.csv"), output_path))


def test_missing_column_fails_before_writing(spark, write_csv, output_path, tmp_path):
    spec = replace(make_spec(write_csv(BRIEF_CSV), output_path), columns=("Phone",))

    with pytest.raises(ColumnNotFoundError):
        run_regex_replace(spark, spec)

    assert not (tmp_path / "output").exists()
