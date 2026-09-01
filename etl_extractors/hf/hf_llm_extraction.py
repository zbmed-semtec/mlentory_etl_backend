import os
import json
import time
from typing import Dict, Optional, Tuple, List, Any
from itertools import islice
import re
from collections import defaultdict
import copy

from packaging import version

from etl import LLMSchemaPropertyExtractor
from etl import ChunkRankingEngine

class HFLLMSchemaPropertyExtractor(LLMSchemaPropertyExtractor):

    def estimate_max_concurrent_cards(
        self,
        model_cards: Dict[str, str],
        typical_visible_output_tokens: Optional[int] = None,
        typical_thinking_tokens: Optional[int] = None,
        safety_margin: float = 0.85,
    ) -> int:
        """
        N_max ~= C / (P_avg + k * D_typical)
 
        C = total KV cache pool in tokens
        P_avg = average model-card prompt length in tokens
        D_typical = typical decode length per property, i.e. visible_output + thinking tokens.
        k = properties per card
        """
        if not model_cards:
            return 1

        gpu_kv_cache_tokens = self.config.gpu_kv_cache_size or 8096
        sampler_kwargs = self.config.sampler_kwargs or {}
        props_per_card = len(self.questions)
 
        visible_tokens = typical_visible_output_tokens
        if visible_tokens is None:
            visible_tokens = sampler_kwargs.get("max_tokens", 8096)
 
        thinking_tokens = typical_thinking_tokens
        if thinking_tokens is None:
            thinking_tokens = sampler_kwargs.get("thinking_token_budget", 768)
 
        d_typical = visible_tokens + thinking_tokens
 
        avg_prompt_tokens = sum(
            len(self.tokenizer.encode(card)) for card in model_cards.values()
        ) / len(model_cards)
 
        per_card_tokens = avg_prompt_tokens + props_per_card * d_typical
        n_max = int((gpu_kv_cache_tokens * safety_margin) / per_card_tokens)
        self.logger.info(f"Estimated max concurrent cards: {max(1, n_max)}")
        return max(1, n_max)

    def extract_properties(self,
                           model_cards: Dict[str, str],
                           system_prompt: str = "You are a helpful assistant designed to extract specific information based on provided criteria. Think carefully what the extraction task is, and then strictly answer as instructed.",
                           max_retry_per_batch: int = 3,
                           batch_size: int = 10,
                           return_result: bool = True,
                           ground_truth_dir: Optional[str] = None,
                           ) -> Optional[Tuple[Dict, Dict]]:
        
        if not self.client or not self.tokenizer:
            self.logger.error("LLM client not loaded, run load_llm first.")
            return
        
        if not self.questions or not self.templates:
            self.logger.error("Metadata not loaded, run load_metadata first.")
            return

        sampler_kwargs=self.config.sampler_kwargs
        chat_template_kwargs=self.config.chat_template_kwargs
        connection_retry_delay=self.config.connection_retry_delay
        vllm_version = self.config.vllm_image.split(":")[1]

        if not self.config.enable_prefix_caching:
            self.logger.warning("Model initialized without prefix caching. This will cause much slower inferencing.")

        # map sampler_kwargs to OpenAI parameters
        extra_body = {}
        if "repetition_penalty" in sampler_kwargs:
            extra_body["repetition_penalty"] = sampler_kwargs["repetition_penalty"]
        if "skip_special_tokens" in sampler_kwargs:
            extra_body["skip_special_tokens"] = sampler_kwargs["skip_special_tokens"]
        if "thinking_token_budget" in sampler_kwargs:
            extra_body["thinking_token_budget"] = sampler_kwargs["thinking_token_budget"]

        # structured outputs depending on vLLM version
        schema = self._load_structured_output_json("structured_output.json")
        if vllm_version == "latest" or version.parse(vllm_version) >= version.parse("v0.12.0"):
            extra_body["structured_outputs"] = {"json": schema}
        else:
            self.logger.warning(f"vLLM version {vllm_version} does not support structured_outputs. Using guided_json instead.")
            extra_body["guided_json"] = {"guided_json": schema}

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

    def _build_rag_chunk_selection_prompt(self, candidates, llm_question):
        lines = []
        for chunk_id, data in candidates.items():
            chunk = data["chunk"][0]
            htext = chunk.get("htext", "") or ""
            phtext = chunk.get("phtext", "") or ""
            snippet = (chunk.get("text", "") or "")[:300].replace("\n", " ")
            lines.append(
                f"- id: {chunk_id}\n"
                f"  heading: {htext}\n"
                f"  parent_heading: {phtext}\n"
                f"  preview: {snippet}"
            )
        candidates_block = "\n".join(lines)
        user_msg = (
            f"Candidate sections:\n{candidates_block}\n\n" + llm_question
        )
        return user_msg
    
    def _score_boosting_usageinstructions(self, target_id, children_by_parent, score):
        """Boosts score if the chunk contains a usage-style code block.

        Used for property == 'fair4ml:usageInstructions'.
        """
        code_children = [
            c for c in children_by_parent.get(target_id, [])
            if c.get("type") == "code"
        ]

        return score + (len(code_children) * 0.15)

    def extract_rag_properties(self, models_chunks_dict, max_tokens=2048, top_n=5,
                                max_retry: int = 3) -> Optional[Dict]:
        """Extracts properties using RAG (Retrieval-Augmented Generation) approach."""

        if not self.rag_questions:
            self.logger.error("RAG descriptions / questions are not defined. Make sure 'rag_questions.csv' is present and loaded.")
            return

        if not self.client:
            self.logger.error("LLM client not loaded, run load_llm first.")
            return

        if not self.ranker:
            self.ranker = ChunkRankingEngine(logger=self.logger, hf_token=os.getenv("HUGGINGFACE_API_TOKEN"))

        out = {}
        prompts = []
        metadata = []
        structured_json_base = self._load_structured_output_json("rag_schema.json")

        sampler_kwargs = self.config.sampler_kwargs
        connection_retry_delay = self.config.connection_retry_delay

        extra_body = {}
        if "repetition_penalty" in sampler_kwargs:
            extra_body["repetition_penalty"] = sampler_kwargs["repetition_penalty"] +0.15
        if "skip_special_tokens" in sampler_kwargs:
            extra_body["skip_special_tokens"] = sampler_kwargs["skip_special_tokens"]
        if "thinking_token_budget" in sampler_kwargs:
            extra_body["thinking_token_budget"] = sampler_kwargs["thinking_token_budget"]

        vllm_version = self.config.vllm_image.split(":")[1]
        use_structured_outputs = vllm_version == "latest" or version.parse(vllm_version) >= version.parse("v0.12.0")
        if not use_structured_outputs:
            self.logger.warning(f"vLLM version {vllm_version} does not support structured_outputs. Using guided_json instead.")

        # Pre-compute property embeddings once
        property_embeddings = {}
        for property, val_dict in self.rag_questions.items():
            pos_emb = self.ranker.compute_property_embedding(val_dict["RAGPositive"])
            neg_emb = None
            if val_dict.get("RAGNegative"):
                neg_emb = self.ranker.compute_property_embedding(val_dict["RAGNegative"])
            property_embeddings[property] = (pos_emb, neg_emb)

        # Map property -> optional score-boosting function
        property_boosting_functions = {
            "fair4ml:usageInstructions": self._score_boosting_usageinstructions,
        }

        # Iterate over models
        for model_id, chunks in models_chunks_dict.items():
            out[model_id] = {}

            # Compute document/heading embeddings once per model
            children_by_parent = defaultdict(list)
            for c in chunks:
                children_by_parent[c.get("parent")].append(c)

            sections = [c for c in chunks if c.get("type") == "section"]
            heading_texts = [
                f"{s.get('htext', '')} {s.get('phtext', '') or ''}".strip().lower()
                for s in sections
            ]
            heading_embs = self.ranker.compute_document_embedding(heading_texts)

            # Iterate over properties
            for property, val_dict in self.rag_questions.items():
                self.logger.info(f"Processing property: {property} for model: {model_id}")

                # Fetch pre-computed intent embeddings
                positive_intent_emb, negative_intent_emb = property_embeddings[property]

                boosting_fn = property_boosting_functions.get(property)

                context = {}

                for section, heading_emb in zip(sections, heading_embs):
                    target_id = section.get("id")

                    pos_score = float(self.ranker.model.similarity(positive_intent_emb, heading_emb)[0][0])
                    score = pos_score
                    neg_score = None
                    if negative_intent_emb is not None:
                        neg_score = float(self.ranker.model.similarity(negative_intent_emb, heading_emb)[0][0])
                        score = pos_score - neg_score

                    if boosting_fn:
                        score = boosting_fn(target_id, children_by_parent, score)

                    if score <= 0:
                        continue

                    context[target_id] = {
                        "score": score,
                        "pos_score": pos_score,
                        "neg_score": neg_score,
                        "parent": section.get("parent"),
                        "htext": section.get("htext"),
                        "chunk": [section],
                    }

                # Sort the context by score
                context = dict(
                    sorted(context.items(), key=lambda kv: kv[1]["score"], reverse=True)
                )

                candidates = dict(list(context.items())[:top_n])
                structured_json = copy.deepcopy(structured_json_base)
                structured_json["properties"]["chunk_ids"]["items"]["enum"] = list(candidates.keys())
                prompt_str = self._build_rag_chunk_selection_prompt(candidates, val_dict["LLMQuestion"])

                out[model_id][property] = {
                    "json_schema": structured_json,
                    "prompt": prompt_str,
                    "llm_response": None,
                    "chunks": [],
                }

                prompts.append(prompt_str)
                metadata.append((model_id, property, structured_json, candidates))

        # Run the LLM calls (one per prompt, since each has its own chunk_ids schema)
        self.logger.info(f"Running RAG extraction for {len(prompts)} prompts...")

        for prompt_str, (model_id, property, structured_json, candidates) in zip(prompts, metadata):
            request_extra_body = dict(extra_body)
            if use_structured_outputs:
                request_extra_body["structured_outputs"] = {"json": structured_json}
            else:
                request_extra_body["guided_json"] = {"guided_json": structured_json}

            attempts = 0
            response_text = None

            while attempts < max_retry:
                try:
                    self.logger.debug(f"extra_body being sent: {request_extra_body}")
                    resp = self.client.completions.create(
                        model=self.model_name,
                        prompt=prompt_str,
                        max_tokens=max_tokens,
                        temperature=sampler_kwargs.get("temperature"),
                        top_p=sampler_kwargs.get("top_p"),
                        extra_body=request_extra_body
                    )
                    response_text = resp.choices[0].text.strip()
                    self.logger.debug(f"resp recieved: {response_text}")
                    break

                except Exception as e:
                    attempts += 1
                    self.logger.error(
                        f"API Error during RAG generation for {model_id} - {property}: {e}. "
                        f"Attempt {attempts}/{max_retry}."
                    )
                    self.logger.info(f"Connection issue detected. Retrying in {connection_retry_delay} seconds...")
                    time.sleep(connection_retry_delay)

                    if attempts >= max_retry:
                        self.logger.error(f"Max retries reached for {model_id} - {property}. Skipping.")
                        response_text = None

            out[model_id][property]["llm_response"] = response_text

            # Map returned chunk_ids back to the actual chunk objects
            selected_chunks = []
            if response_text:
                try:
                    parsed = json.loads(response_text)
                    chunk_ids = parsed.get("chunk_ids", [])
                    self.logger.info(f"Correctly extracted JSON for {model_id} - {property}: {chunk_ids}")
                except (json.JSONDecodeError, AttributeError) as e:
                    self.logger.error(f"Failed to parse LLM response as JSON for {model_id} - {property}: {e}")
                    self.logger.error(response_text)
                    chunk_ids = []

                for cid in chunk_ids:
                    candidate = candidates.get(cid)
                    if candidate is None:
                        self.logger.warning(f"chunk_id '{cid}' returned by LLM not found in candidates for {model_id} - {property}.")
                        continue
                    selected_chunks.extend(candidate["chunk"])

            out[model_id][property]["chunks"] = selected_chunks

        self.logger.info(f"Completed RAG extraction for {len(out)} model cards.")
        return out

    def _load_structured_output_json(self, json_name) -> Dict[str, Any]:
        """Loads the structured output json into a dict"""
        
        metadata_dir = self.config.dir_metadata
        json_dir = os.path.join(metadata_dir, json_name)
        with open(json_dir, 'r', encoding='utf-8') as f:
            schema_dict = json.load(f)

        return schema_dict

    def parse_llm_output(self) -> Dict[str, Any]:
        """Parses the raw text output from the LLM into a structured dictionary."""
        result = {}
        reasoning_start_str = self.config.reasoning_start_str
        reasoning_end_str = self.config.reasoning_end_str

        if not reasoning_start_str or not reasoning_end_str:
            self.logger.info("Reasoning start or end strings not set. Parsing raw output without reasoning tokens.")

        for m_id, p_dict in self.extraction_results.items():
            result[m_id] = {}

            for p_name, generated_text in p_dict.items():
                json_string = ""
                
                if not reasoning_start_str or not reasoning_end_str or \
                   reasoning_start_str not in generated_text or reasoning_end_str not in generated_text:
                    matches = re.findall(r'\{.*?\}', generated_text, re.DOTALL)
                    if matches:
                        json_string = matches[0]
                        
                else:                                                 
                    ss = generated_text.split(reasoning_end_str)
                    matches = re.findall(r'\{.*?\}', ss[1], re.DOTALL)
                    json_string = matches[0] if matches else ss[1]

                try:
                    parsed_dict = json.loads(json_string)
                        
                except (json.JSONDecodeError, TypeError):
                    self.logger.error(f"{self.model_name} failed to output correct json for property: {p_name}, model: {m_id}. Generated output: {generated_text}. Returning the raw output as is.")
                    parsed_dict = {"result": generated_text}

                if not isinstance(parsed_dict, dict) or not parsed_dict.get("result", ""):
                    self.logger.error(f"{self.model_name} failed to output correct json for property: {p_name}, model: {m_id}. Generated output: {generated_text}. Unable to get a valid output for key 'result' from parsed json. Returning the raw output as is.")
                    parsed_dict = {"result": generated_text}

                result[m_id][p_name] = parsed_dict.get("result", "")

        return result