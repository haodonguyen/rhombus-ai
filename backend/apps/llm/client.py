"""Claude-backed generation of regex suggestions.

The rest of the app depends on the `RegexGenerator` protocol, not on the Anthropic SDK, so
tests substitute a fake generator and never reach the network.
"""

import logging
from functools import cache
from typing import Protocol

import anthropic
import pydantic
from django.conf import settings

from apps.llm.exceptions import (
    LLMInvalidResponse,
    LLMNotConfigured,
    LLMRefused,
    LLMRequestFailed,
    LLMUnavailable,
)
from apps.llm.prompts.regex import SYSTEM_PROMPT, build_user_message
from apps.llm.schemas import RegexSuggestion

logger = logging.getLogger(__name__)

# Server-side refusal fallback: if the model declines, the API re-runs the request on
# Anthropic's recommended fallback model within the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Room for adaptive thinking; the JSON answer itself is small.
MAX_TOKENS = 16000


class RegexGenerator(Protocol):
    def generate(self, description: str) -> RegexSuggestion: ...


class ClaudeRegexGenerator:
    def __init__(self, client: anthropic.Anthropic, model: str) -> None:
        self.client = client
        self.model = model

    def generate(self, description: str) -> RegexSuggestion:
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_message(description)}],
                output_format=RegexSuggestion,
                fallbacks="default",
                betas=[FALLBACK_BETA],
            )
        # Transient failures; the SDK has already retried these a few times with backoff.
        # 503/504/529 have their own classes and do not subclass InternalServerError.
        except (
            anthropic.RateLimitError,
            anthropic.ConflictError,
            anthropic.InternalServerError,
            anthropic.ServiceUnavailableError,
            anthropic.DeadlineExceededError,
            anthropic.OverloadedError,
            anthropic.APIConnectionError,
        ) as exc:
            logger.warning("Claude is temporarily unavailable: %s", exc)
            raise LLMUnavailable() from exc
        except (
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
            anthropic.NotFoundError,
        ) as exc:
            logger.error("Claude rejected the credentials or model %r: %s", self.model, exc)
            raise LLMNotConfigured() from exc
        except anthropic.APIStatusError as exc:
            logger.error("Claude request failed with status %s: %s", exc.status_code, exc)
            raise LLMRequestFailed() from exc
        except (pydantic.ValidationError, ValueError) as exc:
            logger.warning("Claude output did not match the schema", exc_info=True)
            raise LLMInvalidResponse() from exc

        if response.stop_reason == "refusal":
            logger.info("Claude declined to generate a pattern (request %s)", response._request_id)
            raise LLMRefused()
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            logger.warning(
                "Claude returned no usable output (stop_reason=%s, request %s)",
                response.stop_reason,
                response._request_id,
            )
            raise LLMInvalidResponse()

        logger.info(
            "Claude generated a pattern (model %s, request %s)",
            response.model,
            response._request_id,
        )
        return response.parsed_output


def get_regex_generator() -> RegexGenerator:
    if not settings.ANTHROPIC_API_KEY:
        raise LLMNotConfigured()
    client = _anthropic_client(
        settings.ANTHROPIC_API_KEY, settings.LLM_TIMEOUT_SECONDS, settings.LLM_MAX_RETRIES
    )
    return ClaudeRegexGenerator(client, settings.LLM_MODEL)


@cache
def _anthropic_client(api_key: str, timeout: float, max_retries: int) -> anthropic.Anthropic:
    # One client per worker process, so HTTP connections are reused across jobs.
    return anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=max_retries)
