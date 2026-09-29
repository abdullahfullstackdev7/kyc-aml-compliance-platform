"""LLMProvider interface and the two free-tier providers. See
PROJECT_PLAN.md Phase 6.2. Both providers are told to return strict JSON
matching the caller's schema; neither ever screens, approves or rejects a
case - they only draft text for a human to read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.app.core.config import get_settings


class LLMTransientError(Exception):
    """Retryable: timeout or 5xx. The router retries once, then fails over."""


class LLMRateLimitedError(Exception):
    """429. The router fails over immediately without retrying."""

    def __init__(self, retry_after_seconds: float | None = None):
        super().__init__("rate limited")
        self.retry_after_seconds = retry_after_seconds


@dataclass
class LLMResult:
    data: dict
    prompt_tokens: int
    completion_tokens: int
    model: str


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_json(
        self, *, purpose: str, system_prompt: str, user_payload: dict, max_tokens: int
    ) -> LLMResult: ...


class GroqProvider:
    name = "groq"

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.groq_model
        self._api_key = settings.groq_api_key
        self._timeout = settings.llm_timeout_seconds

    def generate_json(
        self, *, purpose: str, system_prompt: str, user_payload: dict, max_tokens: int
    ) -> LLMResult:
        from groq import APIStatusError, APITimeoutError, Groq

        client = Groq(api_key=self._api_key, timeout=self._timeout)
        import json as _json

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": _json.dumps(user_payload, separators=(",", ":"))},
                ],
                temperature=0.2,
                max_completion_tokens=max_tokens,
                response_format={"type": "json_object"},
                reasoning_effort="low",
            )
        except APITimeoutError as exc:
            raise LLMTransientError(str(exc)) from exc
        except APIStatusError as exc:
            if exc.status_code == 429:
                retry_after = exc.response.headers.get("retry-after") if exc.response else None
                raise LLMRateLimitedError(float(retry_after) if retry_after else None) from exc
            if exc.status_code >= 500:
                raise LLMTransientError(str(exc)) from exc
            raise

        choice = response.choices[0]
        usage = response.usage
        return LLMResult(
            data=_json.loads(choice.message.content or "{}"),
            prompt_tokens=usage.prompt_tokens if usage and usage.prompt_tokens else 0,
            completion_tokens=usage.completion_tokens if usage and usage.completion_tokens else 0,
            model=self.model,
        )


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.gemini_model
        self._api_key = settings.gemini_api_key
        self._timeout = settings.llm_timeout_seconds

    def generate_json(
        self, *, purpose: str, system_prompt: str, user_payload: dict, max_tokens: int
    ) -> LLMResult:
        import json as _json

        from google import genai
        from google.genai import types
        from google.genai.errors import APIError, ClientError

        from backend.app.services.llm.prompts import RESPONSE_SCHEMA

        client = genai.Client(
            api_key=self._api_key,
            http_options=types.HttpOptions(timeout=self._timeout * 1000),
        )
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=_json.dumps(user_payload, separators=(",", ":")),
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                    max_output_tokens=max_tokens,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
        except ClientError as exc:
            if getattr(exc, "code", None) == 429:
                raise LLMRateLimitedError() from exc
            raise
        except APIError as exc:
            if getattr(exc, "code", 0) >= 500:
                raise LLMTransientError(str(exc)) from exc
            raise
        except TimeoutError as exc:
            raise LLMTransientError(str(exc)) from exc

        usage = response.usage_metadata
        return LLMResult(
            data=_json.loads(response.text or "{}"),
            prompt_tokens=(usage.prompt_token_count or 0) if usage else 0,
            completion_tokens=(usage.candidates_token_count or 0) if usage else 0,
            model=self.model,
        )


def get_provider(name: str) -> LLMProvider:
    if name == "groq":
        return GroqProvider()
    if name == "gemini":
        return GeminiProvider()
    raise ValueError(f"unknown LLM provider: {name}")
