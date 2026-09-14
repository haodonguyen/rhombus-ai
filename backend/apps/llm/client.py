"""Regex suggestions from a local LLM served by Ollama.

The rest of the app depends on the `RegexGenerator` protocol, not on the Ollama client, so
tests substitute a fake generator and never reach a model server.
"""

import logging
from functools import cache
from typing import Protocol

import httpx
import ollama
import pydantic
from django.conf import settings

from apps.llm.exceptions import (
    LLMInvalidResponse,
    LLMNotConfigured,
    LLMRequestFailed,
    LLMUnavailable,
)
from apps.llm.prompts.regex import SYSTEM_PROMPT, build_user_message
from apps.llm.schemas import RegexSuggestion

logger = logging.getLogger(__name__)

# Deterministic output: the same description should always produce the same pattern.
GENERATION_OPTIONS = {"temperature": 0}
# Server responses worth retrying later: overloaded, restarting or still loading the model.
TRANSIENT_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class RegexGenerator(Protocol):
    def generate(self, description: str) -> RegexSuggestion: ...


class OllamaRegexGenerator:
    def __init__(self, client: ollama.Client, model: str) -> None:
        self.client = client
        self.model = model

    def generate(self, description: str) -> RegexSuggestion:
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_message(description)},
                ],
                # Constrains decoding to JSON that matches the schema.
                format=RegexSuggestion.model_json_schema(),
                options=GENERATION_OPTIONS,
            )
        # The client raises ConnectionError when the server is unreachable; timeouts and
        # other transport failures surface as httpx errors.
        except (ConnectionError, httpx.TransportError) as exc:
            logger.warning("Ollama is unreachable: %s", exc)
            raise LLMUnavailable() from exc
        except ollama.ResponseError as exc:
            if exc.status_code == 404:
                logger.error("Ollama model %r is not available: %s", self.model, exc.error)
                raise LLMNotConfigured(
                    "The language model is not installed on the Ollama server. "
                    "Enter a regex instead."
                ) from exc
            if exc.status_code in TRANSIENT_STATUSES:
                logger.warning("Ollama is temporarily unavailable (%s)", exc.status_code)
                raise LLMUnavailable() from exc
            logger.error("Ollama request failed (%s): %s", exc.status_code, exc.error)
            raise LLMRequestFailed() from exc

        if response.done_reason == "length":
            logger.warning("Ollama output was cut off at the token limit")
            raise LLMInvalidResponse()
        try:
            suggestion = RegexSuggestion.model_validate_json(response.message.content or "")
        except pydantic.ValidationError as exc:
            logger.warning("Ollama output did not match the schema")
            raise LLMInvalidResponse() from exc

        logger.info("Ollama generated a pattern (model %s)", self.model)
        return suggestion


def get_regex_generator() -> RegexGenerator:
    if not settings.LLM_BASE_URL:
        raise LLMNotConfigured()
    client = _ollama_client(settings.LLM_BASE_URL, settings.LLM_TIMEOUT_SECONDS)
    return OllamaRegexGenerator(client, settings.LLM_MODEL)


@cache
def _ollama_client(host: str, timeout: float) -> ollama.Client:
    # One client per worker process, so HTTP connections are reused across jobs.
    return ollama.Client(host=host, timeout=timeout)
