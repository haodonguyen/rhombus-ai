import threading
import time
from types import SimpleNamespace

import pytest

from processing.progress import STAGE_RANGES, ProgressTracker, SparkJobMonitor, task_fraction

# --- task_fraction ------------------------------------------------------------------


def test_task_fraction_sums_across_stages():
    assert task_fraction([(4, 2), (6, 6)]) == 0.8


def test_task_fraction_without_tasks_is_zero():
    assert task_fraction([]) == 0.0


def test_task_fraction_caps_completed_at_total():
    assert task_fraction([(2, 5)]) == 1.0


def test_stage_ranges_are_ordered_and_leave_100_for_success():
    ranges = list(STAGE_RANGES.values())
    assert all(start < end for start, end in ranges)
    assert all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:], strict=False))
    assert ranges[-1][1] < 100


# --- ProgressTracker ----------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def emitted() -> list[tuple[str, int]]:
    return []


@pytest.fixture
def tracker(emitted, clock) -> ProgressTracker:
    return ProgressTracker(lambda stage, pct: emitted.append((stage, pct)), clock=clock)


def test_stage_changes_emit_the_stage_start(tracker, emitted):
    tracker.enter_stage("LOADING")
    tracker.enter_stage("TRANSFORMING")

    assert emitted == [("LOADING", 5), ("TRANSFORMING", 10)]


def test_fraction_maps_into_the_stage_range_and_is_throttled(tracker, emitted, clock):
    tracker.enter_stage("TRANSFORMING")
    clock.now = 0.5
    tracker.update_fraction(0.5)  # within the throttle window
    clock.now = 1.5
    tracker.update_fraction(0.5)
    clock.now = 3.0
    tracker.update_fraction(1.0)

    assert emitted == [("TRANSFORMING", 10), ("TRANSFORMING", 50), ("TRANSFORMING", 90)]


def test_progress_never_goes_backwards(tracker, emitted, clock):
    tracker.enter_stage("TRANSFORMING")
    clock.now = 2.0
    tracker.update_fraction(0.75)
    clock.now = 4.0
    tracker.update_fraction(0.25)
    tracker.enter_stage("LOADING")

    assert tracker.percent == 70
    assert emitted[-1] == ("LOADING", 70)


def test_fraction_before_any_stage_is_ignored(tracker, emitted):
    tracker.update_fraction(0.5)

    assert emitted == []


# --- SparkJobMonitor ----------------------------------------------------------------


class FakeStatusTracker:
    def __init__(self, stages: dict[int, tuple[int, int]]) -> None:
        self.stages = stages

    def getJobIdsForGroup(self, group):  # noqa: N802 - mirrors PySpark's API
        return [7] if group == "job-1" else []

    def getJobInfo(self, job_id):  # noqa: N802
        return SimpleNamespace(stageIds=list(self.stages))

    def getStageInfo(self, stage_id):  # noqa: N802
        num_tasks, completed = self.stages[stage_id]
        return SimpleNamespace(numTasks=num_tasks, numCompletedTasks=completed)


class FakeSparkContext:
    def __init__(self) -> None:
        self.tracker = FakeStatusTracker({1: (4, 1), 2: (4, 3)})
        self.cancelled: list[str] = []

    def statusTracker(self):  # noqa: N802
        return self.tracker

    def cancelJobGroup(self, group):  # noqa: N802
        self.cancelled.append(group)


def test_monitor_reports_completion_for_its_job_group():
    monitor = SparkJobMonitor(FakeSparkContext(), "job-1", on_fraction=lambda f: None)

    assert monitor.fraction() == 0.5


def test_monitor_returns_none_before_any_job_in_the_group():
    monitor = SparkJobMonitor(FakeSparkContext(), "other", on_fraction=lambda f: None)

    assert monitor.fraction() is None


def test_monitor_thread_reports_cancels_once_and_cleans_up():
    context = FakeSparkContext()
    fractions: list[float] = []
    exits: list[bool] = []
    enough = threading.Event()

    def on_fraction(fraction: float) -> None:
        fractions.append(fraction)
        if len(fractions) >= 3:
            enough.set()

    with SparkJobMonitor(
        context,
        "job-1",
        on_fraction=on_fraction,
        should_cancel=lambda: True,
        interval=0.01,
        on_thread_exit=lambda: exits.append(True),
    ):
        assert enough.wait(timeout=2)

    assert context.cancelled == ["job-1"]
    assert fractions[0] == 0.5
    assert exits == [True]


def test_monitor_survives_callback_errors():
    calls: list[float] = []

    def failing(fraction: float) -> None:
        calls.append(fraction)
        raise RuntimeError("database unavailable")

    with SparkJobMonitor(FakeSparkContext(), "job-1", on_fraction=failing, interval=0.01):
        deadline = time.monotonic() + 2
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)

    assert len(calls) >= 2
