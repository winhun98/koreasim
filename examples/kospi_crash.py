"""Example: 코스피 8% 급락 + 서킷브레이커 발동 시 한국 투자자/시민의 반응."""

from __future__ import annotations

import asyncio
from pathlib import Path

from koreasim.analysis.aggregate import aggregate_by
from koreasim.llm.backend import LLMConfig, MockBackend
from koreasim.persona.loader import PersonaLoader
from koreasim.scenario.runner import ScenarioRunner
from koreasim.viz.dashboard import build_dashboard, render_text_report


async def main():
    # 코스피 시나리오는 income_bracket / 연령에 따른 분화가 핵심.
    loader = PersonaLoader.sample(count=200, seed=2026)
    backend = MockBackend(LLMConfig())
    await backend.start()
    try:
        runner = ScenarioRunner(backend)
        result = await runner.run(loader.personas, "kospi_crash", progress=True)
    finally:
        await backend.stop()

    print(render_text_report(result))

    # 소득 분위별 추가 breakdown
    print("\n=== 소득 분위별 반응 ===")
    for r in aggregate_by(result, "income_bracket"):
        print(
            f"  {r.group:>5s}  N={r.n:<4d}  반대={r.opposed_pct:5.1f}%  "
            f"강도={r.avg_intensity:.0f}  net={r.net_score:+.0f}"
        )

    out = Path("results")
    out.mkdir(exist_ok=True)
    build_dashboard(result, out / "kospi_crash.html")
    print("\n→ results/kospi_crash.html")


if __name__ == "__main__":
    asyncio.run(main())
