"""Adapter from Django settings to the framework-free processing layer's Spark config."""

from django.conf import settings

from processing.spark_session import SparkConfig


def spark_config_from_settings(app_name: str = "nl-regex") -> SparkConfig:
    return SparkConfig(
        app_name=app_name,
        master=settings.SPARK_MASTER,
        driver_memory=settings.SPARK_DRIVER_MEMORY,
        shuffle_partitions=settings.SPARK_SHUFFLE_PARTITIONS,
        max_partition_bytes=settings.SPARK_MAX_PARTITION_BYTES,
        jars_dir=settings.SPARK_JARS_DIR,
        s3_endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        aws_region=settings.AWS_REGION,
    )
