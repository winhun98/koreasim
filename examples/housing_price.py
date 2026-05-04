"""Example: 수도권 아파트 가격 20% 상승 시 한국 사회 반응."""

from __future__ import annotations

import asyncio
from pathlib import Path

from koreasim.llm.backend import LLMConfig, MockBackend
from koreasim.persona.loader import PersonaLoader
from koreasim.scenario.runner import ScenarioRunner
from koreasim.viz.dashboard import build_dashboard, render_text_report


async def main():
    loader = PersonaLoader.sample(count=200, seed=7)
    backend = MockBackend(LLMConfig())
    await backend.start()
    try:
        runner = ScenarioRunner(backend)
        result = await runner.run(loader.personas, "housing_price", progress=True)
    finally:
        await backend.stop()

    print(render_text_report(result))
    out = Path("results")
    out.mkdir(exist_ok=True)
    build_dashboard(result, out / "housing_price.html")
    print("\n→ results/housing_price.html")


if __name__ == "__main__":
    asyncio.run(main())
