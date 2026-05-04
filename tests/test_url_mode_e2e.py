"""End-to-end tests for `koreasim run --url <URL>` mode."""

from __future__ import annotations

import json

from click.testing import CliRunner

from koreasim.cli import main

_ARTICLE_HTML = """<!doctype html>
<html lang="ko"><head><title>보험료 인상</title></head><body>
<article>
<h1>보험료 30% 인상 발표</h1>
<p>정부가 자동차 보험료를 내년 1월부터 평균 30% 인상한다고 발표했습니다.
운전자 1,200만 명이 영향을 받을 것으로 예상됩니다.
김모 운전자는 "부담이 너무 크다"며 반대 입장을 밝혔습니다.
전문가들은 손해율 상승을 그 배경으로 지목했습니다.
보험료 인상은 2026년 1월 1일부터 단계적으로 적용될 예정입니다.</p>
</article>
</body></html>"""


def test_cli_url_and_scenario_mutually_exclusive(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "run", "pension_age",
            "--url", "https://example.com/x",
            "--mock",
            "--out", str(tmp_path),
        ],
    )
    assert result.exit_code != 0


def test_cli_run_neither_scenario_nor_url(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--mock", "--out", str(tmp_path)])
    assert result.exit_code != 0


def test_cli_run_url_mode_end_to_end(httpx_mock, tmp_path, monkeypatch):
    """--url 모드 e2e: fetch → brief → simulate → JSON + HTML 저장 확인."""
    monkeypatch.setenv("KOREASIM_CACHE_DIR", str(tmp_path / "cache"))
    httpx_mock.add_response(url="https://example.com/news/1", text=_ARTICLE_HTML)

    out = tmp_path / "out"
    cli_runner = CliRunner()
    result = cli_runner.invoke(
        main,
        [
            "run",
            "--url", "https://example.com/news/1",
            "--n", "10",
            "--mock",
            "--out", str(out),
            "--no-card",
        ],
    )

    if result.exit_code != 0:
        # Surface any failure for debugging.
        raise AssertionError(
            f"CLI failed exit={result.exit_code}\n"
            f"output:\n{result.output}\n"
            f"exception: {result.exception}"
        )
    assert result.exit_code == 0

    # JSON output must include source_url and brief.
    json_files = [p for p in out.glob("*.json") if not p.name.endswith(".summary.json")]
    assert len(json_files) == 1, f"expected 1 main json, got {[p.name for p in out.glob('*.json')]}"
    data = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert data["source_url"] == "https://example.com/news/1"
    assert data["brief"] is not None
    assert "summary" in data["brief"]
    assert data["n"] == 10

    # Dashboard HTML must reference the source URL.
    html_files = list(out.glob("*.html"))
    assert len(html_files) == 1
    html = html_files[0].read_text(encoding="utf-8")
    assert "https://example.com/news/1" in html
