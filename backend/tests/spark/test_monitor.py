import threading
import time

import pytest

from processing.progress import SparkJobMonitor


def test_monitor_tracks_and_cancels_a_real_spark_job_group(spark):
    context = spark.sparkContext
    fractions: list[float] = []
    progress_seen = threading.Event()

    def on_fraction(fraction: float) -> None:
        fractions.append(fraction)
        progress_seen.set()  # once the job is visible, ask for cancellation

    context.setJobGroup("monitor-test", "monitor test", True)
    started = time.monotonic()
    try:
        with SparkJobMonitor(
            context,
            "monitor-test",
            on_fraction=on_fraction,
            should_cancel=progress_seen.is_set,
            interval=0.2,
        ):
            with pytest.raises(Exception, match="(?i)cancel"):
                # Far too large to finish: only cancellation can end it.
                spark.range(0, 10**12, numPartitions=4).selectExpr("sum(id)").collect()
    finally:
        context.setLocalProperty("spark.jobGroup.id", None)

    assert fractions and all(0.0 <= fraction <= 1.0 for fraction in fractions)
    assert time.monotonic() - started < 60
