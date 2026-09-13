"""Infrastructure tasks used to verify the worker environment end to end."""

from pathlib import Path
from typing import Any

from celery import shared_task
from django.conf import settings

from apps.core.spark import spark_config_from_settings
from processing.spark_session import get_spark_session, s3a_uri


@shared_task(name="core.ping")
def ping() -> str:
    return "pong"


@shared_task(name="core.spark_smoke_test")
def spark_smoke_test(
    csv_key: str = "samples/customers.csv",
    xlsx_key: str = "samples/customers.xlsx",
) -> dict[str, Any]:
    """Read a CSV and an XLSX from S3 through S3A, write each to Parquet and read it back.

    Proves the worker image has compatible Spark, hadoop-aws and spark-excel jars.
    """
    spark = get_spark_session(spark_config_from_settings(app_name="spark-smoke-test"))
    bucket = settings.S3_BUCKET
    output_root = Path(settings.RESULTS_PATH) / "_smoke"

    readers = {
        "csv": spark.read.option("header", True)
        .option("inferSchema", False)
        .csv(s3a_uri(bucket, csv_key)),
        "xlsx": spark.read.format("com.crealytics.spark.excel")
        .option("header", True)
        .option("inferSchema", False)
        .load(s3a_uri(bucket, xlsx_key)),
    }

    jvm = spark.sparkContext._jvm
    result: dict[str, Any] = {
        "spark_version": spark.version,
        "hadoop_version": jvm.org.apache.hadoop.util.VersionInfo.getVersion(),
        "java_version": jvm.java.lang.System.getProperty("java.version"),
    }
    for name, df in readers.items():
        output_path = str(output_root / name)
        df.write.mode("overwrite").parquet(output_path)
        result[name] = {
            "columns": df.columns,
            "source_rows": df.count(),
            "parquet_rows": spark.read.parquet(output_path).count(),
            "partitions": df.rdd.getNumPartitions(),
            "output_path": output_path,
        }
    return result
