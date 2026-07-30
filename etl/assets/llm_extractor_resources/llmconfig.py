import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass(frozen=True)
class LLMConfig:
    dir_metadata: Path = Path(__file__).parent
    connection_retry_delay: int = 30 # seconds
    vllm_image: str = os.getenv("IMAGE", "vllm/vllm-openai:latest")
    gpu_kv_cache_size: int = int(os.getenv("GPU_KV_CACHE_SIZE", 100000))
    reasoning_start_str: str = os.getenv("REASONING_START_STR", "")
    reasoning_end_str: str = os.getenv("REASONING_END_STR", "")
    thinking_token_budget: int = int(os.getenv("THINKING_TOKEN_BUDGET", 512))
    enable_thinking: bool = os.getenv("ENABLE_THINKING", True)

    vllm_kwargs: Dict[str, Any] = field(default_factory=lambda: {
        "api_base_url": "http://vllm:8000/v1",
        "api_key": os.getenv("HUGGINGFACE_API_TOKEN", "dummy-key"),
        "vllm_timeout": 600, # seconds
        "vllm_interval": 2.0
    })
    
    sampler_kwargs: Dict[str, Any] = field(default_factory=lambda: {
        "max_tokens": 8096, 
        "temperature": 1.0, 
        "repetition_penalty": 1.1, 
        "top_p": 0.95, 
        "skip_special_tokens": False,
    })

    chat_template_kwargs: Dict[str, bool] = field(default_factory=lambda: {
        "tokenize": False, 
        "add_generation_prompt": True,
    })

def __post_init__(self):
    if self.thinking_token_budget > 0:
        self.sampler_kwargs["thinking_token_budget"] = self.thinking_token_budget

    if self.enable_thinking:
        self.chat_template_kwargs["enable_thinking"] = True