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
    # Upper bound on bytes per input partition when reading files. Smaller partitions mean
    # more, shorter tasks: better parallelism and finer-grained progress reporting.
    max_partition_bytes: str = "128m"
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
        "spark.sql.files.maxPartitionBytes": config.max_partition_bytes,
        "spark.sql.adaptive.enabled": "true",
        "spark.sql.adaptive.coalescePartitions.enabled": "true",
        # Unparseable dates become null instead of raising; format normalization relies on it.
        "spark.sql.legacy.timeParserPolicy": "CORRECTED",
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


def apply_s3_credentials(spark: SparkSession, config: SparkConfig) -> None:
    """Point the running session's S3A filesystem at one set of credentials.

    The session is created once per worker process but each job carries its own keys, so
    they are set on the live Hadoop configuration rather than at build time. The worker
    runs one job at a time (concurrency 1), so there is no cross-job interference; a
    multi-slot worker would need one session per slot, or per-bucket configuration.
    """
    hadoop_conf = spark.sparkContext._jsc.hadoopConfiguration()
    prefix = "spark.hadoop."
    for key, value in build_spark_conf(config).items():
        if key.startswith(prefix + "fs.s3a."):
            hadoop_conf.set(key[len(prefix) :], value)
    if not (config.aws_access_key_id and config.aws_secret_access_key):
        # Fall back to the default chain rather than reusing a previous job's keys.
        hadoop_conf.unset("fs.s3a.access.key")
        hadoop_conf.unset("fs.s3a.secret.key")
    if not config.s3_endpoint_url:
        hadoop_conf.unset("fs.s3a.endpoint")
        hadoop_conf.set("fs.s3a.path.style.access", "false")


def s3a_uri(bucket: str, key: str) -> str:
    return f"s3a://{bucket}/{key.lstrip('/')}"
