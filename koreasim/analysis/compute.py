"""Compute receipt — quantify the scale and throughput of one scenario run.

The headline numbers KoreaSim needs to communicate:
- N agents
- Elapsed wall-clock
- Tokens generated
- Effective throughput (agents/sec)

These end up in the CLI summary, the HTML dashboard hero card, and the
auto-generated social card PNG.
"""

from __future__ import annotations

from dataclasses import dataclass

# Approximate per-agent token usage for KoreaSim's reaction prompt.
# system prompt (~300) + user prompt (~200) + response (~80).
DEFAULT_INPUT_TOKENS_PER_AGENT = 500
DEFAULT_OUTPUT_TOKENS_PER_AGENT = 80


@dataclass
class ComputeReceipt:
    """Scale / throughput receipt for one scenario run."""

    n_agents: int
    elapsed_s: float
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def agents_per_sec(self) -> float:
        return self.n_agents / max(self.elapsed_s, 1e-6)

    @property
    def tokens_per_sec(self) -> float:
        return self.total_tokens / max(self.elapsed_s, 1e-6)

    def to_dict(self) -> dict:
        return {
            "n_agents": self.n_agents,
            "elapsed_s": round(self.elapsed_s, 2),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "agents_per_sec": round(self.agents_per_sec, 1),
            "tokens_per_sec": round(self.tokens_per_sec, 0),
        }


def receipt_for_run(
    n_agents: int,
    elapsed_s: float,
    *,
    input_tokens_per_agent: int = DEFAULT_INPUT_TOKENS_PER_AGENT,
    output_tokens_per_agent: int = DEFAULT_OUTPUT_TOKENS_PER_AGENT,
    actual_total_tokens: int | None = None,
) -> ComputeReceipt:
    """Build a receipt. Pass `actual_total_tokens` (sum of LLM-reported usage)
    to override the per-agent estimate when the backend tracks tokens.
    """
    if actual_total_tokens and actual_total_tokens > 0:
        # Split using the same input:output ratio as the defaults.
        ratio = input_tokens_per_agent / max(input_tokens_per_agent + output_tokens_per_agent, 1)
        input_tokens = int(actual_total_tokens * ratio)
        output_tokens = actual_total_tokens - input_tokens
    else:
        input_tokens = n_agents * input_tokens_per_agent
        output_tokens = n_agents * output_tokens_per_agent

    return ComputeReceipt(
        n_agents=n_agents,
        elapsed_s=elapsed_s,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
