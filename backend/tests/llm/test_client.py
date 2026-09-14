from types import SimpleNamespace

import httpx
import ollama
import pytest

from apps.llm.client import GENERATION_OPTIONS, OllamaRegexGenerator, get_regex_generator
from apps.llm.exceptions import (
    LLMInvalidResponse,
    LLMNotConfigured,
    LLMRequestFailed,
    LLMUnavailable,
)
from apps.llm.prompts.regex import SYSTEM_PROMPT
from apps.llm.schemas import RegexSuggestion
from tests.llm.conftest import make_suggestion

MODEL = "qwen2.5-coder:3b"
REQUEST = httpx.Request("POST", "http://ollama:11434/api/chat")


class FakeClient:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def response(content: str, done_reason: str = "stop"):
    return SimpleNamespace(done_reason=done_reason, message=SimpleNamespace(content=content))


def generator_returning(outcome) -> tuple[OllamaRegexGenerator, FakeClient]:
    client = FakeClient(outcome)
    return OllamaRegexGenerator(client, MODEL), client


def test_returns_structured_suggestion_and_sends_expected_request():
    suggestion = make_suggestion()
    generator, client = generator_returning(response(suggestion.model_dump_json()))

    assert generator.generate("find email addresses") == suggestion

    [call] = client.calls
    assert call["model"] == MODEL
    assert call["format"] == RegexSuggestion.model_json_schema()
    assert call["options"] == GENERATION_OPTIONS
    assert call["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Description: find email addresses"},
    ]


@pytest.mark.parametrize(
    "outcome",
    [
        response("not json"),
        response('{"pattern": "x"}'),
        response('{"feasible": true}', done_reason="length"),
    ],
    ids=["invalid-json", "missing-fields", "truncated"],
)
def test_unusable_output_raises_invalid_response(outcome):
    generator, _ = generator_returning(outcome)

    with pytest.raises(LLMInvalidResponse):
        generator.generate("anything")


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ConnectionError("Failed to connect to Ollama"), LLMUnavailable),
        (httpx.ReadTimeout("timed out", request=REQUEST), LLMUnavailable),
        (ollama.ResponseError("server busy", status_code=503), LLMUnavailable),
        (ollama.ResponseError("model 'x' not found", status_code=404), LLMNotConfigured),
        (ollama.ResponseError("invalid format", status_code=400), LLMRequestFailed),
    ],
    ids=["unreachable", "timeout", "busy", "model-missing", "bad-request"],
)
def test_client_errors_map_to_domain_errors(error, expected):
    generator, _ = generator_returning(error)

    with pytest.raises(expected):
        generator.generate("anything")


def test_factory_requires_a_server_url(settings):
    settings.LLM_BASE_URL = ""

    with pytest.raises(LLMNotConfigured):
        get_regex_generator()


def test_factory_uses_configured_server_and_model(settings):
    settings.LLM_BASE_URL = "http://ollama:11434"
    settings.LLM_MODEL = MODEL

    generator = get_regex_generator()

    assert isinstance(generator, OllamaRegexGenerator)
    assert generator.model == MODEL
