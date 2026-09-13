"""Serve result pages from a job's Parquet output with DuckDB. Never starts Spark.

Pages are ordered by ROW_ID_COLUMN. The ids are monotonic but not consecutive, so a page
is found in two steps. First, LIMIT/OFFSET over the id column alone gives the page's id
range. Then rows are fetched with a BETWEEN filter, which Parquet row-group statistics can
prune.
"""

import math
from dataclasses import dataclass

import duckdb

from apps.jobs.exceptions import ResultsUnavailable
from processing.schema import MATCHED_COLUMN, ROW_ID_COLUMN

MAX_PAGE_SIZE = 500


@dataclass(frozen=True)
class ResultRow:
    row_number: int
    matched: bool
    values: list[str | None]


@dataclass(frozen=True)
class ResultsPage:
    columns: list[str]
    rows: list[ResultRow]
    page: int
    page_size: int
    total_rows: int

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total_rows / self.page_size))


def read_results_page(result_path: str, total_rows: int, page: int, page_size: int) -> ResultsPage:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (page - 1) * page_size
    source = f"{result_path.rstrip('/')}/*.parquet"

    try:
        with duckdb.connect() as connection:
            # Keep the web process's footprint small; pages are tiny.
            connection.execute("SET threads = 2")
            connection.execute("SET memory_limit = '256MB'")
            low, high = connection.execute(
                f"SELECT min({ROW_ID_COLUMN}), max({ROW_ID_COLUMN}) FROM ("
                f"  SELECT {ROW_ID_COLUMN} FROM read_parquet(?)"
                f"  ORDER BY {ROW_ID_COLUMN} LIMIT ? OFFSET ?"
                ")",
                [source, page_size, offset],
            ).fetchone()
            cursor = connection.execute(
                f"SELECT * FROM read_parquet(?) WHERE {ROW_ID_COLUMN} BETWEEN ? AND ? "
                f"ORDER BY {ROW_ID_COLUMN}",
                [source, low, high],
            )
            names = [description[0] for description in cursor.description]
            records = cursor.fetchall()
    except duckdb.Error as exc:
        raise ResultsUnavailable() from exc

    data_indexes = [
        index for index, name in enumerate(names) if name not in (ROW_ID_COLUMN, MATCHED_COLUMN)
    ]
    matched_index = names.index(MATCHED_COLUMN)
    rows = [
        ResultRow(
            row_number=offset + position + 1,
            matched=bool(record[matched_index]),
            values=[record[index] for index in data_indexes],
        )
        for position, record in enumerate(records)
    ]
    return ResultsPage(
        columns=[names[index] for index in data_indexes],
        rows=rows,
        page=page,
        page_size=page_size,
        total_rows=total_rows,
    )
