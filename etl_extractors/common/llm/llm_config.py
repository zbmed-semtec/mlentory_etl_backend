import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any

def env_bool(name: str, default: bool) -> bool:
    """os.getenv returns a string, and "false" is truthy. Read it as a real bool."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")

@dataclass(frozen=True)
class LLMConfig:
    dir_metadata: Path = Path(__file__).parent / "resources"
    structured_outputs: bool = env_bool("STRUCTURED_OUTPUTS", False) # set per GPU profile, needs vLLM >= 0.12
    priority_scheduling: bool = env_bool("PRIORITY_SCHEDULING", False) # set per GPU profile, vLLM runs with --scheduling-policy priority
    opener_timeout_s: int = 120 # max seconds to wait for a document's first token before sending its other properties
    system_prompt: str = "You are a helpful assistant designed to extract specific information based on provided criteria. Think carefully what the extraction task is, and then strictly answer as instructed."

    vllm_kwargs: Dict[str, Any] = field(default_factory=lambda: {
        "api_base_url": "http://vllm:8000/v1",
        "api_key": os.getenv("HUGGINGFACE_API_TOKEN", "dummy-key"),
        "timeout": 600, # seconds
        "interval": 2.0
    })

    sampler_kwargs: Dict[str, Any] = field(default_factory=lambda: {
        "max_tokens": 2048,
        "temperature": 1.0,
        "top_p": 0.95,
        "skip_special_tokens": False,
    })
