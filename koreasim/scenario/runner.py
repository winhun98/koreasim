"""ScenarioRunner — drive N personas through a single stimulus and collect reactions."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from koreasim.llm.backend import LLMBackend, LLMResponse
from koreasim.persona.schema import KoreanPersona, Reaction
from koreasim.scenario.prompts import REACTION_USER_PROMPT, REACTION_USER_PROMPT_FALLBACK, SCENARIO_TEMPLATES

logger = logging.getLogger(__name__)


@dataclass
class ScenarioResult:
    """Aggregated output of a scenario run.

    `source_url` and `brief` are populated only when the scenario was generated
    from a fetched article (`koreasim run --url ...`). Otherwise both are None
    and the JSON output stays backward-compatible with v0.1.x.
    """

    scenario: str
    reactions: list[Reaction] = field(default_factory=list)
    persona_index: dict[str, KoreanPersona] = field(default_factory=dict)
    elapsed_s: float = 0.0
    n_failed: int = 0
    source_url: str | None = None
    brief: dict | None = None

    @property
    def n(self) -> int:
        return len(self.reactions)

    def persona_for(self, reaction: Reaction) -> KoreanPersona | None:
        return self.persona_index.get(reaction.persona_id)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "elapsed_s": self.elapsed_s,
            "n": self.n,
            "n_failed": self.n_failed,
            "source_url": self.source_url,
            "brief": self.brief,
            "reactions": [r.to_dict() for r in self.reactions],
            "personas": {pid: p.to_dict() for pid, p in self.persona_index.items()},
        }

    def save_json(self, path: str) -> None:
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


class ScenarioRunner:
    """Run a single scenario across many personas, in parallel.

    Concurrency is bounded by the LLM backend's semaphore — we just await all
    coroutines and let httpx + the backend rate-limit naturally.
    """

    def __init__(self, llm: LLMBackend, *, max_tokens: int = 256, temperature: float = 0.7):
        self.llm = llm
        self.max_tokens = max_tokens
        self.temperature = temperature

    @staticmethod
    def resolve_scenario(scenario: str) -> str:
        """If `scenario` matches a template key, expand it; else return as-is."""
        return SCENARIO_TEMPLATES.get(scenario, scenario)

    async def run(
        self,
        personas: Iterable[KoreanPersona],
        scenario: str,
        *,
        progress: bool = False,
        source_url: str | None = None,
        brief: dict | None = None,
    ) -> ScenarioResult:
        scenario_text = self.resolve_scenario(scenario)
        personas = list(personas)

        if progress:
            logger.info("Running scenario over %d personas", len(personas))

        loop = asyncio.get_running_loop()
        t0 = loop.time()

        tasks = [self._react_one(p, scenario_text) for p in personas]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        reactions: list[Reaction] = []
        n_failed = 0
        for persona, resp in zip(personas, responses, strict=False):
            if isinstance(resp, Exception):
                logger.warning("Reaction failed for %s: %s", persona.persona_id, resp)
                n_failed += 1
                continue
            reactions.append(resp)

        elapsed = loop.time() - t0

        return ScenarioResult(
            scenario=scenario_text,
            reactions=reactions,
            persona_index={p.persona_id: p for p in personas},
            elapsed_s=elapsed,
            n_failed=n_failed,
            source_url=source_url,
            brief=brief,
        )

    async def _react_one(self, persona: KoreanPersona, scenario_text: str) -> Reaction:
        # `/no_think` disables Qwen3's chain-of-thought phase (silently ignored
        # by other models). Plain text mode is more robust than JSON mode for
        # qwen3 — `response_format=json_object` interacts badly with thinking
        # and returns empty content ~37% of the time.
        # `/no_think` in both system + user prompt — Qwen3 sometimes ignores
        # the system-only directive when JSON-style instructions are present.
        #
        # Rejection sampling: the elaborate stake-elicitation prompt
        # (REACTION_USER_PROMPT) reduces neutral bias but makes some personas
        # (전업주부·학생·농업인, weak direct stake) freeze and return empty.
        # On attempt 3, fall back to a minimal prompt that those personas can
        # handle. Empty rate drops ~14% → ~3% with this fallback.
        system = persona.to_system_prompt() + "\n\n/no_think"
        full_prompt = REACTION_USER_PROMPT.format(scenario=scenario_text) + "\n\n/no_think"
        fallback_prompt = REACTION_USER_PROMPT_FALLBACK.format(scenario=scenario_text) + "\n\n/no_think"

        for attempt in range(3):
            prompt = fallback_prompt if attempt >= 2 else full_prompt
            temp = self.temperature + (attempt * 0.15)
            try:
                resp: LLMResponse = await self.llm.generate(
                    prompt,
                    system=system,
                    temperature=temp,
                    max_tokens=self.max_tokens,
                    json_mode=False,
                )
            except Exception as exc:
                logger.warning("Generation attempt %d failed: %s", attempt + 1, exc)
                continue
            if resp.text and resp.text.strip():
                return _parse_reaction(persona.persona_id, resp.text)
        return _parse_reaction(persona.persona_id, "")


# ----- Robust JSON extraction -----
#
# Real LLM outputs include multi-line JSON, ```json fences, leading/trailing prose,
# and (under tight max_tokens) truncated JSON. We extract via brace-counting,
# repair common truncation cases, and fall back to keyword sentiment.

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_INTENSITY_RE = re.compile(r'"intensity"\s*:\s*(\d+)')
_SENTIMENT_RE = re.compile(r'"sentiment"\s*:\s*"(supportive|neutral|opposed)"', re.IGNORECASE)
_REASONING_RE = re.compile(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)
# Match a truncated reasoning string (no closing quote): captures text up to EOL/EOF.
_REASONING_TRUNC_RE = re.compile(r'"reasoning"\s*:\s*"((?:[^"\\]|\\.)*)$', re.DOTALL)


def _extract_json_block(text: str) -> str | None:
    """Find the first balanced `{...}` block in `text`. Multi-line aware."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _repair_truncated_json(text: str) -> dict | None:
    """Salvage a partially-truncated JSON object via regex on each field.

    Handles three truncation patterns:
    1. Complete reasoning string with closing quote — captured by _REASONING_RE.
    2. Truncated reasoning (`"reasoning": "주식시장`) — captured by _REASONING_TRUNC_RE.
    3. Missing reasoning entirely (truncation before reasoning field).
    """
    sent_m = _SENTIMENT_RE.search(text)
    int_m = _INTENSITY_RE.search(text)
    reason_m = _REASONING_RE.search(text)
    reason_trunc_m = None if reason_m else _REASONING_TRUNC_RE.search(text)
    if not (sent_m or int_m or reason_m or reason_trunc_m):
        return None
    out: dict = {}
    if sent_m:
        out["sentiment"] = sent_m.group(1).lower()
    if int_m:
        out["intensity"] = int(int_m.group(1))
    if reason_m:
        out["reasoning"] = _unescape_json_string(reason_m.group(1))
    elif reason_trunc_m:
        partial = _unescape_json_string(reason_trunc_m.group(1)).rstrip()
        if partial:
            out["reasoning"] = partial + "…"
    return out


