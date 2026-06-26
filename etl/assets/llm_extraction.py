import os
import json
from typing import Dict, Optional, Any
from logging import Logger
import time
import httpx

import pandas as pd
from openai import OpenAI
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download
from pathlib import Path

from abc import ABC, abstractmethod
from etl import LLMConfig

class LLMSchemaPropertyExtractor(ABC):
    def __init__(self, logger: Logger, config: LLMConfig):
        self.logger = logger
        self.config = config
        self.vllm_kwargs = self.config.vllm_kwargs
        self.client = None
        self.tokenizer = None
        self.model_name = None
        self.llm_len = 0
        
        self.questions = None
        self.prop_template_type_map = None
        self.templates = None
        
        self.extraction_results = {}
        self.evaluation_results = {}
        
    def load_metadata(self) -> None:
        """Method to load metadata for schema extraction."""
        metadata_dir = self.config.dir_metadata

        if self.templates and self.questions and self.prop_template_type_map:
            self.logger.warning("Metadata already loaded, overwriting.")

        questions_file = os.path.join(metadata_dir, 'llm_questions.csv')
        templates_file = os.path.join(metadata_dir, 'llm_templates.csv')

        if not os.path.exists(questions_file) or not os.path.exists(templates_file):
            self.logger.error(f"FATAL: Metadata files not found in directory: {metadata_dir}")
            return
        
        questions_df = pd.read_csv(questions_file, sep=";")
        self.questions = questions_df.set_index('Property')['Question'].to_dict()
        self.prop_template_type_map = questions_df.set_index('Property')['Template_Type'].to_dict()

        templates_df = pd.read_csv(templates_file, sep=";")
        self.templates = templates_df.set_index('Type')['Template'].to_dict()

    def load_llm(self) -> None:
        """Initializes the OpenAI API client and local tokenizer."""

        if self.client:
            self.logger.warning("LLM client is already loaded, skipping load.")
            return

        hf_token = self.vllm_kwargs.get("api_key")
        
        self.logger.info(f"Waiting for vLLM API to finish loading model.")
        self._wait_for_vllm_ready()

        self.logger.info(f"Connecting to vLLM API at {self.vllm_kwargs.get('api_base_url')}...")
        self.client = OpenAI(
            base_url=self.vllm_kwargs.get("api_base_url", "http://vllm:8000/v1"),
            api_key=hf_token
        )

        models_response = self.client.models.list()
        if not models_response.data:
            raise ValueError("vLLM returned an empty model list.")

        model_data = models_response.data[0]
        self.model_name = model_data.id

        extra_attributes = getattr(model_data, "model_extra", None) or getattr(model_data, "__dict__", {})
        self.llm_len = extra_attributes.get("max_model_len")

        self.logger.info(f"Loaded LLM: {self.model_name} with context length: {self.llm_len}")

        if "google/gemma-4" in self.model_name:
            # workaround for Gemma4 on transformers < 5
            self.logger.info(f"Applying config workaround and loading local tokenizer for {self.model_name}...")

            try:
                config_path = Path(hf_hub_download(self.model_name, "tokenizer_config.json", token=hf_token))
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
            token=hf_token
        )

    def _wait_for_vllm_ready(self):
        """Poll /health until the server is ready or timeout is reached."""
        timeout = self.vllm_kwargs.get("timeout", 600)
        base_url = self.vllm_kwargs.get("api_base_url", "http://vllm:8000/v1")
        interval = self.vllm_kwargs.get("interval", 2.0)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url.rstrip('/')}/models", timeout=5)
                if resp.status_code == 200:
                    return True
            except (httpx.ConnectError, httpx.TimeoutException):
                pass  # Server not up yet
            time.sleep(interval)
        raise TimeoutError(f"vLLM server at {base_url} did not become ready within {timeout}s")

    @abstractmethod
    def extract_properties(self) -> Dict[str, Any]:
        """Executes the full property extraction pipeline."""
        pass

    @abstractmethod
    def parse_llm_output(self) -> Dict[str, Any]:
        """Parses the raw output from the LLM into a structured dictionary."""
        pass