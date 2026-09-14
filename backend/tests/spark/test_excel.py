from pathlib import Path

import pytest
from openpyxl import Workbook

from processing.errors import SourceReadError
from processing.file_types import FileType
from processing.pipeline import RegexReplaceSpec, RunStats, run_regex_replace
from processing.schema import ROW_ID_COLUMN
from tests.spark.conftest import BRIEF_CSV, EMAIL_PATTERN

BRIEF_ROWS = [line.split(",") for line in BRIEF_CSV.strip().splitlines()]


def write_xlsx(path: Path, rows: list[list[str]]) -> str:
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    workbook.save(path)
    return str(path)


def make_spec(source_uri: str, file_type: FileType, output_path: str) -> RegexReplaceSpec:
    return RegexReplaceSpec(
        source_uri=source_uri,
        file_type=file_type,
        columns=("Email",),
        pattern=EMAIL_PATTERN,
        replacement="REDACTED",
        output_path=output_path,
    )


def test_xlsx_and_csv_sources_produce_identical_results(spark, tmp_path, write_csv):
    csv_output, xlsx_output = str(tmp_path / "from-csv"), str(tmp_path / "from-xlsx")
    xlsx_source = write_xlsx(tmp_path / "source.xlsx", BRIEF_ROWS)

    csv_stats = run_regex_replace(spark, make_spec(write_csv(BRIEF_CSV), FileType.CSV, csv_output))
    xlsx_stats = run_regex_replace(spark, make_spec(xlsx_source, FileType.XLSX, xlsx_output))

    def values(path: str) -> list[tuple]:
        rows = spark.read.parquet(path).orderBy(ROW_ID_COLUMN).collect()
        return [(row["ID"], row["Name"], row["Email"]) for row in rows]

    assert csv_stats == xlsx_stats == RunStats(row_count=3, matched_count=3)
    assert values(csv_output) == values(xlsx_output)


def test_corrupt_xlsx_is_a_source_read_error(spark, tmp_path):
    corrupt = tmp_path / "corrupt.xlsx"
    corrupt.write_bytes(b"this is not a zip archive")

    with pytest.raises(SourceReadError):
        run_regex_replace(spark, make_spec(str(corrupt), FileType.XLSX, str(tmp_path / "output")))
