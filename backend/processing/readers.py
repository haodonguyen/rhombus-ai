"""Load source files into Spark DataFrames, keeping every column as a string."""

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from processing.file_types import FileType
from processing.schema import ROW_ID_COLUMN

EXCEL_FORMAT = "com.crealytics.spark.excel"


def read_source(spark: SparkSession, uri: str, file_type: FileType) -> DataFrame:
    if file_type is FileType.CSV:
        return read_csv(spark, uri)
    if file_type is FileType.XLSX:
        return read_excel(spark, uri)
    raise ValueError(f"Unsupported file type: {file_type}")


def read_csv(spark: SparkSession, uri: str) -> DataFrame:
    # No schema inference: it costs a full extra pass and could reformat values.
    return (
        spark.read.option("header", True)
        .option("inferSchema", False)
        .option("mode", "PERMISSIVE")
        .option("encoding", "UTF-8")
        .csv(uri)
    )


def read_excel(spark: SparkSession, uri: str) -> DataFrame:
    # XLSX is a zip archive and cannot be split, so the read itself is a single task.
    return (
        spark.read.format(EXCEL_FORMAT)
        .option("header", True)
        .option("inferSchema", False)
        .load(uri)
    )


def with_row_id(df: DataFrame) -> DataFrame:
    """Prepend ROW_ID_COLUMN. Must run before any shuffle so ids follow source order."""
    return df.select(F.monotonically_increasing_id().alias(ROW_ID_COLUMN), "*")
