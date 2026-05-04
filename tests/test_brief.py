"""Brief generation + verbatim guard tests."""

from __future__ import annotations

import json

import pytest

from koreasim.llm.backend import LLMBackend, LLMResponse
from koreasim.scenario.article import ArticleSource
from koreasim.scenario.brief import (
    Brief,
    BriefGenerationError,
    _validate_verbatim,
    generate_brief,
)

ARTICLE_TEXT = (
    "정부가 자동차 보험료를 내년 1월부터 평균 30% 인상한다고 발표했습니다. "
    "운전자 1,200만 명이 영향을 받을 것으로 예상됩니다. "
    '김모 씨는 "부담이 너무 크다"며 반대 입장을 밝혔습니다. '
    "전문가들은 손해율 상승을 그 배경으로 지목했습니다."
)


def _article() -> ArticleSource:
    return ArticleSource(
        url="https://example.com/test",
        text=ARTICLE_TEXT,
        title="보험료 인상",
        fetched_at="2026-04-29T00:00:00",
    )


class StubBriefBackend(LLMBackend):
    """Returns canned responses in sequence regardless of prompt."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0
        self.last_prompt: str | None = None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def generate(
        self, prompt, *, system="", temperature=None, max_tokens=None, json_mode=False
    ):
        self.calls += 1
        self.last_prompt = prompt
        idx = min(self.calls - 1, len(self._responses) - 1)
        return LLMResponse(text=self._responses[idx], tokens_used=128)


def _good_response() -> str:
    return json.dumps(
        {
            "actor": "정부",
            "action": "자동차 보험료 인상",
            "magnitude": "30% 인상",
            "target": "운전자 1,200만 명",
            "time": "내년 1월",
            "scope": "전국",
            "key_numbers": ["30% 인상", "1,200만 명"],
            "quotes": ["부담이 너무 크다"],
            "summary": "정부가 자동차 보험료를 내년 1월부터 30% 인상하기로 했습니다.",
        },
        ensure_ascii=False,
    )


def _bad_response() -> str:
    return json.dumps(
        {
            "actor": "정부",
            "action": "보험료 인상",
            "magnitude": "50% 인상",
            "target": "운전자",
            "time": "내년 1월",
            "scope": "전국",
            "key_numbers": ["50% 인상"],  # not in source
            "quotes": ["환영합니다"],  # not in source
            "summary": "정부가 보험료 인상을 발표했습니다.",
        },
        ensure_ascii=False,
    )


async def test_generate_brief_passes_when_verbatim_match():
    backend = StubBriefBackend([_good_response()])
    brief = await generate_brief(backend, _article())
    assert isinstance(brief, Brief)
    assert brief.unverified == []
    assert "30% 인상" in brief.key_numbers
    assert "부담이 너무 크다" in brief.quotes
    assert backend.calls == 1
    assert brief.summary


async def test_generate_brief_drops_unverified_after_retry():
    backend = StubBriefBackend([_bad_response(), _bad_response()])
    brief = await generate_brief(backend, _article())
    assert backend.calls == 2  # initial + 1 retry
    assert any("50% 인상" in u for u in brief.unverified)
    assert any("환영합니다" in u for u in brief.unverified)
    assert "50% 인상" not in brief.key_numbers
    assert "환영합니다" not in brief.quotes
    assert brief.summary  # summary still preserved


async def test_generate_brief_retry_succeeds():
    backend = StubBriefBackend([_bad_response(), _good_response()])
    brief = await generate_brief(backend, _article())
    assert backend.calls == 2
    assert brief.unverified == []
    assert "30% 인상" in brief.key_numbers


async def test_generate_brief_handles_messy_json():
    raw = (
        "Sure, here you go:\n```json\n"
        + _good_response()
        + "\n```\nDone!"
    )
    backend = StubBriefBackend([raw])
    brief = await generate_brief(backend, _article())
    assert brief.actor == "정부"
    assert "30% 인상" in brief.key_numbers


async def test_generate_brief_retry_prompt_lists_failed_items():
    """The retry prompt should explicitly list which items failed verbatim check."""
    backend = StubBriefBackend([_bad_response(), _good_response()])
    await generate_brief(backend, _article())
    # 2nd call's prompt is the retry prompt — should mention the failed items.
    assert backend.last_prompt is not None
    assert "50% 인상" in backend.last_prompt or "환영합니다" in backend.last_prompt


def test_validate_verbatim_passes_on_exact_match():
    failed = _validate_verbatim(
        {"key_numbers": ["30% 인상"], "quotes": ["부담이 너무 크다"]},
        ARTICLE_TEXT,
    )
    assert failed == []


def test_validate_verbatim_normalizes_whitespace():
    article = "보험료가  30%   인상됩니다"
    failed = _validate_verbatim(
        {"key_numbers": ["30% 인상"], "quotes": []},
        article,
    )
    assert failed == []


def test_validate_verbatim_flags_missing_items():
    failed = _validate_verbatim(
        {"key_numbers": ["50% 인상"], "quotes": ["환영합니다"]},
        ARTICLE_TEXT,
    )
    assert len(failed) == 2
    assert any("50%" in f for f in failed)
    assert any("환영합니다" in f for f in failed)


async def test_generate_brief_thin_retry_does_not_blank_first_attempt():
    """Smaller LLMs often return only the corrected fields on retry. The earlier
    attempt's richer fields (actor/summary) must be preserved."""
    rich_first = json.dumps({
        "actor": "정부",
        "action": "보험료 인상",
        "magnitude": "30% 인상",
        "target": "운전자",
        "time": "내년 1월",
        "scope": "전국",
        "key_numbers": ["50% 인상"],   # bad — triggers retry
        "quotes": ["부담이 너무 크다"],
        "summary": "정부가 자동차 보험료를 인상하기로 했습니다.",
    }, ensure_ascii=False)
    thin_retry = json.dumps({
        "actor": "",
        "action": "",
        "magnitude": "",
        "target": "",
        "time": "",
        "scope": "",
        "key_numbers": ["30% 인상"],
        "quotes": [],
        "summary": "",
    }, ensure_ascii=False)
    backend = StubBriefBackend([rich_first, thin_retry])
    brief = await generate_brief(backend, _article())
    assert brief.actor == "정부"
    assert brief.summary  # not blanked!
    assert "30% 인상" in brief.key_numbers  # retry's correction took effect
    assert backend.calls == 2


