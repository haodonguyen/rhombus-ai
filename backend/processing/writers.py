from pyspark.sql import DataFrame


def write_parquet(df: DataFrame, path: str) -> None:
    """Write results as Parquet, replacing any previous output (keeps re-runs idempotent)."""
    df.write.mode("overwrite").parquet(path)
