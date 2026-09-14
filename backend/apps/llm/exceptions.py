"""Failures while turning a description into a pattern.

The task layer records `code` and the message on the job, so messages must be safe to
show to end users. Details belong in logs. `retryable` errors are retried by the task.
"""


class LLMError(Exception):
    code = "LLM_ERROR"
    default_message = "The language model could not produce a pattern."
    retryable = False

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class LLMNotConfigured(LLMError):
    code = "LLM_NOT_CONFIGURED"
    default_message = (
        "Natural-language patterns are not available because the language model is not "
        "configured. Enter a regex instead."
    )


class LLMUnavailable(LLMError):
    """Transient: server unreachable, overloaded or timed out. Worth retrying later."""

    code = "LLM_UNAVAILABLE"
    default_message = "The language model is temporarily unavailable. Please try again shortly."
    retryable = True


class LLMRequestFailed(LLMError):
    code = "LLM_REQUEST_FAILED"
    default_message = "The request to the language model failed."


class LLMInvalidResponse(LLMError):
    code = "LLM_INVALID_RESPONSE"
    default_message = (
        "The language model returned an unusable answer. Try rephrasing the description."
    )


class PatternNotExpressible(LLMError):
    code = "PATTERN_NOT_EXPRESSIBLE"
    default_message = "This description cannot be expressed as a regular expression."


class NormalizationNotPossible(LLMError):
    code = "NORMALIZATION_NOT_POSSIBLE"
    default_message = "The requested format cannot be produced by reformatting the values."
