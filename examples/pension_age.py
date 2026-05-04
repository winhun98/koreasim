"""Example: 국민연금 수령 개시 연령 상향 시 한국 사회의 반응 시뮬레이션.

Usage:
    python examples/pension_age.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from koreasim.analysis.aggregate import aggregate_by, summarize
from koreasim.llm.backend import LLMConfig, MockBackend
from koreasim.persona.loader import PersonaLoader
from koreasim.scenario.runner import ScenarioRunner
from koreasim.viz.dashboard import build_dashboard, render_text_report


async def main():
    # 1. 표본 200명 (광역시도 stratified)
    loader = PersonaLoader.sample(count=200, seed=42)

    # 2. Mock LLM (실제로는 OpenAICompatibleBackend로 BitNet 연결)
    backend = MockBackend(LLMConfig())
    await backend.start()

    try:
        runner = ScenarioRunner(backend)
        result = await runner.run(loader.personas, "pension_age", progress=True)
    finally:
        await backend.stop()

    # 3. 요약 + 데모그래픽 분석
    print(render_text_report(result))

    # 4. 대시보드
    out = Path("results")
    out.mkdir(exist_ok=True)
    build_dashboard(result, out / "pension_age.html")
    print("\n→ results/pension_age.html (open in browser)")

    # 5. 핵심 인사이트
    summary = summarize(result)
    by_age = aggregate_by(result, "age_bucket")
    print("\n=== 핵심 인사이트 ===")
    print(f"전체: {summary.headline}")
    sorted_by_opp = sorted(by_age, key=lambda r: -r.opposed_pct)
    if sorted_by_opp:
        top = sorted_by_opp[0]
        print(f"가장 강하게 반대: {top.group} ({top.opposed_pct:.0f}% 반대, 평균 강도 {top.avg_intensity:.0f})")


if __name__ == "__main__":
    asyncio.run(main())
