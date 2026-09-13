"""Resolve Spark connector jars at image build time so workers never download at runtime.

hadoop-aws must match the Hadoop version bundled inside PySpark exactly, so that
version is read from the PySpark distribution rather than hard-coded.

Usage: python fetch_spark_jars.py <destination-dir>
"""

import glob
import os
import re
import shutil
import sys

import pyspark
from pyspark.sql import SparkSession

SPARK_EXCEL_PACKAGE = "com.crealytics:spark-excel_2.12:3.5.1_0.20.4"
IVY_DIR = "/tmp/ivy"


def bundled_hadoop_version() -> str:
    jars_dir = os.path.join(os.path.dirname(pyspark.__file__), "jars")
    for jar in glob.glob(os.path.join(jars_dir, "hadoop-client-api-*.jar")):
        match = re.search(r"hadoop-client-api-(.+)\.jar$", jar)
        if match:
            return match.group(1)
    raise RuntimeError(f"No hadoop-client-api jar found in {jars_dir}")


def main(destination: str) -> None:
    packages = [
        f"org.apache.hadoop:hadoop-aws:{bundled_hadoop_version()}",
        SPARK_EXCEL_PACKAGE,
    ]
    print(f"Resolving {packages}", flush=True)
    spark = (
        SparkSession.builder.master("local[1]")
        .config("spark.jars.packages", ",".join(packages))
        .config("spark.jars.ivy", IVY_DIR)
        .getOrCreate()
    )
    spark.stop()

    os.makedirs(destination, exist_ok=True)
    for jar in glob.glob(os.path.join(IVY_DIR, "jars", "*.jar")):
        shutil.copy(jar, destination)
    shutil.rmtree(IVY_DIR, ignore_errors=True)
    print("\n".join(sorted(os.listdir(destination))), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
