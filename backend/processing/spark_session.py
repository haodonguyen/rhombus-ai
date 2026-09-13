"""SparkSession factory.

Callers pass an explicit SparkConfig so this module stays independent of Django.
PySpark is imported lazily, so the configuration helpers work in images without it.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


@dataclass(frozen=True)
class SparkConfig:
    app_name: str = "nl-regex"
    master: str = "local[*]"
    driver_memory: str = "2g"
    shuffle_partitions: int = 8
    jars_dir: str | None = None
    s3_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str | None = None


def build_spark_conf(config: SparkConfig) -> dict[str, str]:
    """Translate a SparkConfig into Spark/Hadoop configuration keys."""
    conf = {
        "spark.driver.memory": config.driver_memory,
        "spark.sql.shuffle.partitions": str(config.shuffle_partitions),
        "spark.sql.adaptive.enabled": "true",
        "spark.sql.adaptive.coalescePartitions.enabled": "true",
        "spark.ui.showConsoleProgress": "false",
        "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
    }

    if config.jars_dir:
        jars = sorted(glob.glob(os.path.join(config.jars_dir, "*.jar")))
        if jars:
            conf["spark.jars"] = ",".join(jars)

    # Without static keys, S3A falls back to its default chain (env vars, IAM role).
    if config.aws_access_key_id and config.aws_secret_access_key:
        conf["spark.hadoop.fs.s3a.aws.credentials.provider"] = (
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider"
        )
        conf["spark.hadoop.fs.s3a.access.key"] = config.aws_access_key_id
        conf["spark.hadoop.fs.s3a.secret.key"] = config.aws_secret_access_key

    if config.aws_region:
        conf["spark.hadoop.fs.s3a.endpoint.region"] = config.aws_region

    if config.s3_endpoint_url:
        conf["spark.hadoop.fs.s3a.endpoint"] = config.s3_endpoint_url
        conf["spark.hadoop.fs.s3a.path.style.access"] = "true"
        conf["spark.hadoop.fs.s3a.connection.ssl.enabled"] = str(
            config.s3_endpoint_url.startswith("https://")
        ).lower()

    return conf


def get_spark_session(config: SparkConfig) -> SparkSession:
    """Return the process-wide SparkSession, creating it on first use."""
    from pyspark.sql import SparkSession

    builder = SparkSession.builder.appName(config.app_name).master(config.master)
    for key, value in build_spark_conf(config).items():
        builder = builder.config(key, value)
    return builder.getOrCreate()


def s3a_uri(bucket: str, key: str) -> str:
    return f"s3a://{bucket}/{key.lstrip('/')}"
