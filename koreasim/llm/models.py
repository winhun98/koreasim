"""1.58-bit model presets — friendly aliases for known HuggingFace IDs.

Three actually-available BitNet/1.58-bit models, in increasing size:

    bitnet-2b     — microsoft/bitnet-b1.58-2B-4T          (~0.4GB, MIT)
    bitnet-3b     — 1bitLLM/bitnet_b1_58-3B               (~0.6GB, Apache 2.0)
    llama3-8b     — HF1BitLLM/Llama3-8B-1.58-100B-tokens  (~1.6GB, Llama 3)

The user picks one with `--model llama3-8b` (CLI) or
`LLMConfig.from_preset("llama3-8b")` (Python).

You can also pass an explicit HF id like `--model some-org/your-model` and
KoreaSim will forward it as-is to the bitnet.cpp / vLLM / NIM endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPreset:
    """Metadata for one 1.58-bit model that KoreaSim knows about."""

    key: str
    model_id: str           # the string passed to /v1/chat/completions as `model`
    display_name: str
    params_b: float         # billions of parameters
    weight_size_gb: float   # quantized on-disk size, approximate
    license: str
    notes: str

    def label(self) -> str:
        return f"{self.display_name} · {self.params_b:.1f}B · ~{self.weight_size_gb:.1f}GB · {self.license}"


PRESETS: dict[str, ModelPreset] = {
    "bitnet-2b": ModelPreset(
        key="bitnet-2b",
        model_id="microsoft/bitnet-b1.58-2B-4T",
        display_name="BitNet b1.58 2B (Microsoft)",
        params_b=2.0,
        weight_size_gb=0.4,
        license="MIT",
        notes="Smallest, fastest. English-centric — Korean output is acceptable but flat.",
    ),
    "bitnet-3b": ModelPreset(
        key="bitnet-3b",
        model_id="1bitLLM/bitnet_b1_58-3B",
        display_name="BitNet b1.58 3B (1bitLLM repro)",
        params_b=3.0,
        weight_size_gb=0.6,
        license="Apache-2.0",
        notes="A bit larger than the Microsoft 2B; community-reproduction.",
    ),
    "llama3-8b": ModelPreset(
        key="llama3-8b",
        model_id="HF1BitLLM/Llama3-8B-1.58-100B-tokens",
        display_name="Llama3 8B @ 1.58-bit",
        params_b=8.0,
        weight_size_gb=1.6,
        license="Llama 3 Community",
        notes="Largest 1.58-bit reproduction. 4× the model of bitnet-2b, still fits on a laptop.",
    ),
    # ----- Quantized stand-ins (Ollama, used when 1.58-bit weights aren't practical) -----
    "qwen3-8b": ModelPreset(
        key="qwen3-8b",
        model_id="qwen3:8b",
        display_name="Qwen3 8B (Q4_K_M)",
        params_b=8.2,
        weight_size_gb=5.2,
        license="Apache-2.0",
        notes="Default for laptop demos. Strong Korean, ~15 tok/s on a 16-core CPU via Ollama.",
    ),
    "llama3.1-8b": ModelPreset(
        key="llama3.1-8b",
        model_id="llama3.1:latest",
        display_name="Llama3.1 8B (Q4_K_M)",
        params_b=8.0,
        weight_size_gb=4.9,
        license="Llama 3.1 Community",
        notes="Stand-in via Ollama; English-leaning, weaker Korean than Qwen3.",
    ),
}

# Default to Qwen3 8B Q4_K_M — best laptop-class Korean output we found.
# 1.58-bit BitNet weights only run efficiently on AVX_VNNI / Apple Silicon CPUs;
# on plain AVX2 hardware, BitNet i2_s falls back to a slow software path
# (~0.1 tok/s for 8B), making the "runs on a laptop" claim impractical there.
DEFAULT_PRESET: str = "qwen3-8b"


def get_preset(name: str) -> ModelPreset | None:
    """Return preset by key, or None if `name` looks like an explicit HF id."""
    if not name:
        return PRESETS[DEFAULT_PRESET]
    if name in PRESETS:
        return PRESETS[name]
    # Anything that smells like an HF model id (`org/name`) is opaque to us — pass through.
    if "/" in name:
        return None
    raise ValueError(
        f"Unknown model preset '{name}'. "
        f"Choices: {sorted(PRESETS)}, or pass an explicit HF id (e.g. org/model-name)."
    )


def resolve_model(model_arg: str | None) -> tuple[str, ModelPreset | None]:
    """Resolve a CLI/API `model` argument into (model_id, preset_or_none).

    - `None`/empty → use DEFAULT_PRESET.
    - Known preset key → preset's `model_id`.
    - Explicit HF id → return as-is, preset=None.
    """
    if not model_arg:
        p = PRESETS[DEFAULT_PRESET]
        return p.model_id, p
    p = get_preset(model_arg)
    if p is not None:
        return p.model_id, p
    return model_arg, None
