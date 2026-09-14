"""Job progress: stage-weighted percentages and a Spark job-group monitor.

No PySpark import. The monitor only calls methods on the SparkContext it is given, so it
can be unit-tested with a fake.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterable

logger = logging.getLogger(__name__)

# Overall percentage range for each stage. TRANSFORMING is the pass over the data, so it
# gets most of the bar; 100 is reserved for success. GENERATING_REGEX runs before the data
# is read (find and replace); GENERATING_SPEC runs after sampling it (other transforms).
STAGE_RANGES: dict[str, tuple[int, int]] = {
    "GENERATING_REGEX": (0, 5),
    "LOADING": (5, 8),
    "GENERATING_SPEC": (8, 10),
    "TRANSFORMING": (10, 90),
    "FINALIZING": (90, 99),
}


def task_fraction(stages: Iterable[tuple[int, int]]) -> float:
    """Completed / total tasks across Spark stages, from `(num_tasks, num_completed)` pairs."""
    total = completed = 0
    for num_tasks, num_completed in stages:
        total += num_tasks
        completed += min(num_completed, num_tasks)
    return completed / total if total else 0.0


class ProgressTracker:
    """Turns stage changes and within-stage fractions into a percentage that only grows.

    Stage changes are always emitted. Fraction updates are emitted at most once per
    `min_interval` seconds, so frequent polling does not flood the database. The tracker
    is thread-safe: the task thread enters stages while the Spark monitor reports
    fractions, and emitting under the lock keeps writes in order.
    """

    def __init__(
        self,
        emit: Callable[[str, int], None],
        min_interval: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._emit = emit
        self._min_interval = min_interval
        self._clock = clock
        self._lock = threading.Lock()
        self._stage = ""
        self._percent = 0
        self._last_emit = float("-inf")

    @property
    def percent(self) -> int:
        return self._percent

    def enter_stage(self, stage: str) -> None:
        start, _ = STAGE_RANGES[stage]
        with self._lock:
            self._stage = stage
            self._percent = max(self._percent, start)
            self._last_emit = self._clock()
            self._emit(self._stage, self._percent)

    def update_fraction(self, fraction: float) -> None:
        with self._lock:
            if self._stage not in STAGE_RANGES:
                return
            start, end = STAGE_RANGES[self._stage]
            percent = start + int((end - start) * min(max(fraction, 0.0), 1.0))
            now = self._clock()
            if percent <= self._percent or now - self._last_emit < self._min_interval:
                return
            self._percent = percent
            self._last_emit = now
            self._emit(self._stage, percent)


class SparkJobMonitor:
    """Background thread that watches one Spark job group while it runs.

    On every tick it reports the fraction of completed tasks, and it cancels the group
    once `should_cancel()` returns true. Monitoring must never break the job, so errors
    raised by callbacks or Spark are logged and ignored.
    """

    def __init__(
        self,
        spark_context,
        job_group: str,
        on_fraction: Callable[[float], None],
        should_cancel: Callable[[], bool] = lambda: False,
        interval: float = 1.0,
        on_thread_exit: Callable[[], None] | None = None,
    ) -> None:
        self._context = spark_context
        self._job_group = job_group
        self._on_fraction = on_fraction
        self._should_cancel = should_cancel
        self._interval = interval
        self._on_thread_exit = on_thread_exit
        self._stop = threading.Event()
        self._cancelled = False
        self._thread = threading.Thread(
            target=self._run, name=f"spark-monitor-{job_group}", daemon=True
        )

    def __enter__(self) -> "SparkJobMonitor":
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval * 5)

    def fraction(self) -> float | None:
        """Task completion across the group's jobs, or None before any job has started."""
        tracker = self._context.statusTracker()
        stages = []
        for job_id in tracker.getJobIdsForGroup(self._job_group):
            job = tracker.getJobInfo(job_id)
            if job is None:
                continue
            for stage_id in job.stageIds:
                stage = tracker.getStageInfo(stage_id)
                if stage is not None:
                    stages.append((stage.numTasks, stage.numCompletedTasks))
        return task_fraction(stages) if stages else None

    def _run(self) -> None:
        try:
            while not self._stop.wait(self._interval):
                self._tick()
        finally:
            if self._on_thread_exit is not None:
                self._on_thread_exit()

    def _tick(self) -> None:
        try:
            if not self._cancelled and self._should_cancel():
                self._cancelled = True
                logger.info("Cancelling Spark job group %s", self._job_group)
                self._context.cancelJobGroup(self._job_group)
            fraction = self.fraction()
            if fraction is not None:
                self._on_fraction(fraction)
        except Exception:
            logger.warning("Spark progress monitoring failed", exc_info=True)
