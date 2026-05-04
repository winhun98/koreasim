"""LLM backends — BitNet 1.58-bit (default) + any OpenAI-compatible endpoint."""

from koreasim.llm.backend import (
    LLMBackend,
    LLMConfig,
    LLMResponse,
    MockBackend,
    OpenAICompatibleBackend,
)
from koreasim.llm.models import DEFAULT_PRESET, PRESETS, ModelPreset, get_preset, resolve_model

__all__ = [
    "LLMBackend",
    "LLMConfig",
    "LLMResponse",
    "MockBackend",
    "OpenAICompatibleBackend",
    "ModelPreset",
    "PRESETS",
    "DEFAULT_PRESET",
    "get_preset",
    "resolve_model",
]
