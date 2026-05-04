"""LLM-driven brief generation from a fetched article.

Pipeline: article text → LLM (one call) → structured brief JSON → verbatim
guard → (failed?) one retry → final Brief. Items that still fail verbatim
checking after retry are dropped from `key_numbers` / `quotes` and recorded
in `unverified` so the dashboard can warn the reader.

The verbatim guard normalises whitespace before substring matching — Korean
news articles often have erratic spaces / line breaks that the LLM cleans up
when quoting. We only require character-level identity, not raw byte identity.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field

from koreasim.llm.backend import LLMBackend
from koreasim.scenario.article import ArticleSource
from koreasim.scenario.prompts import BRIEF_GENERATION_PROMPT, BRIEF_RETRY_PROMPT

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ("actor", "action", "magnitude", "target", "time", "scope")
_LIST_FIELDS = ("key_numbers", "quotes")
_BRIEF_MAX_TOKENS = 1024
_BRIEF_TEMPERATURE = 0.3


class BriefGenerationError(Exception):
    """Raised when the LLM response cannot be parsed into a brief at all."""


@dataclass
class Brief:
    actor: str
    action: str
    magnitude: str
    target: str
    time: str
    scope: str
    key_numbers: list[str] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)
    summary: str = ""
    unverified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ----- Public API -----


async def generate_brief(
    backend: LLMBackend,
    article: ArticleSource,
    *,
    max_retries: int = 1,
) -> Brief:
    """Generate a structured brief from an article, with one retry on verbatim failures.

    Strategy:
      attempt 1: full BRIEF_GENERATION_PROMPT
      attempts 2..N: BRIEF_RETRY_PROMPT listing the failed items
      if final attempt still fails: drop unverified items, keep summary, mark them.
    """
    article_text = article.text
    failed_items: list[str] = []
    parsed: dict | None = None

    for attempt in range(max_retries + 1):
        if attempt == 0:
            prompt = BRIEF_GENERATION_PROMPT.format(article_text=article_text)
        else:
            prompt = BRIEF_RETRY_PROMPT.format(
                failed_items="\n".join(f"- {f}" for f in failed_items),
                article_text=article_text,
            )

        resp = await backend.generate(
            prompt,
            temperature=_BRIEF_TEMPERATURE,
            max_tokens=_BRIEF_MAX_TOKENS,
            json_mode=False,
        )
        candidate = _parse_brief_json(resp.text)
        if candidate is None:
            logger.warning("brief attempt %d: unparseable JSON", attempt + 1)
            failed_items = ["JSON 파싱 실패"]
            continue

        # Merge with earlier attempt so a thin retry doesn't blank-out the
        # richer first response. Smaller models (e.g. qwen3:8b) frequently
        # return only the verbatim-corrected fields on retry, leaving every
        # other slot empty. We keep the new values for non-empty fields and
        # fall back to the previous attempt for empties.
        if parsed is not None:
            candidate = _merge_brief(parsed, candidate)
        failed_items = _validate_verbatim(candidate, article_text)
        parsed = candidate
        if not failed_items:
            break  # clean — done

    if parsed is None:
        raise BriefGenerationError(
            "brief LLM never returned parseable JSON (after retries)"
        )

    if failed_items:
        logger.warning(
            "brief still has %d unverified items after retry — dropping them",
            len(failed_items),
        )
        parsed = _drop_unverified(parsed, failed_items)

    return _build_brief(parsed, unverified=failed_items)


# ----- Verbatim guard -----


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _validate_verbatim(brief: dict, article_text: str) -> list[str]:
    """Return tagged items that don't appear in `article_text` (whitespace-normalised).

    Tag format: `"key_number: <item>"` or `"quote: <item>"` so the retry prompt
    is unambiguous about which slot the item came from.
    """
    haystack = _normalise(article_text)
    failed: list[str] = []
    for n in brief.get("key_numbers", []) or []:
        if not isinstance(n, str):
            continue
        needle = _normalise(n)
        if needle and needle not in haystack:
            failed.append(f"key_number: {n}")
    for q in brief.get("quotes", []) or []:
        if not isinstance(q, str):
            continue
        needle = _normalise(q)
        if needle and needle not in haystack:
            failed.append(f"quote: {q}")
    return failed


def _merge_brief(prev: dict, new: dict) -> dict:
    """Take new's value when non-empty, else fall back to prev's value.

    Empty = empty string after strip(), or empty list, or None. Strings and
    lists are compared structurally; this lets a retry that only refills
    `key_numbers` keep the original `actor` / `summary` from the first attempt.
    """
    out = dict(prev)
    for key, val in new.items():
        if isinstance(val, str):
            if val.strip():
                out[key] = val
        elif isinstance(val, list):
            if val:
                out[key] = val
        elif val is not None:
            out[key] = val
    return out


def _drop_unverified(brief: dict, failed_items: list[str]) -> dict:
    """Remove items listed in `failed_items` from key_numbers / quotes."""
    bad_numbers = {f.removeprefix("key_number: ") for f in failed_items if f.startswith("key_number: ")}
    bad_quotes = {f.removeprefix("quote: ") for f in failed_items if f.startswith("quote: ")}
    out = dict(brief)
    out["key_numbers"] = [n for n in (brief.get("key_numbers") or []) if n not in bad_numbers]
    out["quotes"] = [q for q in (brief.get("quotes") or []) if q not in bad_quotes]
    return out


# ----- JSON extraction (mirrors the robust parser in runner.py) -----


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _parse_brief_json(text: str) -> dict | None:
    """Find the first balanced `{...}` block in `text` and json.loads it.

    Tolerates ```json fences and prose around the JSON. Returns None on failure.
    """
    if not text or not text.strip():
        return None
    raw = text.strip()
    fence = _FENCE_RE.search(raw)
    candidate = fence.group(1).strip() if fence else raw

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    block = _extract_balanced_brace_block(candidate)
    if not block:
        return None
    try:
        parsed = json.loads(block)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _extract_balanced_brace_block(text: str) -> str | None:
    """Return the first balanced `{...}` block, ignoring braces inside strings."""
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
                return text[start : i + 1]
    return None


# ----- Brief construction -----


def _build_brief(parsed: dict, *, unverified: list[str]) -> Brief:
    def _str(key: str) -> str:
        v = parsed.get(key, "")
        return v.strip() if isinstance(v, str) else ""

    def _list(key: str) -> list[str]:
        v = parsed.get(key) or []
        return [x for x in v if isinstance(x, str) and x.strip()]

    return Brief(
        actor=_str("actor"),
        action=_str("action"),
        magnitude=_str("magnitude"),
        target=_str("target"),
        time=_str("time"),
        scope=_str("scope"),
        key_numbers=_list("key_numbers"),
        quotes=_list("quotes"),
        summary=_str("summary"),
        unverified=list(unverified),
    )
