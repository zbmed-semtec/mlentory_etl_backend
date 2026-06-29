import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass(frozen=True)
class LLMConfig:
    dir_metadata: Path = Path(__file__).parent
    connection_retry_delay: int = 30 # seconds
    batch_size: int = 125

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
        "thinking_token_budget": 768
    })

    chat_template_kwargs: Dict[str, bool] = field(default_factory=lambda: {
        "tokenize": False, 
        "add_generation_prompt": True, 
        "enable_thinking": True
    })