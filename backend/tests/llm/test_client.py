from types import SimpleNamespace

import httpx
import ollama
import pytest

from apps.llm.client import GENERATION_OPTIONS, OllamaLLM, get_llm
from apps.llm.exceptions import (
    LLMInvalidResponse,
    LLMNotConfigured,
    LLMRequestFailed,
    LLMUnavailable,
)
from apps.llm.schemas import NormalizationSuggestion, RegexSuggestion
from tests.llm_fakes import make_date_normalization, make_suggestion

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


def llm_returning(outcome) -> tuple[OllamaLLM, FakeClient]:
    client = FakeClient(outcome)
    return OllamaLLM(client, MODEL), client


def test_returns_parsed_output_and_sends_expected_request():
    suggestion = make_suggestion()
    llm, client = llm_returning(response(suggestion.model_dump_json()))

    assert llm.complete("system text", "user text", RegexSuggestion) == suggestion

    [call] = client.calls
    assert call["model"] == MODEL
    assert call["format"] == RegexSuggestion.model_json_schema()
    assert call["options"] == GENERATION_OPTIONS
    assert call["options"]["temperature"] == 0
    # A repetition loop must end at the cap rather than run until the request times out.
    assert 0 < call["options"]["num_predict"] <= 2048
    assert call["messages"] == [
        {"role": "system", "content": "system text"},
        {"role": "user", "content": "user text"},
    ]


def test_each_output_type_is_constrained_by_its_own_schema():
    suggestion = make_date_normalization()
    llm, client = llm_returning(response(suggestion.model_dump_json()))

    assert llm.complete("s", "u", NormalizationSuggestion) == suggestion
    assert client.calls[0]["format"] == NormalizationSuggestion.model_json_schema()


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
    llm, _ = llm_returning(outcome)

    with pytest.raises(LLMInvalidResponse):
        llm.complete("s", "u", RegexSuggestion)


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
    llm, _ = llm_returning(error)

    with pytest.raises(expected):
        llm.complete("s", "u", RegexSuggestion)


def test_factory_requires_a_server_url(settings):
    settings.LLM_BASE_URL = ""

    with pytest.raises(LLMNotConfigured):
        get_llm()


def test_factory_uses_configured_server_and_model(settings):
    settings.LLM_BASE_URL = "http://ollama:11434"
    settings.LLM_MODEL = MODEL

    llm = get_llm()

    assert isinstance(llm, OllamaLLM)
    assert llm.model == MODEL
