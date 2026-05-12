import os
from pathlib import Path

class LLMConfig:
    DIR_METADATA = Path(__file__).parent

    CONNECTION_RETRY_DELAY = 30 # seconds

    LLM_KWARGS = {
        "api_base_url": "http://vllm:8000/v1",
        "api_key": os.getenv("HUGGINGFACE_API_TOKEN", "dummy-key"),
        "model": "google/gemma-4-E4B-it", 
        "max_model_len": 65536,
        "trust_remote_code": True,
        "chat_template" : DIR_METADATA / "tool_chat_template_gemma4.jinja",
    }

    BATCH_SIZE = 125

    SAMPLER_KWARGS = {
        "max_tokens": 8096, 
        "temperature": 1.0, 
        "repetition_penalty": 1.1, 
        "top_p": 0.95, 
        "skip_special_tokens": False, 
        "thinking_token_budget": 768
    }

    CHAT_TEMPLATE_KWARGS = {
        "tokenize": False, 
        "add_generation_prompt": True, 
        "enable_thinking": True
    }