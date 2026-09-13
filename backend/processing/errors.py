"""Failures caused by the input data or request, as opposed to infrastructure faults.

The task layer records `code` and the message on the job; anything else is treated as an
unexpected internal error.
"""

from collections.abc import Sequence


class ProcessingError(Exception):
    code = "PROCESSING_ERROR"


class ColumnNotFoundError(ProcessingError):
    code = "COLUMN_NOT_FOUND"

    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = list(missing)
        super().__init__(f"Column(s) not found in the source file: {', '.join(self.missing)}")


class SourceReadError(ProcessingError):
    code = "SOURCE_READ_ERROR"


class InvalidPatternError(ProcessingError):
    code = "INVALID_PATTERN"


def describe_error(exc: BaseException, limit: int = 300) -> str:
    """First line of an exception message, including JVM exceptions surfaced through Py4J."""
    java_exception = getattr(exc, "java_exception", None)
    text = java_exception.toString() if java_exception is not None else str(exc)
    lines = text.strip().splitlines()
    return (lines[0] if lines else type(exc).__name__)[:limit]
