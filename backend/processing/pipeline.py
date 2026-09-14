"""End-to-end runs: read source -> build the transformation -> write Parquet -> collect stats.

Framework-free: callers supply the SparkSession, a function that builds the transformed
DataFrame from the source, an optional stage callback (the task layer reports progress with
it) and an optional job group (used to monitor and cancel the run's Spark jobs).
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum

from py4j.protocol import Py4JJavaError
from pyspark.errors.exceptions.captured import CapturedException
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from processing.errors import (
    ProcessingError,
    SourceReadError,
    SourceUnavailableError,
    describe_error,
    error_text,
    is_transient_storage_error,
)
from processing.file_types import FileType
from processing.pipeline_stats import RunStats
from processing.readers import read_source, with_row_id
from processing.schema import MATCHED_COLUMN
from processing.transforms.regex_replace import regex_replace
from processing.writers import write_parquet

__all__ = [
    "Builder",
    "RegexReplaceSpec",
    "RunStats",
    "Stage",
    "run_regex_replace",
    "run_transform",
]

_SPARK_ERRORS = (CapturedException, Py4JJavaError)

# Builds the transformed DataFrame from the source. It may run small Spark actions first,
# such as sampling values for an LLM, but returns a lazy plan over the full data.
Builder = Callable[[DataFrame], DataFrame]


class Stage(StrEnum):
    LOADING = "LOADING"
    TRANSFORMING = "TRANSFORMING"
    FINALIZING = "FINALIZING"


StageCallback = Callable[[str], None]


@dataclass(frozen=True)
class RegexReplaceSpec:
    source_uri: str
    file_type: FileType
    columns: Sequence[str]
    pattern: str
    replacement: str
    output_path: str


def run_transform(
    spark: SparkSession,
    *,
    source_uri: str,
    file_type: FileType,
    output_path: str,
    build: Builder,
    on_stage: StageCallback | None = None,
    job_group: str | None = None,
) -> RunStats:
    notify = on_stage or (lambda _stage: None)
    if job_group:
        # Tag every Spark job below so it can be monitored and cancelled as a unit.
        spark.sparkContext.setJobGroup(job_group, f"transform {job_group}", True)

    notify(Stage.LOADING)
    source = load_source(spark, source_uri, file_type)
    with _spark_errors_as_source_errors():
        transformed = build(source)

    notify(Stage.TRANSFORMING)
    # Transform and write are a single Spark action: one pass over the data.
    with _storage_outages_as_unavailable():
        write_parquet(transformed, output_path)

    notify(Stage.FINALIZING)
    return collect_stats(spark, output_path)


def run_regex_replace(
    spark: SparkSession,
    spec: RegexReplaceSpec,
    on_stage: StageCallback | None = None,
    job_group: str | None = None,
) -> RunStats:
    return run_transform(
        spark,
        source_uri=spec.source_uri,
        file_type=spec.file_type,
        output_path=spec.output_path,
        build=lambda df: regex_replace(df, spec.columns, spec.pattern, spec.replacement),
        on_stage=on_stage,
        job_group=job_group,
    )


def load_source(spark: SparkSession, uri: str, file_type: FileType) -> DataFrame:
    try:
        return with_row_id(read_source(spark, uri, file_type))
    except _SPARK_ERRORS as exc:
        raise _source_error(exc) from exc


def collect_stats(spark: SparkSession, output_path: str) -> RunStats:
    """Count rows and matches from the written Parquet, which reads a single column."""
    row = (
        spark.read.parquet(output_path)
        .agg(
            F.count(F.lit(1)).alias("rows"),
            F.coalesce(F.sum(F.col(MATCHED_COLUMN).cast("long")), F.lit(0)).alias("matched"),
        )
        .first()
    )
    return RunStats(row_count=int(row["rows"]), matched_count=int(row["matched"]))


def _source_error(exc: BaseException) -> ProcessingError:
    if is_transient_storage_error(error_text(exc)):
        return SourceUnavailableError(
            f"The source file could not be reached: {describe_error(exc)}"
        )
    return SourceReadError(f"Could not read the source file: {describe_error(exc)}")


@contextmanager
def _spark_errors_as_source_errors() -> Iterator[None]:
    """Spark reads lazily, so the first action (e.g. sampling) is where read errors surface."""
    try:
        yield
    except _SPARK_ERRORS as exc:
        raise _source_error(exc) from exc


@contextmanager
def _storage_outages_as_unavailable() -> Iterator[None]:
    """Data is read lazily during the write, so storage outages can surface here too."""
    try:
        yield
    except _SPARK_ERRORS as exc:
        if is_transient_storage_error(error_text(exc)):
            raise SourceUnavailableError(
                f"The source file could not be reached: {describe_error(exc)}"
            ) from exc
        raise
