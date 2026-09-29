"""GroqProvider/GeminiProvider with the SDK clients mocked at the module
boundary - no real network calls, no API keys needed."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.services.llm.provider import (
    GeminiProvider,
    GroqProvider,
    LLMRateLimitedError,
    LLMTransientError,
)


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from backend.app.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    yield
    config.get_settings.cache_clear()


def test_groq_provider_parses_successful_response(monkeypatch):
    import groq

    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"summary": "hi"}'))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=4),
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response
    monkeypatch.setattr(groq, "Groq", lambda **_kwargs: fake_client)

    provider = GroqProvider()
    result = provider.generate_json(
        purpose="case_summary", system_prompt="s", user_payload={"a": 1}, max_tokens=100
    )

    assert result.data == {"summary": "hi"}
    assert result.prompt_tokens == 12
    assert result.completion_tokens == 4


def test_groq_provider_maps_429_to_rate_limited_error(monkeypatch):
    import groq

    class FakeAPIStatusError(Exception):
        def __init__(self):
            self.status_code = 429
            self.response = SimpleNamespace(headers={})

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = FakeAPIStatusError()
    monkeypatch.setattr(groq, "Groq", lambda **_kwargs: fake_client)
    monkeypatch.setattr(groq, "APIStatusError", FakeAPIStatusError)

    provider = GroqProvider()
    with pytest.raises(LLMRateLimitedError):
        provider.generate_json(
            purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
        )


def test_groq_provider_maps_5xx_to_transient_error(monkeypatch):
    import groq

    class FakeAPIStatusError(Exception):
        def __init__(self):
            self.status_code = 503
            self.response = None

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = FakeAPIStatusError()
    monkeypatch.setattr(groq, "Groq", lambda **_kwargs: fake_client)
    monkeypatch.setattr(groq, "APIStatusError", FakeAPIStatusError)

    provider = GroqProvider()
    with pytest.raises(LLMTransientError):
        provider.generate_json(
            purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
        )


def test_groq_provider_maps_timeout_to_transient_error(monkeypatch):
    import groq

    class FakeTimeout(Exception):
        pass

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = FakeTimeout()
    monkeypatch.setattr(groq, "Groq", lambda **_kwargs: fake_client)
    monkeypatch.setattr(groq, "APITimeoutError", FakeTimeout)

    provider = GroqProvider()
    with pytest.raises(LLMTransientError):
        provider.generate_json(
            purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
        )


def test_gemini_provider_parses_successful_response(monkeypatch):
    from google import genai

    fake_response = SimpleNamespace(
        text='{"summary": "hi"}',
        usage_metadata=SimpleNamespace(prompt_token_count=8, candidates_token_count=3),
    )
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_response
    monkeypatch.setattr(genai, "Client", lambda **_kwargs: fake_client)

    provider = GeminiProvider()
    result = provider.generate_json(
        purpose="case_summary", system_prompt="s", user_payload={"a": 1}, max_tokens=100
    )

    assert result.data == {"summary": "hi"}
    assert result.prompt_tokens == 8
    assert result.completion_tokens == 3


def test_gemini_provider_maps_429_to_rate_limited_error(monkeypatch):
    from google import genai
    from google.genai import errors

    class FakeClientError(Exception):
        code = 429

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = FakeClientError()
    monkeypatch.setattr(genai, "Client", lambda **_kwargs: fake_client)
    monkeypatch.setattr(errors, "ClientError", FakeClientError)

    provider = GeminiProvider()
    with pytest.raises(LLMRateLimitedError):
        provider.generate_json(
            purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
        )
