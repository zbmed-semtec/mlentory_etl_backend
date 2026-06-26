import os
import json
import time
import subprocess
from typing import Dict, Optional, Tuple, List, Any
from logging import Logger
from itertools import islice
import re

import pandas as pd
from openai import OpenAI
from transformers import AutoTokenizer
from huggingface_hub import hf_hub_download
from pathlib import Path

from etl import LLMSchemaPropertyExtractor

class HFLLMSchemaPropertyExtractor(LLMSchemaPropertyExtractor):

    def extract_properties(self,
                           model_cards: Dict[str, str],
                           system_prompt: str = "You are a helpful assistant designed to extract specific information based on provided criteria. Think carefully what the extraction task is, and then strictly answer as instructed.",
                           max_retry_per_batch: int = 3,
                           return_result: bool = True,
                           ground_truth_dir: Optional[str] = None,
                           ) -> Optional[Tuple[Dict, Dict]]:
        
        if not self.client or not self.tokenizer:
            self.logger.error("LLM client not loaded, run load_llm first.")
            return
        
        if not self.questions or not self.templates:
            self.logger.error("Metadata not loaded, run load_metadata first.")
            return

        batch_size = self.config.batch_size
        sampler_kwargs=self.config.sampler_kwargs
        chat_template_kwargs=self.config.chat_template_kwargs
        connection_retry_delay=self.config.connection_retry_delay

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

            schema = self._load_structured_output_json()
            extra_body["structured_outputs"] = {"json": schema}

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
                    
                    self.logger.info(f"Connection issue detected. Retrying in {connection_retry_delay} seconds...")
                    time.sleep(connection_retry_delay)

                    if attempts >= max_retry_per_batch:
                        self.logger.error("Max retries reached. Aborting.")                        
                        if return_result:
                            return self.extraction_results, self.evaluation_results
                        return
                    
                    continue

            for raw_text, (m_id, p_name) in zip(outputs_1 + outputs_rest, metadata_first + metadata_rest):
                generated_text = raw_text.strip()
                self.extraction_results[m_id][p_name] = generated_text
                self.evaluation_results[m_id][p_name]["llm_response"] = generated_text

        self.logger.info(f"Completed extraction for {len(self.extraction_results)} model cards and {len(self.questions)} properties.")
        if return_result:
            return self.extraction_results, self.evaluation_results
        
    def _load_structured_output_json(self) -> Dict[str, Any]:
        """Loads the structured output json into a dict"""
        
        metadata_dir = self.config.dir_metadata
        json_dir = os.path.join(metadata_dir, 'structured_output.json')
        with open(json_dir, 'r', encoding='utf-8') as f:
            schema_dict = json.load(f)

        return schema_dict

    def _parse_gemma_output(self) -> Dict[str, Any]:
        """Parses the raw text output from Gemma4 into a structured dictionary."""
        result = {}

        for m_id, p_dict in self.extraction_results.items():
            result[m_id] = {}

            for p_name, generated_text in p_dict.items():
                if "<channel|>" and "<|channel>" not in generated_text: # llm did not think
                    json_out = generated_text
                elif not "<channel|>" in generated_text:                # llm did not close thinking tokens properly
                    json_out = re.findall(r'\{.*?\}', generated_text)
                else:                                                   # normal case
                    ss = generated_text.split('<channel|>')
                    json_out = ss[1]

                try:
                    parsed_dict = json.loads(json_out)
                        
                except (json.JSONDecodeError, TypeError):
                    self.logger.error(f"Gemma4 failed to output correct json for property: {p_name}, model: {m_id}. Generated output: {generated_text}")
                    parsed_dict = {}        # we drop the result

                if not parsed_dict.get("result", ""):
                    self.logger.error(f"Gemma4 failed to output correct json for property: {p_name}, model: {m_id}. Generated output: {generated_text}")
                    parsed_dict = {}
                    
                result[m_id][p_name] = parsed_dict.get("result", "")

        return result
    
    def parse_llm_output(self) -> Dict[str, Any]:
        """Parses the raw text output from the LLM into a structured dictionary."""
        return self._parse_gemma_output()