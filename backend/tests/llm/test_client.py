from types import SimpleNamespace

import anthropic
import httpx2
import pydantic
import pytest

from apps.llm.client import FALLBACK_BETA, ClaudeRegexGenerator, get_regex_generator
from apps.llm.exceptions import (
    LLMInvalidResponse,
    LLMNotConfigured,
    LLMRefused,
    LLMRequestFailed,
    LLMUnavailable,
)
from apps.llm.prompts.regex import SYSTEM_PROMPT
from apps.llm.schemas import RegexSuggestion
from tests.llm.conftest import make_suggestion

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(error_class, status: int):
    return error_class("error", response=httpx2.Response(status, request=REQUEST), body=None)


class FakeMessages:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def generator_returning(outcome) -> tuple[ClaudeRegexGenerator, FakeMessages]:
    messages = FakeMessages(outcome)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeRegexGenerator(client, "claude-opus-5"), messages


def response(stop_reason="end_turn", parsed_output=None):
    return SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=parsed_output,
        model="claude-opus-5",
        _request_id="req_test",
    )


def test_returns_structured_suggestion_and_sends_expected_request():
    suggestion = make_suggestion()
    generator, messages = generator_returning(response(parsed_output=suggestion))

    assert generator.generate("find email addresses") == suggestion

    [call] = messages.calls
    assert call["model"] == "claude-opus-5"
    assert call["output_format"] is RegexSuggestion
    assert call["system"] == SYSTEM_PROMPT
    assert (call["fallbacks"], call["betas"]) == ("default", [FALLBACK_BETA])
    assert call["messages"] == [{"role": "user", "content": "Description: find email addresses"}]


def test_refusal_raises_llm_refused():
    generator, _ = generator_returning(response(stop_reason="refusal"))

    with pytest.raises(LLMRefused):
        generator.generate("anything")


@pytest.mark.parametrize(
    "outcome",
    [
        response(stop_reason="max_tokens"),
        response(parsed_output=None),
        pydantic.ValidationError.from_exception_data("RegexSuggestion", []),
    ],
)
def test_unusable_output_raises_invalid_response(outcome):
    generator, _ = generator_returning(outcome)

    with pytest.raises(LLMInvalidResponse):
        generator.generate("anything")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (status_error(anthropic.RateLimitError, 429), LLMUnavailable),
        (status_error(anthropic.InternalServerError, 500), LLMUnavailable),
        (status_error(anthropic.ServiceUnavailableError, 503), LLMUnavailable),
        (status_error(anthropic.OverloadedError, 529), LLMUnavailable),
        (anthropic.APIConnectionError(request=REQUEST), LLMUnavailable),
        (anthropic.APITimeoutError(request=REQUEST), LLMUnavailable),
        (status_error(anthropic.AuthenticationError, 401), LLMNotConfigured),
        (status_error(anthropic.NotFoundError, 404), LLMNotConfigured),
        (status_error(anthropic.BadRequestError, 400), LLMRequestFailed),
    ],
)
def test_sdk_errors_map_to_domain_errors(error, expected):
    generator, _ = generator_returning(error)

    with pytest.raises(expected):
        generator.generate("anything")


def test_factory_requires_an_api_key(settings):
    settings.ANTHROPIC_API_KEY = ""

    with pytest.raises(LLMNotConfigured):
        get_regex_generator()


def test_factory_uses_configured_model(settings):
    settings.ANTHROPIC_API_KEY = "sk-ant-test"
    settings.LLM_MODEL = "claude-opus-5"

    generator = get_regex_generator()

    assert isinstance(generator, ClaudeRegexGenerator)
    assert generator.model == "claude-opus-5"
