from apps.llm.exceptions import LLMRefused, LLMUnavailable
from processing.errors import (
    SourceReadError,
    SourceUnavailableError,
    error_text,
    is_transient_storage_error,
)


def test_storage_outage_is_transient():
    message = (
        "org.apache.hadoop.fs.s3a.AWSClientIOException: getFileStatus on s3a://bucket/key: "
        "com.amazonaws.SdkClientException: Unable to execute HTTP request: Connect to "
        "minio:9000 failed: Connection refused"
    )

    assert is_transient_storage_error(message)


def test_missing_path_is_not_transient():
    assert not is_transient_storage_error(
        "[PATH_NOT_FOUND] Path does not exist: s3a://bucket/missing.csv."
    )


class FakeJavaException:
    def __init__(self, text: str, cause: "FakeJavaException | None" = None) -> None:
        self.text = text
        self.cause = cause

    def toString(self) -> str:  # noqa: N802 - mirrors the JVM API
        return self.text

    def getCause(self):  # noqa: N802
        return self.cause


def test_error_text_follows_the_java_cause_chain():
    exc = Exception("An error occurred while calling o42.load.")
    exc.java_exception = FakeJavaException(
        "java.io.IOException: read failed", FakeJavaException("java.net.ConnectException: refused")
    )

    text = error_text(exc)

    assert text.splitlines() == [
        "An error occurred while calling o42.load.",
        "java.io.IOException: read failed",
        "java.net.ConnectException: refused",
    ]
    assert is_transient_storage_error(text)


def test_retryable_flags():
    assert SourceUnavailableError.retryable and LLMUnavailable.retryable
    assert not SourceReadError.retryable and not LLMRefused.retryable
