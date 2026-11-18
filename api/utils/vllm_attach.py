"""Keep trying vLLM after the API has already started.

The startup check tries once. When that try cannot reach vLLM, gets an
error response, or does not list the configured model, the API serves
search with question answering off, and this loop tries again in the
background. One later try that lists the model turns question answering on.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

VLLM_RETRY_START_SECONDS = 20
VLLM_RETRY_MAX_SECONDS = 300


def build_vllm_runner(
    base_url: str,
    model_name: str,
    temperature: float,
    stop_event: Optional[threading.Event] = None,
):
    """Build a runner with one check. ``stop_event`` aborts that check."""
    from api.utils.llm_runners import VLLMRunner

    return VLLMRunner(
        base_url=base_url,
        model_name=model_name,
        temperature=temperature,
        max_retries=1,
        retry_delay=0,
        stop_event=stop_event,
    )


def keep_trying_vllm(
    base_url: str,
    model_name: str,
    temperature: float,
    stop_event: threading.Event,
    on_ready: Callable,
    connect: Callable = build_vllm_runner,
    wait: Optional[Callable[[float], bool]] = None,
) -> None:
    """Wait, then try vLLM again until it answers or stop_event is set.

    The API already tried once before calling this. This waits before the
    first try here. ``wait`` returns True when the loop should stop. The
    default wait is ``stop_event.wait``.
    """
    def shutdown_requested() -> bool:
        if not stop_event.is_set():
            return False
        logger.info("Stopped waiting for vLLM.")
        return True

    pause = wait or stop_event.wait
    delay = VLLM_RETRY_START_SECONDS
    while True:
        logger.info("vLLM is not available. Trying again in %s seconds.", delay)
        if pause(delay):
            logger.info("Stopped waiting for vLLM.")
            return
        if shutdown_requested():
            return
        try:
            if connect is build_vllm_runner:
                runner = connect(base_url, model_name, temperature, stop_event)
            else:
                runner = connect(base_url, model_name, temperature)
            if shutdown_requested():
                return
            on_ready(runner)
        except (ConnectionError, RuntimeError) as exc:
            if shutdown_requested():
                return
            delay = min(delay * 2, VLLM_RETRY_MAX_SECONDS)
            logger.warning("vLLM is still unavailable (%s).", exc)
            continue
        except Exception:
            if shutdown_requested():
                return
            delay = min(delay * 2, VLLM_RETRY_MAX_SECONDS)
            logger.exception("Could not enable question answering. Will keep trying.")
            continue
        logger.info("vLLM is available. Question answering is enabled.")
        return