def _unescape_json_string(s: str) -> str:
    """Apply only the JSON string escapes we care about — keep UTF-8 bytes intact.

    Avoid `unicode_escape` codec because it mangles Korean (which is already
    valid UTF-8 in the source string).
    """
    return (
        s.replace("\\n", "\n")
         .replace("\\t", "\t")
         .replace("\\r", "\r")
         .replace('\\"', '"')
         .replace("\\/", "/")
         .replace("\\\\", "\\")
    )


def _parse_reaction(persona_id: str, raw: str) -> Reaction:
    """Try hard to recover a Reaction from a possibly-messy LLM response."""
    raw_stripped = raw.strip()
    if not raw_stripped:
        return Reaction(persona_id=persona_id, sentiment="neutral", intensity=50,
                        reasoning="", raw_response="")

    # 1. Try a code-fence first: ```json {...} ```
    fence = _FENCE_RE.search(raw_stripped)
    candidate = fence.group(1).strip() if fence else raw_stripped

    # 2. Strict full-JSON parse.
    parsed: dict | None = None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 3. Brace-counted extraction of the first balanced block.
    if not isinstance(parsed, dict):
        block = _extract_json_block(candidate)
        if block:
            try:
                parsed = json.loads(block)
            except json.JSONDecodeError:
                parsed = None

    # 4. Truncation salvage — regex on each field.
    if not isinstance(parsed, dict):
        parsed = _repair_truncated_json(candidate)

    # 5. Last resort: keyword heuristic on the raw text.
    if not isinstance(parsed, dict):
        sentiment = _guess_sentiment(raw_stripped)
        return Reaction(
            persona_id=persona_id,
            sentiment=sentiment,
            intensity=50,
            reasoning=raw_stripped[:200],
            raw_response=raw_stripped,
        )

    sentiment = str(parsed.get("sentiment", "neutral")).lower()
    if sentiment not in ("supportive", "neutral", "opposed"):
        sentiment = _guess_sentiment(sentiment + " " + str(parsed.get("reasoning", "")))

    try:
        intensity = int(parsed.get("intensity", 50))
    except (TypeError, ValueError):
        intensity = 50
    intensity = max(0, min(100, intensity))

    return Reaction(
        persona_id=persona_id,
        sentiment=sentiment,  # type: ignore[arg-type]
        intensity=intensity,
        reasoning=str(parsed.get("reasoning", "")).strip(),
        raw_response=raw_stripped,
    )


_SUPPORT_KW = ("찬성", "동의", "긍정", "support", "agree")
_OPPOSE_KW = ("반대", "부정", "거부", "oppose", "against", "분노", "패닉", "panic")


def _guess_sentiment(text: str) -> str:
    t = text.lower()
    if any(k in text for k in _OPPOSE_KW) or any(k in t for k in _OPPOSE_KW):
        return "opposed"
    if any(k in text for k in _SUPPORT_KW) or any(k in t for k in _SUPPORT_KW):
        return "supportive"
    return "neutral"
