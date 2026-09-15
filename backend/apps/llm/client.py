"""Structured completions from a local LLM served by Ollama.

The rest of the app depends on the `StructuredLLM` protocol, not on the Ollama client, so
tests substitute a fake and never reach a model server.
"""

import logging
from functools import cache
from typing import Protocol, TypeVar

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

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=pydantic.BaseModel)

# Deterministic output: the same inputs should always produce the same answer. The token cap
# stops a small model that falls into a repetition loop: every answer fits in a few hundred
# tokens, and without a cap the loop runs until the request times out and is then retried.
GENERATION_OPTIONS = {"temperature": 0, "num_predict": 1024}
# Server responses worth retrying later: overloaded, restarting or still loading the model.
TRANSIENT_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class StructuredLLM(Protocol):
    def complete(self, system: str, user: str, output_type: type[ModelT]) -> ModelT: ...


class OllamaLLM:
    def __init__(self, client: ollama.Client, model: str) -> None:
        self.client = client
        self.model = model

    def complete(self, system: str, user: str, output_type: type[ModelT]) -> ModelT:
        """Ask for a JSON answer constrained to `output_type`'s schema and parse it."""
        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # Constrains decoding to JSON that matches the schema.
                format=output_type.model_json_schema(),
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
            parsed = output_type.model_validate_json(response.message.content or "")
        except pydantic.ValidationError as exc:
            logger.warning("Ollama output did not match the %s schema", output_type.__name__)
            raise LLMInvalidResponse() from exc

        logger.info("Ollama produced a %s (model %s)", output_type.__name__, self.model)
        return parsed


def get_llm() -> StructuredLLM:
    if not settings.LLM_BASE_URL:
        raise LLMNotConfigured()
    client = _ollama_client(settings.LLM_BASE_URL, settings.LLM_TIMEOUT_SECONDS)
    return OllamaLLM(client, settings.LLM_MODEL)


@cache
def _ollama_client(host: str, timeout: float) -> ollama.Client:
    # One client per worker process, so HTTP connections are reused across jobs.
    return ollama.Client(host=host, timeout=timeout)
