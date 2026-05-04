"""Compute receipt — quantify what running this on a laptop saved.

The headline numbers KoreaSim needs to communicate:
- N agents
- Elapsed wall-clock
- Tokens generated
- Estimated GPT-4 / Claude cost the same simulation would have cost
- Effective throughput (agents/sec)

These end up in the CLI summary, the HTML dashboard hero card, and the
auto-generated social card PNG.
"""

from __future__ import annotations

from dataclasses import dataclass

# Public 4o / Sonnet rates (mid-2026, USD per 1M tokens). Used only as a
# transparent reference point for the "cost saved" framing — *not* a precise
# billing oracle.
GPT_4O_INPUT_PER_1M = 2.50
GPT_4O_OUTPUT_PER_1M = 10.00
SONNET_INPUT_PER_1M = 3.00
SONNET_OUTPUT_PER_1M = 15.00

# Approximate per-agent token usage for KoreaSim's reaction prompt.
# system prompt (~300) + user prompt (~200) + response (~80).
DEFAULT_INPUT_TOKENS_PER_AGENT = 500
DEFAULT_OUTPUT_TOKENS_PER_AGENT = 80


@dataclass
class ComputeReceipt:
    """Cost / scale receipt for one scenario run."""

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

    @property
    def gpt4o_cost_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * GPT_4O_INPUT_PER_1M
            + self.output_tokens / 1_000_000 * GPT_4O_OUTPUT_PER_1M
        )

    @property
    def sonnet_cost_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * SONNET_INPUT_PER_1M
            + self.output_tokens / 1_000_000 * SONNET_OUTPUT_PER_1M
        )

    @property
    def local_cost_usd(self) -> float:
        # BitNet on a CPU = electricity-only. Negligible.
        return 0.0

    def to_dict(self) -> dict:
        return {
            "n_agents": self.n_agents,
            "elapsed_s": round(self.elapsed_s, 2),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "agents_per_sec": round(self.agents_per_sec, 1),
            "tokens_per_sec": round(self.tokens_per_sec, 0),
            "gpt4o_cost_usd": round(self.gpt4o_cost_usd, 2),
            "sonnet_cost_usd": round(self.sonnet_cost_usd, 2),
            "local_cost_usd": 0.0,
            "savings_vs_gpt4o_usd": round(self.gpt4o_cost_usd, 2),
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
