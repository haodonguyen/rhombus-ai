"""Failures caused by the input data or request, or by the storage a job reads from.

The task layer records `code` and the message on the job. Errors marked `retryable` are
transient (e.g. storage briefly unreachable), so the task retries them before failing.
"""

from collections.abc import Sequence


class ProcessingError(Exception):
    code = "PROCESSING_ERROR"
    retryable = False


class ColumnNotFoundError(ProcessingError):
    code = "COLUMN_NOT_FOUND"

    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = list(missing)
        super().__init__(f"Column(s) not found in the source file: {', '.join(self.missing)}")


class SourceReadError(ProcessingError):
    code = "SOURCE_READ_ERROR"


class SourceUnavailableError(ProcessingError):
    """The source could not be reached (network or S3 outage), rather than being unreadable."""

    code = "STORAGE_UNAVAILABLE"
    retryable = True


class InvalidPatternError(ProcessingError):
    code = "INVALID_PATTERN"


# Text found in JVM errors when the storage endpoint was unreachable, as opposed to the
# data or path being wrong.
_TRANSIENT_STORAGE_MARKERS = (
    "java.net.ConnectException",
    "java.net.SocketTimeoutException",
    "java.net.UnknownHostException",
    "org.apache.hadoop.fs.s3a.AWSClientIOException",
    "com.amazonaws.SdkClientException",
    "Unable to execute HTTP request",
    "Connection refused",
    "503 Service Unavailable",
    "SlowDown",
)


def is_transient_storage_error(text: str) -> bool:
    return any(marker in text for marker in _TRANSIENT_STORAGE_MARKERS)


def error_text(exc: BaseException, max_depth: int = 10) -> str:
    """The exception's message plus, for JVM errors surfaced through Py4J, its cause chain."""
    texts = [str(exc)]
    java = getattr(exc, "java_exception", None) or getattr(exc, "_origin", None)
    for _ in range(max_depth):
        if java is None:
            break
        texts.append(str(java.toString()))
        java = java.getCause()
    return "\n".join(texts)


def describe_error(exc: BaseException, limit: int = 300) -> str:
    """First line of an exception message, including JVM exceptions surfaced through Py4J."""
    java_exception = getattr(exc, "java_exception", None)
    text = java_exception.toString() if java_exception is not None else str(exc)
    lines = text.strip().splitlines()
    return (lines[0] if lines else type(exc).__name__)[:limit]
