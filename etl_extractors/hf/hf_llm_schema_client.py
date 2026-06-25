"""
HTTP client for vLLM OpenAI-compatible chat completions (HF schema extraction).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class VLLMSchemaClientError(RuntimeError):
    """Raised when vLLM chat completion fails after retries."""


class VLLMSchemaClient:
    """Thin synchronous client for vLLM ``/v1/chat/completions``."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 512,
        timeout_seconds: float = 120.0,
        max_retries: int = 3,
        retry_delay_seconds: float = 2.0,
        api_key: str = "dummy-key",
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.api_key = api_key
        self._injected_client = client
        self._thread_local = threading.local()
        self._clients_lock = threading.Lock()
        self._clients: list[httpx.Client] = []

    @classmethod
    def from_env(
        cls,
        *,
        max_tokens: Optional[int] = None,
        temperature: float = 0.1,
    ) -> "VLLMSchemaClient":
        base_url = os.getenv("VLLM_BASE_URL", "http://vllm:8000")
        model_name = os.getenv("VLLM_MODEL") or os.getenv("LLM_MODEL", "google/gemma-3-4b-it")
        return cls(
            base_url=base_url,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens or int(os.getenv("HF_LLM_SCHEMA_MAX_TOKENS", "512")),
        )

    def _get_client(self) -> httpx.Client:
        if self._injected_client is not None:
            return self._injected_client
        client = getattr(self._thread_local, "client", None)
        if client is None:
            client = httpx.Client(timeout=self.timeout_seconds)
            self._thread_local.client = client
            with self._clients_lock:
                self._clients.append(client)
        return client

    def close(self) -> None:
        if self._injected_client is not None:
            return
        with self._clients_lock:
            for client in self._clients:
                client.close()
            self._clients.clear()

    def __enter__(self) -> "VLLMSchemaClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def chat_completion(self, messages: List[Dict[str, str]]) -> str:
        """
        Run a chat completion and return the assistant message content.

        Raises:
            VLLMSchemaClientError: On HTTP or response-format failure.
        """
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        last_error: Optional[Exception] = None
        client = self._get_client()

        for attempt in range(1, self.max_retries + 1):
            try:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return self._extract_message_content(data)
            except (httpx.HTTPError, VLLMSchemaClientError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    logger.warning(
                        "vLLM chat completion failed (attempt %s/%s): %s",
                        attempt,
                        self.max_retries,
                        exc,
                    )
                    time.sleep(self.retry_delay_seconds)
                else:
                    break

        raise VLLMSchemaClientError(
            f"vLLM chat completion failed after {self.max_retries} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def _extract_message_content(data: Dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise VLLMSchemaClientError(f"Unexpected vLLM response (no choices): {data}")

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if content is not None:
                return str(content)

        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        if text is not None:
            return str(text)

        raise VLLMSchemaClientError(f"Unexpected vLLM response format: {data}")
