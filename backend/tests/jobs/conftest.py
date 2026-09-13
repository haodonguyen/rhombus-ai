import duckdb
import pytest


@pytest.fixture
def write_result_parts(tmp_path):
    """Write Parquet part files shaped like Spark's output: __row_id, data, __matched."""

    def factory(parts: list[list[tuple]]) -> str:
        directory = tmp_path / "result"
        directory.mkdir()
        with duckdb.connect() as connection:
            for index, rows in enumerate(parts):
                connection.execute(
                    "CREATE OR REPLACE TABLE part "
                    "(__row_id BIGINT, Name VARCHAR, Email VARCHAR, __matched BOOLEAN)"
                )
                if rows:
                    connection.executemany("INSERT INTO part VALUES (?, ?, ?, ?)", rows)
                path = directory / f"part-{index:05d}.parquet"
                connection.execute(f"COPY part TO '{path}' (FORMAT PARQUET)")
        return str(directory)

    return factory
