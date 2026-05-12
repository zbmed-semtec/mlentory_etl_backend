import os
import json
import time
import subprocess
from typing import Dict, Optional, Tuple
from logging import Logger
from itertools import islice

import pandas as pd
from openai import OpenAI
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download
from pathlib import Path

class LLMSchemaPropertyExtractor:
    def __init__(self, logger: Logger):
        self.logger = logger
        self.client = None
        self.tokenizer = None
        self.model_name = None
        self.llm_len = 0
        
        self.questions = None
        self.prop_template_type_map = None
        self.templates = None
        
        self.extraction_results = {}
        self.evaluation_results = {}
        
    def load_metadata(self, metadata_dir: str) -> None:
        """Method to load metadata for schema extraction."""
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

    def load_llm(self, llm_kwargs: Optional[dict] = None) -> None:
        """Initializes the OpenAI API client and local tokenizer."""
        
        if self.client:
            self.logger.warning("LLM client is already loaded, skipping load.")
            return
        
        if not llm_kwargs:
            self.logger.error("llm_kwargs must be provided to configure API and Tokenizer.")
            return

        self.model_name = llm_kwargs.get("model", "google/gemma-4-E4B-it")
        self.llm_len = llm_kwargs.get("max_model_len", 65536)
        hf_token = llm_kwargs.get("api_key")
        
        self.logger.info(f"Connecting to vLLM API at {llm_kwargs.get('api_base_url')}...")
        self.client = OpenAI(
            base_url=llm_kwargs.get("api_base_url", "http://vllm:8000/v1"),
            api_key=hf_token
        )

        self.logger.info(f"Applying config workaround and loading local tokenizer for {self.model_name}...")

        # workaround for Gemma4 on transformers < 5
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
            trust_remote_code=llm_kwargs.get("trust_remote_code", True),
            token=hf_token
        )
        
        chat_template_path = llm_kwargs.get("chat_template")
        if chat_template_path and os.path.exists(chat_template_path):
            with open(chat_template_path, "r") as f:
                self.tokenizer.chat_template = f.read()
            self.logger.info("Successfully loaded custom chat template.")

    def extract_properties(self,
                           model_cards: Dict[str, str],
                           system_prompt: str = "You are a helpful assistant designed to extract specific information based on provided criteria. Think carefully what the extraction task is, and then strictly answer as instructed.",
                           chat_template_kwargs: Optional[dict] = None,
                           sampler_kwargs: Optional[dict] = None,
                           batch_size: int = 20,
                           max_retry_per_batch: int = 3,
                           connection_retry_delay: int = 30,
                           return_result: bool = True,
                           ground_truth_dir: Optional[str] = None,
                           ) -> Optional[Tuple[Dict, Dict]]:
        
        if not self.client or not self.tokenizer:
            self.logger.error("LLM client not loaded, run load_llm first.")
            return
        
        if not self.questions or not self.templates:
            self.logger.error("Metadata not loaded, run load_metadata first.")
            return
        
        chat_template_kwargs = chat_template_kwargs or {"add_generation_prompt": True, "tokenize": False}
        sampler_kwargs = sampler_kwargs or {"max_tokens": 8096, "temperature": 0.1}

        total_models = len(model_cards)
        self.logger.info(f"Starting extraction. Processing {total_models} models in batches of {batch_size}...")

        it = iter(model_cards.items())
        for i in range(0, total_models, batch_size):
            batch = dict(islice(it, batch_size))
            self.logger.info(f"==== Processing batch {i//batch_size + 1} of {total_models//batch_size + 1} ====")
            
            first_prompts, remaining_prompts = [], []
            metadata_first, metadata_rest = [],[]

            for model_id, model_card in batch.items():
                if model_id not in self.evaluation_results:
                    self.evaluation_results[model_id] = {}
                    self.extraction_results[model_id] = {}

                is_first_valid_prompt = True

                for prop_name, prop_question in self.questions.items():
                    template_type = self.prop_template_type_map.get(prop_name)
                    template = self.templates.get(template_type)

                    instruction = template.replace("PROPERTY_NAME", prop_name).replace("PROPERTY_DESCRIPTION", prop_question).replace("RETRIEVED_CONTEXT", model_card)
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": instruction}
                    ]
                    
                    prompt_str = self.tokenizer.apply_chat_template(messages, **chat_template_kwargs)
                    token_count = len(self.tokenizer.encode(prompt_str))
                    
                    if token_count + sampler_kwargs.get("max_tokens", 8096) > self.llm_len:
                        self.logger.error(f"Prompt for {model_id} - {prop_name} exceeds LLM context length. Skipping.")
                        continue

                    self.evaluation_results[model_id][prop_name] = {
                        "specific_instruct": prop_question,
                        "input_prompt": instruction,
                        "llm_response": None, 
                        "token_count": token_count,
                        "ground_truth": self.get_ground_truth(model_id, prop_name, ground_truth_dir) if ground_truth_dir else "Ground truth directory not provided"
                    }
                
                    meta = (model_id, prop_name)

                    if is_first_valid_prompt:
                        first_prompts.append(prompt_str)
                        metadata_first.append(meta)
                        is_first_valid_prompt = False
                    else:
                        remaining_prompts.append(prompt_str)
                        metadata_rest.append(meta)

            # map sampler_kwargs to OpenAI parameters
            extra_body = {}
            if "repetition_penalty" in sampler_kwargs:
                extra_body["repetition_penalty"] = sampler_kwargs["repetition_penalty"]
            if "skip_special_tokens" in sampler_kwargs:
                extra_body["skip_special_tokens"] = sampler_kwargs["skip_special_tokens"]
            if "thinking_token_budget" in sampler_kwargs:
                extra_body["thinking_token_budget"] = sampler_kwargs["thinking_token_budget"]

            attempts = 0
            while attempts < max_retry_per_batch:
                try:
                    outputs_1, outputs_rest = [],[]
                    
                    if first_prompts:
                        resp_1 = self.client.completions.create(
                            model=self.model_name,
                            prompt=first_prompts,
                            max_tokens=sampler_kwargs.get("max_tokens"),
                            temperature=sampler_kwargs.get("temperature"),
                            top_p=sampler_kwargs.get("top_p"),
                            extra_body=extra_body
                        )
                        outputs_1 = [choice.text for choice in sorted(resp_1.choices, key=lambda c: c.index)]

                    if remaining_prompts:
                        resp_rest = self.client.completions.create(
                            model=self.model_name,
                            prompt=remaining_prompts,
                            max_tokens=sampler_kwargs.get("max_tokens"),
                            temperature=sampler_kwargs.get("temperature"),
                            top_p=sampler_kwargs.get("top_p"),
                            extra_body=extra_body
                        )
                        outputs_rest = [choice.text for choice in sorted(resp_rest.choices, key=lambda c: c.index)]
                    break

                except Exception as e:
                    error_msg = str(e)
                    attempts += 1
                    
                    self.logger.error(f"API Error during generation: {error_msg}. Attempt {attempts}/{max_retry_per_batch}.")
                    
                    if "Connection Error" in error_msg:
                        self.logger.info(f"Connection issue detected. Retrying in {connection_retry_delay} seconds...")
                        time.sleep(connection_retry_delay)

                    if attempts >= max_retry_per_batch:
                        self.logger.error("Max retries reached. Aborting.")                        
                        if return_result:
                            return self.extraction_results, self.evaluation_results
                        return
                    
                    self._restart_vllm_container()
                    continue

            for raw_text, (m_id, p_name) in zip(outputs_1 + outputs_rest, metadata_first + metadata_rest):
                generated_text = raw_text.strip()
                self.extraction_results[m_id][p_name] = generated_text
                self.evaluation_results[m_id][p_name]["llm_response"] = generated_text

        self.logger.info("Completed extraction for all model cards and properties.")
        if return_result:
            return self.extraction_results, self.evaluation_results

    def _restart_vllm_container(self) -> None:
        """Helper to restart the vllm container via docker sock and wait for it to be ready."""
        self.logger.info("Attempting to restart vllm Docker container...")
        try:
            subprocess.run(["docker", "restart", "vllm"], check=True)
            self.logger.info("Restart command sent successfully. Waiting 30s for vLLM API to boot...")
            time.sleep(30)
        except Exception as e:
            self.logger.error(f"Failed to restart container. Error: {e}")

    def get_ground_truth(self, modelname: str, prop_name: str, ground_truth_dir: str) -> Optional[str]:
        gt_file = os.path.join(ground_truth_dir, f"gt_{modelname.split('/')[1]}.json")
        if os.path.isfile(gt_file):
            with open(gt_file, 'r') as f:
                ground_truth = json.load(f)
            return ground_truth.get(prop_name, None)
        else:
            self.logger.warning(f"Ground truth file not found: {modelname}")
            return None