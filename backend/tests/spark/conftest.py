import os
from pathlib import Path

import pytest

from processing.spark_session import SparkConfig, get_spark_session

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"

BRIEF_CSV = (
    "ID,Name,Email\n"
    "1,John Doe,john.doe@example.com\n"
    "2,Jane Smith,jane_smith@domain.com\n"
    "3,Alice Brown,alice.brown@website.org\n"
)


@pytest.fixture(scope="session")
def spark():
    session = get_spark_session(
        SparkConfig(
            app_name="tests",
            master="local[2]",
            driver_memory="1g",
            shuffle_partitions=2,
            jars_dir=os.environ.get("SPARK_JARS_DIR"),
        )
    )
    yield session
    session.stop()


@pytest.fixture
def write_csv(tmp_path):
    def factory(content: str, name: str = "source.csv") -> str:
        path: Path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return str(path)

    return factory