async def test_generate_brief_raises_when_both_attempts_unparseable():
    backend = StubBriefBackend(["this is not json", "still not json"])
    with pytest.raises(BriefGenerationError):
        await generate_brief(backend, _article())
    assert backend.calls == 2


async def test_generate_brief_filters_empty_string_items():
    """LLM may return empty strings or whitespace-only items in lists — drop them."""
    response = json.dumps({
        "actor": "정부",
        "action": "보험료 인상",
        "magnitude": "30% 인상",
        "target": "운전자",
        "time": "내년 1월",
        "scope": "전국",
        "key_numbers": ["30% 인상", "", "  "],  # last two should be dropped
        "quotes": ["부담이 너무 크다", ""],
        "summary": "정부가 자동차 보험료를 내년 1월부터 30% 인상합니다.",
    }, ensure_ascii=False)
    backend = StubBriefBackend([response])
    brief = await generate_brief(backend, _article())
    assert brief.key_numbers == ["30% 인상"]
    assert brief.quotes == ["부담이 너무 크다"]


def test_validate_verbatim_handles_none_and_non_string():
    """Mixed-type list items (None, ints) should be silently skipped, not crash."""
    failed = _validate_verbatim(
        {"key_numbers": [None, 42, "30% 인상"], "quotes": None},
        ARTICLE_TEXT,
    )
    assert failed == []  # 30% 인상 matches; None/42/None all skipped


def test_brief_to_dict_includes_all_fields():
    b = Brief(
        actor="정부", action="x", magnitude="y", target="z", time="w",
        scope="전국", key_numbers=["1"], quotes=["q"], summary="s",
        unverified=[],
    )
    d = b.to_dict()
    for k in (
        "actor", "action", "magnitude", "target", "time", "scope",
        "key_numbers", "quotes", "summary", "unverified",
    ):
        assert k in d
