"""Question answering turns on when a later vLLM try succeeds."""

from __future__ import annotations

import threading

from api.utils.vllm_attach import keep_trying_vllm


def test_later_try_enables_question_answering():
    waits = []
    attempts = []
    enabled = []

    def pause(seconds):
        waits.append(seconds)
        return False

    def connect(base_url, model_name, temperature):
        attempts.append((base_url, model_name, temperature))
        if len(attempts) == 1:
            raise ConnectionError("failed to resolve 'vllm'")
        return "runner"

    keep_trying_vllm(
        base_url="http://vllm:8000",
        model_name="google/gemma-3-4b-it",
        temperature=0.1,
        stop_event=threading.Event(),
        on_ready=enabled.append,
        connect=connect,
        wait=pause,
    )

    assert waits == [20, 40]
    assert attempts == [
        ("http://vllm:8000", "google/gemma-3-4b-it", 0.1),
        ("http://vllm:8000", "google/gemma-3-4b-it", 0.1),
    ]
    assert enabled == ["runner"]


def test_stopped_wait_does_not_try_again():
    stop_event = threading.Event()
    stop_event.set()
    attempts = []

    def connect(base_url, model_name, temperature):
        attempts.append(1)
        raise ConnectionError("should not be called")

    keep_trying_vllm(
        base_url="http://vllm:8000",
        model_name="google/gemma-3-4b-it",
        temperature=0.1,
        stop_event=stop_event,
        on_ready=lambda runner: None,
        connect=connect,
    )

    assert attempts == []


def test_retry_waits_grow_until_five_minutes():
    waits = []

    def pause(seconds):
        waits.append(seconds)
        return len(waits) == 6

    def connect(base_url, model_name, temperature):
        raise ConnectionError("down")

    keep_trying_vllm(
        base_url="http://vllm:8000",
        model_name="google/gemma-3-4b-it",
        temperature=0.1,
        stop_event=threading.Event(),
        on_ready=lambda runner: None,
        connect=connect,
        wait=pause,
    )

    assert waits == [20, 40, 80, 160, 300, 300]
