from dataclasses import dataclass


@dataclass(frozen=True)
class RunStats:
    """Outcome of a transformation run. PySpark-free, so the web process can import it."""

    row_count: int
    matched_count: int
