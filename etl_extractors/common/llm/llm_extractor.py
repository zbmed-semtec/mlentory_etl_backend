import os
import json
import re
import time
import asyncio
from collections import Counter
from typing import Dict, Any, List, Optional
from logging import Logger
from pathlib import Path

import httpx
import pandas as pd
from openai import AsyncOpenAI, APIConnectionError
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download

from abc import ABC, abstractmethod
from .llm_config import LLMConfig

class LLMSchemaPropertyExtractor(ABC):
    """
    Extracts schema properties from documents with a vLLM server.

    Each document gets one request per property. W documents are processed concurrently:
    per document, the first property is streamed and the others are sent as soon as its first
    token arrives, so they reuse the document prefix that vLLM just cached.

    Platform subclasses implement `prepare_documents`, which turns the platform's raw records into
    {document_id: document_text}. Everything else is shared.
    """

    def __init__(self, logger: Logger, config: LLMConfig):
        self.logger = logger
        self.config = config
        self.vllm_kwargs = self.config.vllm_kwargs
        self.hf_token = self.vllm_kwargs.get("api_key")
        self.host_url = self.vllm_kwargs.get("api_base_url", "http://vllm:8000/v1")
        self.max_reconnect_attempts = self.vllm_kwargs.get("max_reconnect_attempts", 3)
        self.max_output_tokens = self.config.sampler_kwargs.get("max_tokens", 2048)

        self.questions = None
        self.prop_template_type_map = None
        self.templates = None
        self.structured_output_schema = None

        self.client = None
        self._vllm_healthy = None
        self._reconnect_lock = None
        self._stats = Counter()

        self._load_metadata()
        if self.config.structured_outputs:
            self._load_structured_output_json()
        self._load_llm()
        self._load_tokenizer()

    def extract(
        self,
        documents: Dict[str, str],
        properties: Optional[List[str]] = None,
        typical_visible_output_tokens: Optional[int] = None,
    ) -> Dict[str, Dict[str, str]]:
        """
        Extracts properties from every document.

        Args:
            documents: {document_id: document_text}
            properties: Properties to extract, defaults to all properties in the questions file.
            typical_visible_output_tokens: Expected answer length, used to estimate concurrency.

        Returns:
            {document_id: {property: value or "NA"}}
        """
        properties = properties or list(self.questions)
        missing = [p for p in properties if p not in self.questions]
        if missing:
            raise KeyError(f"Properties not defined in llm_questions.csv: {missing}")

        results = {doc_id: {p: "NA" for p in properties} for doc_id, text in documents.items() if not text.strip()}
        to_extract = {doc_id: text for doc_id, text in documents.items() if doc_id not in results}
        if not to_extract:
            self.logger.info("No documents with text for extraction.")
            return results

        prompts = self._create_prompts(to_extract, properties)
        concurrency = self.estimate_max_concurrent_documents(
            to_extract, len(properties), typical_visible_output_tokens
        )
        results.update(asyncio.run(self._run_pipeline(prompts, concurrency)))

        self.logger.info(
            f"Completed extraction for {len(to_extract)} documents ({len(documents) - len(to_extract)} empty) and {len(properties)} properties. "
            f"Too long for context: {self._stats['skipped']}, request failed: {self._stats['failed']}, "
            f"unparseable output: {self._stats['unparseable']} (all stored as NA)."
        )
        return {doc_id: results[doc_id] for doc_id in documents}

    @staticmethod
    @abstractmethod
    def prepare_documents(raw_records) -> Dict[str, str]:
        """Turns the platform's raw records into {document_id: document_text}."""
        pass

    def _load_metadata(self) -> None:
        """Loads the questions and templates used to build the prompts."""
        metadata_dir = self.config.dir_metadata
        questions_file = os.path.join(metadata_dir, 'llm_questions.csv')
        templates_file = os.path.join(metadata_dir, 'llm_templates.csv')

        if not os.path.exists(questions_file) or not os.path.exists(templates_file):
            raise FileNotFoundError(f"Metadata files not found in directory: {metadata_dir}")

        questions_df = pd.read_csv(questions_file, sep=";")
        self.questions = questions_df.set_index('Property')['Question'].to_dict()
        self.prop_template_type_map = questions_df.set_index('Property')['Template_Type'].to_dict()

        templates_df = pd.read_csv(templates_file, sep=";")
        self.templates = templates_df.set_index('Type')['Template'].to_dict()

        required = set(self.prop_template_type_map.values()) | {"format_json", "format_plain"}
        missing = sorted(str(t) for t in required if t not in self.templates)
        if missing:
            raise ValueError(f"Template types not found in llm_templates.csv: {missing}")

    def _create_prompts(self, documents: Dict[str, str], properties: List[str]) -> Dict[str, Dict[str, str]]:
        """Builds {document_id: {property: prompt}}."""
        # with structured outputs vLLM enforces the JSON, without them small models answer best in plain text
        output_format = self.templates["format_json" if self.config.structured_outputs else "format_plain"]
        prompts = {}
        for doc_id, document in documents.items():
            prompts[doc_id] = {}
            for prop_name in properties:
                template = self.templates[self.prop_template_type_map[prop_name]]
                prompts[doc_id][prop_name] = (
                    template.replace("PROPERTY_NAME", prop_name)
                    .replace("PROPERTY_DESCRIPTION", self.questions[prop_name])
                    .replace("OUTPUT_FORMAT", output_format)
                    .replace("RETRIEVED_CONTEXT", document)
                )
        return prompts

    def _load_structured_output_json(self) -> None:
        schema_file = os.path.join(self.config.dir_metadata, "structured_output.json")
        with open(schema_file, "r", encoding="utf-8") as f:
            self.structured_output_schema = json.load(f)

    def _load_llm(self) -> None:
        """Waits for vLLM and reads the served model name and context length from /models."""
        self.logger.info("Waiting for vLLM API to finish loading model. Check vllm status with: 'docker compose logs -f vllm'")
        models_response = self._wait_for_vllm_ready()
        if not models_response.get("data"):
            raise ValueError("vLLM returned an empty model list.")

        model_data = models_response["data"][0]
        self.model_name = model_data["id"]
        self.llm_len = model_data["max_model_len"]
        self.kv_cache_tokens = self._read_kv_cache_tokens()
        self.logger.info(f"Loaded LLM: {self.model_name} with context length: {self.llm_len}, KV cache: {self.kv_cache_tokens} tokens")

    def _read_kv_cache_tokens(self) -> int:
        """Reads the KV cache size in tokens from vLLM's /metrics, or falls back to the context length (always fits)."""
        metrics_url = self.host_url.rstrip("/").removesuffix("/v1") + "/metrics"
        try:
            resp = httpx.get(metrics_url, headers={"Authorization": f"Bearer {self.hf_token or 'EMPTY'}"}, timeout=5)
            resp.raise_for_status()
            info = next((line for line in resp.text.splitlines() if line.startswith("vllm:cache_config_info{")), "")
            labels = dict(re.findall(r'(\w+)="([^"]*)"', info))
            if labels.get("kv_cache_size_tokens", "").isdigit():
                return int(labels["kv_cache_size_tokens"])
            if labels.get("num_gpu_blocks", "").isdigit() and labels.get("block_size", "").isdigit():  # older vLLM
                return int(labels["num_gpu_blocks"]) * int(labels["block_size"])
        except httpx.HTTPError as e:
            self.logger.warning(f"Could not read vLLM metrics at {metrics_url}: {e}")
        self.logger.warning(f"vLLM did not report its KV cache size, assuming the context length ({self.llm_len} tokens).")
        return self.llm_len

    def _load_tokenizer(self) -> None:
        """Loads the tokenizer of the served model, used to reject prompts that exceed the context."""

        ### TODO: Remove this workaround once transformers >= 5 is used in vLLM
        # workaround for Gemma4 on transformers < 5
        if "gemma-4" in self.model_name:
            self.logger.info(f"Applying config workaround and loading local tokenizer for {self.model_name}...")

            try:
                config_path = Path(hf_hub_download(self.model_name, "tokenizer_config.json", token=self.hf_token))
                with open(config_path, "r") as f:
                    config = json.load(f)

                if isinstance(config.get("extra_special_tokens"), list):
                    config["extra_special_tokens"] = {}
                    with open(config_path, "w") as f:
                        json.dump(config, f)
                    self.logger.info("Patched tokenizer_config.json successfully")
            except Exception as e:
                self.logger.error(f"Error while patching tokenizer config: {e}")

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            trust_remote_code=True,
            token=self.hf_token
        )
        ###

    def _wait_for_vllm_ready(self) -> dict:
        """Poll /models until the server is ready or timeout is reached. Returns the /models response."""
        timeout = self.vllm_kwargs.get("timeout", 600)
        interval = self.vllm_kwargs.get("interval", 2.0)
        headers = {"Authorization": f"Bearer {self.hf_token or 'EMPTY'}"}
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{self.host_url.rstrip('/')}/models", headers=headers, timeout=5)
                if resp.status_code == 200:
                    return resp.json()
            except httpx.TransportError:
                pass  # Server not up yet
            time.sleep(interval)
        raise TimeoutError(f"vLLM server at {self.host_url} did not become ready within {timeout}s")

    def estimate_max_concurrent_documents(
        self,
        documents: Dict[str, str],
        props_per_document: int,
        typical_visible_output_tokens: Optional[int] = None,
        safety_margin: float = 0.85,
    ) -> int:
        """
        N_max ~= C / (P_avg + k * D_typical)

        C = total KV cache pool in tokens, as reported by vLLM
        P_avg = average document prompt length in tokens
        D_typical = typical decode length per property
        k = properties per document
        """
        d_typical = typical_visible_output_tokens or self.max_output_tokens

        avg_prompt_tokens = sum(
            len(self.tokenizer.encode(doc)) for doc in documents.values()
        ) / len(documents)

        per_document_tokens = avg_prompt_tokens + props_per_document * d_typical
        n_max = int((self.kv_cache_tokens * safety_margin) / per_document_tokens)
        self.logger.info(f"Estimated max concurrent documents: {max(1, n_max)}")
        return max(1, n_max)

    def _build_messages(self, prompt: str) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": prompt},
        ]

    def _build_extra_body(self, priority: int) -> dict:
        extra_body = {k: v for k, v in self.config.sampler_kwargs.items() if k != "max_tokens"}
        if self.config.structured_outputs:
            extra_body["structured_outputs"] = {"json": self.structured_output_schema}
        if self.config.priority_scheduling:
            extra_body["priority"] = priority  # lower value is scheduled first
        return extra_body

    def _split_valid_and_oversized(self, doc_id: str, props: dict) -> tuple[dict, dict]:
        """Reject prompts that would exceed the server's context window before sending them"""
        valid, skipped = {}, {}
        for prop_name, prompt in props.items():
            token_count = len(self.tokenizer.encode(prompt))
            if token_count + self.max_output_tokens > self.llm_len:
                skipped[prop_name] = "NA"
                self._stats["skipped"] += 1
                self.logger.error(
                    f"SKIPPED {doc_id} / {prop_name}: prompt ({token_count} tokens) + max_output_tokens "
                    f"({self.max_output_tokens}) exceeds the context length ({self.llm_len})"
                )
            else:
                valid[prop_name] = prompt
        return valid, skipped

    async def _fire_task(self, prompt: str, priority: int) -> str:
        resp = await self.client.chat.completions.create(
            model=self.model_name,
            messages=self._build_messages(prompt),
            max_tokens=self.max_output_tokens,
            extra_body=self._build_extra_body(priority),
        )
        return resp.choices[0].message.content

    async def _process_document(self, doc_id: str, props: dict) -> dict:
        """Returns {prop_name: raw_text or "NA"}. Raises if vLLM is unreachable, so the worker can reconnect."""
        valid_props, skipped = self._split_valid_and_oversized(doc_id, props)
        if not valid_props:
            return skipped  # nothing here is safe to send

        keys = list(valid_props.keys())
        opener_key, other_keys = keys[0], keys[1:]

        opener_chunks = []
        first_token_seen = asyncio.Event()

        async def run_opener():
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=self._build_messages(valid_props[opener_key]),
                    max_tokens=self.max_output_tokens,
                    stream=True,
                    extra_body=self._build_extra_body(priority=5),  # low: starts a new document
                )
                async for chunk in stream:
                    first_token_seen.set()
                    text = chunk.choices[0].delta.content if chunk.choices else None
                    if text:
                        opener_chunks.append(text)
                return "".join(opener_chunks)
            finally:
                first_token_seen.set()  # don't let a failed opener stall the others

        opener_task = asyncio.create_task(run_opener())

        try:
            await asyncio.wait_for(first_token_seen.wait(), timeout=self.config.opener_timeout_s)
        except asyncio.TimeoutError:
            pass

        all_results = await asyncio.gather(
            opener_task,
            *[self._fire_task(valid_props[k], priority=0) for k in other_keys],  # high: finishes a cached document
            return_exceptions=True,
        )

        results = {}
        for k, r in zip(keys, all_results):
            if isinstance(r, Exception):
                if self._is_connection_error(r):
                    raise r  # vLLM is down: the worker pauses, reconnects and requeues this document
                self._stats["failed"] += 1
                self.logger.error(f"Extraction failed for {doc_id} / {k}: {type(r).__name__}: {r}")
                results[k] = "NA"
            else:
                results[k] = r
        results.update(skipped)
        return results

    def _is_connection_error(self, exc: BaseException) -> bool:
        # Streamed responses raise raw httpx errors (e.g. RemoteProtocolError), not openai ones
        return isinstance(exc, (httpx.TransportError, APIConnectionError))

    async def _handle_vllm_down(self, doc_id: str, props: dict, attempt: int, queue: asyncio.Queue):
        """Pause all workers and wait for vLLM to come back, then requeue this item."""
        self._vllm_healthy.clear()  # tell every worker to pause at their next check

        async with self._reconnect_lock:
            if not self._vllm_healthy.is_set():  # still down
                self.logger.warning(
                    f"Lost connection to vLLM while processing {doc_id}. "
                    "Pausing extraction until it comes back."
                )
                await asyncio.to_thread(self._wait_for_vllm_ready)
                self.logger.info("vLLM is back up. Resuming extraction.")
                self._vllm_healthy.set()

        queue.put_nowait((doc_id, props, attempt + 1))

    async def _worker(self, queue: asyncio.Queue, results: dict, total: int):
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                return
            doc_id, props, attempt = item
            try:
                await self._vllm_healthy.wait()  # waits here while vLLM is down
                try:
                    raw = await self._process_document(doc_id, props)
                    parsed = self._parse_llm_output(doc_id, raw)
                except Exception as e:
                    if self._is_connection_error(e) and attempt < self.max_reconnect_attempts:
                        await self._handle_vllm_down(doc_id, props, attempt, queue)
                        continue  # requeued: it gets stored when it is processed again
                    self._stats["failed"] += len(props)
                    self.logger.error(f"Extraction failed for {doc_id} (attempt {attempt + 1}): {type(e).__name__}: {e}")
                    parsed = {p_name: "NA" for p_name in props}

                results[doc_id] = parsed
                if len(results) % 10 == 0 or len(results) == total:
                    self.logger.info(f"Extracted {len(results)}/{total} documents")
            finally:
                queue.task_done()

    async def _run_pipeline(self, prompts: Dict[str, Dict[str, str]], concurrency: int) -> Dict[str, Dict[str, str]]:
        self.logger.info(f"{len(prompts)} documents to extract, concurrency={concurrency}")
        self._stats.clear()
        self._vllm_healthy = asyncio.Event()
        self._vllm_healthy.set()
        self._reconnect_lock = asyncio.Lock()

        queue: asyncio.Queue = asyncio.Queue()
        for doc_id, props in prompts.items():
            queue.put_nowait((doc_id, props, 0))  # (doc_id, props, reconnect attempts so far)

        results: Dict[str, Dict[str, str]] = {}
        # The client is bound to this event loop, so it lives only for this run
        async with AsyncOpenAI(base_url=self.host_url, api_key=self.hf_token or "EMPTY") as client:
            self.client = client
            async with asyncio.TaskGroup() as tg:
                for _ in range(concurrency):
                    tg.create_task(self._worker(queue, results, len(prompts)))
                await queue.join()  # wait until every document is done, including requeued ones
                for _ in range(concurrency):
                    queue.put_nowait(None)  # then tell each worker to stop
        self.client = None
        return results

    def _parse_llm_output(self, doc_id: str, raw_outputs: Dict[str, str]) -> Dict[str, Any]:
        """Parses the raw text output of every property into its value, or "NA" if it is not valid."""
        result = {}
        for p_name, generated_text in raw_outputs.items():
            if generated_text == "NA":
                result[p_name] = "NA"
                continue

            value = self._parse_value(generated_text)
            if value is None:
                self._stats["unparseable"] += 1
                self.logger.error(f"{self.model_name} gave no usable answer for property: {p_name}, document: {doc_id}. Generated output: {generated_text}. Returning NA.")
                value = "NA"
            result[p_name] = value
        return result

    def _parse_value(self, generated_text: str) -> Optional[str]:
        """Returns the answer in the generated text, or None if there is none."""
        text = generated_text or ""
        if not self.config.structured_outputs:
            return text.strip() or None  # plain-text reply

        try:
            parsed = json.loads(text)  # vLLM enforced the schema, so anything else is a truncated answer
        except json.JSONDecodeError:
            return None
        value = parsed.get("result") if isinstance(parsed, dict) else None
        if value is None:
            return None
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
