"""Smoke tests for ScenarioRunner with the MockBackend."""

from __future__ import annotations

import pytest

from koreasim.analysis.aggregate import aggregate_by, summarize
from koreasim.llm.backend import LLMConfig, MockBackend
from koreasim.persona.loader import PersonaLoader
from koreasim.scenario.runner import ScenarioRunner, _parse_reaction


@pytest.mark.asyncio
async def test_scenario_run_with_mock_backend():
    loader = PersonaLoader.sample(count=20, seed=42)
    backend = MockBackend(LLMConfig())
    await backend.start()
    try:
        runner = ScenarioRunner(backend)
        result = await runner.run(loader.personas, "pension_age")
    finally:
        await backend.stop()

    assert result.n == 20
    assert result.n_failed == 0
    assert all(r.sentiment in ("supportive", "neutral", "opposed") for r in result.reactions)
    assert all(0 <= r.intensity <= 100 for r in result.reactions)


@pytest.mark.asyncio
async def test_scenario_freeform_text():
    loader = PersonaLoader.sample(count=10, seed=42)
    backend = MockBackend(LLMConfig())
    await backend.start()
    try:
        runner = ScenarioRunner(backend)
        result = await runner.run(loader.personas, "갑자기 폭설이 내려 출퇴근이 마비되었습니다.")
    finally:
        await backend.stop()

    assert result.n == 10
    assert "폭설" in result.scenario


def test_scenario_kospi_template_resolves():
    text = ScenarioRunner.resolve_scenario("kospi_crash")
    assert "코스피" in text
    assert "서킷브레이커" in text


@pytest.mark.asyncio
async def test_aggregate_by_age_bucket():
    loader = PersonaLoader.sample(count=50, seed=42)
    backend = MockBackend(LLMConfig())
    await backend.start()
    try:
        runner = ScenarioRunner(backend)
        result = await runner.run(loader.personas, "pension_age")
    finally:
        await backend.stop()

    rows = aggregate_by(result, by="age_bucket")
    assert sum(r.n for r in rows) == result.n
    for r in rows:
        assert abs((r.supportive_pct + r.neutral_pct + r.opposed_pct) - 100) < 0.1 or r.n == 0


@pytest.mark.asyncio
async def test_summary_headline_generated():
    loader = PersonaLoader.sample(count=30, seed=42)
    backend = MockBackend(LLMConfig())
    await backend.start()
    try:
        runner = ScenarioRunner(backend)
        result = await runner.run(loader.personas, "pension_age")
    finally:
        await backend.stop()

    summary = summarize(result)
    assert summary.n == 30
    assert "표본" in summary.headline


def test_reaction_parser_clean_json():
    raw = '{"sentiment": "supportive", "intensity": 75, "reasoning": "좋습니다"}'
    r = _parse_reaction("p1", raw)
    assert r.sentiment == "supportive"
    assert r.intensity == 75
    assert "좋습니다" in r.reasoning


def test_reaction_parser_messy_text_around_json():
    raw = 'Sure, here is my answer: {"sentiment":"opposed","intensity":90,"reasoning":"부담입니다"} thanks!'
    r = _parse_reaction("p1", raw)
    assert r.sentiment == "opposed"
    assert r.intensity == 90


def test_reaction_parser_invalid_falls_back_to_keywords():
    raw = "이 정책에 강하게 반대합니다. 부담이 너무 큽니다."
    r = _parse_reaction("p1", raw)
    assert r.sentiment == "opposed"


def test_reaction_parser_clamps_intensity():
    raw = '{"sentiment": "neutral", "intensity": 200, "reasoning": "x"}'
    r = _parse_reaction("p1", raw)
    assert r.intensity == 100

    raw = '{"sentiment": "neutral", "intensity": -50, "reasoning": "x"}'
    r = _parse_reaction("p1", raw)
    assert r.intensity == 0
