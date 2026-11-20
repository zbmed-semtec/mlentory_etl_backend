"""vLLM startup checks once, and only succeeds when the model is listed."""

from __future__ import annotations

import json
import threading

import requests

from api.utils import llm_runners


def _response(status_code, payload=None):
    response = requests.Response()
    response.status_code = status_code
    response.url = "http://vllm:8000/v1/models"
    if payload is not None:
        response._content = json.dumps(payload).encode()
    return response


def test_unreachable_vllm_does_not_retry(monkeypatch):
    sleeps = []
    calls = []

    def fail_get(*args, **kwargs):
        calls.append(args[0])
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

    assert calls == ["http://vllm:8000/v1/models"]
    assert sleeps == []


def test_http_error_tries_once(monkeypatch):
    sleeps = []
    calls = []

    def error_get(*args, **kwargs):
        calls.append(args[0])
        return _response(503)

    monkeypatch.setattr(llm_runners.requests, "get", error_get)
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
        raise AssertionError("VLLMRunner should fail when vLLM returns an error")

    assert calls == ["http://vllm:8000/v1/models"]
    assert sleeps == []


def test_listed_model_is_required(monkeypatch):
    monkeypatch.setattr(
        llm_runners.requests,
        "get",
        lambda *args, **kwargs: _response(200, {"data": [{"id": "other-model"}]}),
    )

    try:
        llm_runners.VLLMRunner(
            base_url="http://vllm:8000",
            model_name="google/gemma-3-4b-it",
            max_retries=20,
            retry_delay=20,
        )
    except RuntimeError as exc:
        assert "is not listed" in str(exc)
        assert "other-model" in str(exc)
    else:
        raise AssertionError("VLLMRunner should keep waiting when the model is missing")


def test_listed_model_is_accepted(monkeypatch):
    monkeypatch.setattr(
        llm_runners.requests,
        "get",
        lambda *args, **kwargs: _response(
            200, {"data": [{"id": "google/gemma-3-4b-it"}]}
        ),
    )
    monkeypatch.setattr(
        llm_runners.VLLMRunner,
        "_initialize_langchain_llm",
        lambda self: None,
    )

    runner = llm_runners.VLLMRunner(
        base_url="http://vllm:8000",
        model_name="google/gemma-3-4b-it",
    )

    assert runner.model_name == "google/gemma-3-4b-it"


def test_shutdown_stops_the_check(monkeypatch):
    stop_event = threading.Event()
    started = threading.Event()

    class FakeSession:
        def __init__(self):
            self.closed = threading.Event()

        def get(self, url, timeout=10):
            started.set()
            if not self.closed.wait(3):
                raise AssertionError("check kept running after shutdown")
            raise requests.ConnectionError("aborted")

        def close(self):
            self.closed.set()

    monkeypatch.setattr(llm_runners.requests, "Session", FakeSession)
    errors = []

    def run():
        try:
            llm_runners.VLLMRunner(
                base_url="http://vllm:8000",
                model_name="google/gemma-3-4b-it",
                stop_event=stop_event,
            )
        except ConnectionError as exc:
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(2)
    stop_event.set()
    thread.join(2)

    assert not thread.is_alive()
    assert len(errors) == 1
    assert "Stopped waiting for vLLM." in str(errors[0])
