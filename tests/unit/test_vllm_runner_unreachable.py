"""vLLM startup gives up immediately when the service cannot be reached."""

from __future__ import annotations

import requests

from api.utils import llm_runners


def test_unreachable_vllm_does_not_retry(monkeypatch):
    sleeps = []

    def fail_get(*args, **kwargs):
        raise requests.ConnectionError("failed to resolve 'vllm'")

    monkeypatch.setattr(llm_runners.requests, "get", fail_get)
    monkeypatch.setattr(llm_runners.time, "sleep", lambda seconds: sleeps.append(seconds))

    try:
        llm_runners.VLLMRunner(
            base_url="http://vllm:8000",
            model_name="google/gemma-3-4b-it",
            max_retries=20,
            retry_delay=20,
        )
    except ConnectionError as exc:
        assert "Could not connect to vLLM service" in str(exc)
    else:
        raise AssertionError("VLLMRunner should fail when vLLM cannot be reached")

    assert sleeps == []
