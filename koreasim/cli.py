"""koreasim CLI — `koreasim run`, `koreasim demo`, `koreasim list-scenarios`."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import click

from koreasim.analysis.aggregate import aggregate_by, summarize
from koreasim.analysis.compute import receipt_for_run
from koreasim.llm.backend import LLMConfig, MockBackend, OpenAICompatibleBackend
from koreasim.llm.models import DEFAULT_PRESET, PRESETS, resolve_model
from koreasim.persona.loader import PersonaLoader, load_personas
from koreasim.scenario.article import (
    ArticleExtractionError,
    ArticleFetchError,
    fetch_article,
)
from koreasim.scenario.brief import BriefGenerationError, generate_brief
from koreasim.scenario.prompts import SCENARIO_TEMPLATES
from koreasim.scenario.runner import ScenarioRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@click.group()
@click.version_option(package_name="koreasim")
def main():
    """🇰🇷 KoreaSim — Demographically-grounded Korean society simulator."""


@main.command(name="list-scenarios")
def list_scenarios():
    """List built-in scenario templates."""
    click.echo("Built-in scenarios:\n")
    for key, text in SCENARIO_TEMPLATES.items():
        click.echo(f"  {click.style(key, fg='cyan', bold=True):>20s}")
        click.echo(f"    {text}\n")


@main.command(name="list-models")
def list_models():
    """List built-in model presets (Qwen3 8B default + 1.58-bit BitNet variants)."""
    click.echo("Model presets:\n")
    for key, p in PRESETS.items():
        marker = " (default)" if key == DEFAULT_PRESET else ""
        click.echo(f"  {click.style(key, fg='cyan', bold=True):>20s}{marker}")
        click.echo(f"    {p.display_name}")
        click.echo(f"    HF id: {p.model_id}")
        click.echo(f"    {p.params_b:.1f}B params · ~{p.weight_size_gb:.1f}GB · {p.license}")
        click.echo(f"    {p.notes}\n")
    click.echo("Or pass any HuggingFace id directly: --model org/model-name")


@main.command()
@click.argument("scenario", required=False)
@click.option("--url", "article_url", default=None,
              help="Korean news article URL — fetched, summarised, and used as the scenario.")
@click.option("--n", "n_personas", default=1000, type=int, help="Number of personas (default 1000).")
@click.option("--source", default="sample", help="'sample' | 'huggingface' | path to .jsonl")
@click.option("--llm-url", default="http://127.0.0.1:11434", help="OpenAI-compatible endpoint (Ollama default).")
@click.option("--model", "llm_model", default=DEFAULT_PRESET,
              help=f"Model preset ({'/'.join(PRESETS)}) or explicit HF/Ollama id. Default: {DEFAULT_PRESET}.")
@click.option("--api-key", envvar="OPENAI_API_KEY", default=None, help="Optional bearer token.")
@click.option("--mock", is_flag=True, help="Use deterministic mock LLM (no server needed).")
@click.option("--out", "out_dir", default="results", help="Output directory.")
@click.option("--temperature", default=0.9, type=float)
@click.option("--no-dashboard", is_flag=True, help="Skip HTML dashboard rendering.")
@click.option("--no-card", is_flag=True, help="Skip social card PNG rendering.")
def run(scenario, article_url, n_personas, source, llm_url, llm_model, api_key,
        mock, out_dir, temperature, no_dashboard, no_card):
    """Run a scenario across N Korean personas.

    \b
    SCENARIO can be a built-in template key or a free-form Korean sentence.
    Or pass --url <기사 URL> to summarise a real article into the scenario.
    Examples:
        koreasim run pension_age --n 10000 --model llama3-8b
        koreasim run "내년부터 자동차 보험료가 30% 인상됩니다" --n 5000 --mock
        koreasim run --url https://n.news.naver.com/article/<id> --n 1000
        koreasim list-models   # see available 1.58-bit presets
    """
    if scenario and article_url:
        raise click.UsageError("scenario와 --url은 동시에 사용할 수 없습니다.")
    if not scenario and not article_url:
        raise click.UsageError("scenario 또는 --url 중 하나는 필수입니다.")

    asyncio.run(
        _run_scenario(
            scenario, article_url, n_personas, source, llm_url, llm_model, api_key, mock,
            Path(out_dir), temperature, no_dashboard, no_card,
        )
    )


@main.command()
@click.option("--n", "n_personas", default=300, type=int, help="Number of personas (default 300).")
@click.option("--scenario", default="pension_age", help="Built-in scenario key.")
@click.option("--llm-url", default="http://127.0.0.1:11434", help="OpenAI-compatible endpoint (Ollama default).")
@click.option("--model", "llm_model", default=DEFAULT_PRESET,
              help=f"Model preset ({'/'.join(PRESETS)}) or explicit id. Default: {DEFAULT_PRESET}.")
@click.option("--mock", is_flag=True, help="Use deterministic mock LLM (no server needed).")
@click.option("--out", "out_dir", default="results", help="Output directory.")
def demo(n_personas, scenario, llm_url, llm_model, mock, out_dir):
    """Run a real demo against an Ollama / OpenAI-compatible server.

    Defaults to Qwen3 8B (Q4_K_M) via Ollama at :11434. Override with --model
    for any preset (`bitnet-2b`, `llama3-8b`, ...) or explicit id. Use --mock
    for an offline templated run when no server is available.
    """
    asyncio.run(
        _run_scenario(
            scenario=scenario,
            article_url=None,
            n_personas=n_personas,
            source="sample",
            llm_url=llm_url,
            llm_model=llm_model,
            api_key=None,
            mock=mock,
            out_dir=Path(out_dir),
            temperature=0.7,
            no_dashboard=False,
            no_card=False,
        )
    )


async def _run_scenario(
    scenario, article_url, n_personas, source, llm_url, llm_model, api_key, mock,
    out_dir: Path, temperature, no_dashboard, no_card,
):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve model preset → real HF id (or pass-through if already an HF id).
    model_id, preset = resolve_model(llm_model)
    if preset:
        click.echo(f"📦 Model: {click.style(preset.label(), fg='magenta')}")
    else:
        click.echo(f"📦 Model: {click.style(model_id, fg='magenta')} (custom)")

    click.echo(f"🇰🇷 Loading {n_personas:,} personas from '{source}'...")
    if source in ("sample", "huggingface"):
        loader = load_personas(source=source, count=n_personas)
    else:
        loader = PersonaLoader.from_jsonl(source)
        if len(loader) > n_personas:
            loader = loader.stratified_sample(n_personas, by="region")
    click.echo(f"   → {len(loader):,} personas ready")

    # n_parallel=4 matches Ollama's default GPU concurrency. Higher values
    # (e.g. 16) cause Ollama to truncate responses under contention, leaving
    # most reactions empty.
    # max_tokens=800 — Korean prompts + the new stake-elicitation reasoning
    # need ~500-600 tokens; 600 truncated ~20% of responses.
    # min_p=0.03 + temperature=0.9 break Qwen3's "always neutral" RLHF
    # attractor (drops mean neutral 64% → 51%, see docs/SAMPLING.md).
    config = LLMConfig(
        base_url=llm_url, model=model_id, api_key=api_key,
        temperature=temperature, top_p=0.95, min_p=0.03,
        n_parallel=4, max_tokens=800,
    )
    backend = MockBackend(config) if mock else OpenAICompatibleBackend(config)
    await backend.start()

    source_url: str | None = None
    brief_dict: dict | None = None
    slug_seed = scenario or "scenario"

    try:
        # ----- URL mode: fetch article + generate brief, replacing scenario text -----
        if article_url:
            click.echo(f"📰 기사 fetch: {article_url}")
            try:
                article = await fetch_article(article_url)
            except (ArticleFetchError, ArticleExtractionError) as e:
                click.echo(click.style(f"   ✗ 기사 fetch 실패: {e}", fg="red"), err=True)
                return
            click.echo(f"   → {len(article.text):,}자 추출"
                       + (f" (제목: {article.title})" if article.title else ""))
            click.echo("🧠 Brief 생성 중...")
            try:
                brief = await generate_brief(backend, article)
            except BriefGenerationError as e:
                click.echo(click.style(f"   ✗ Brief 생성 실패: {e}", fg="red"), err=True)
                return
            if brief.unverified:
                click.echo(click.style(
                    f"   ! 검증 실패 항목 {len(brief.unverified)}개 (드롭됨)",
                    fg="yellow",
                ))
            scenario_text = brief.summary
            source_url = article_url
            brief_dict = brief.to_dict()
            slug_seed = _url_slug(article_url, article.title)
            click.echo(f"   → brief summary ({len(scenario_text)}자)")
        else:
            scenario_text = scenario

        runner = ScenarioRunner(backend, temperature=temperature, max_tokens=800)
        click.echo(f"🚀 Simulating: {ScenarioRunner.resolve_scenario(scenario_text)[:80]}...")
        result = await runner.run(
            loader.personas, scenario_text, progress=True,
            source_url=source_url, brief=brief_dict,
        )
    finally:
        await backend.stop()

    receipt = receipt_for_run(result.n, result.elapsed_s)

    click.echo(
        f"   → {result.n:,} reactions in {result.elapsed_s:.1f}s "
        f"({receipt.agents_per_sec:.0f} agents/sec, {result.n_failed:,} failed)"
    )

    summary = summarize(result)
    click.echo("")
    click.echo(click.style(summary.headline, fg="cyan", bold=True))

    # ----- Persist -----
    json_path = out_dir / f"{_slug(slug_seed)}.json"
    result.save_json(str(json_path))
    click.echo(f"   ✓ JSON: {json_path}")

    summary_path = out_dir / f"{_slug(slug_seed)}.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "summary": summary.to_dict(),
                "receipt": receipt.to_dict(),
                "by_age": [r.to_dict() for r in aggregate_by(result, "age_bucket")],
                "by_region": [r.to_dict() for r in aggregate_by(result, "region")],
                "by_occupation": [r.to_dict() for r in aggregate_by(result, "occupation_group")],
                "by_political": [r.to_dict() for r in aggregate_by(result, "political_lean")],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    click.echo(f"   ✓ Aggregates: {summary_path}")

    # ----- Text report -----
    from koreasim.viz.dashboard import render_text_report
    click.echo("\n" + render_text_report(result, receipt=receipt))

    # ----- Dashboard -----
    if not no_dashboard:
        try:
            from koreasim.viz.dashboard import build_dashboard
            html_path = out_dir / f"{_slug(slug_seed)}.html"
            build_dashboard(result, html_path, receipt=receipt, model=preset)
            click.echo(f"   ✓ Dashboard: {html_path}")
        except ImportError as e:
            click.echo(f"   ! Dashboard skipped — {e}", err=True)

    # ----- Social card PNG (for X / OG) -----
    if not no_card:
        try:
            from koreasim.viz.social_card import build_social_card
            png_path = out_dir / f"{_slug(slug_seed)}.card.png"
            build_social_card(result, png_path, receipt=receipt, model=preset)
            click.echo(f"   ✓ Social card: {png_path}  ({_pretty_size(png_path)})")
        except Exception as e:
            click.echo(f"   ! Social card skipped — {e}", err=True)


def _slug(s: str) -> str:
    keep = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    s2 = "".join(c if c in keep else "-" for c in s)[:60].strip("-")
    return s2 or "scenario"


def _url_slug(url: str, title: str | None) -> str:
    """Filesystem-friendly slug from host/path. Korean titles get mangled by
    `_slug()` (which only keeps ASCII), so we always derive from the URL."""
    from urllib.parse import urlparse

    del title  # intentionally unused — host/path is more stable for filenames
    parsed = urlparse(url)
    host = parsed.netloc.replace("www.", "")
    path_tail = parsed.path.rstrip("/").split("/")[-1] or parsed.path.replace("/", "-")
    return f"{host}-{path_tail}".strip("-") or "article"


def _pretty_size(p: Path) -> str:
    if not p.exists():
        return "?"
    n = p.stat().st_size
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}KB"
    return f"{n / (1024 * 1024):.1f}MB"


if __name__ == "__main__":
    main()
