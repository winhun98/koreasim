# Changelog

All notable changes to KoreaSim are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **URL input mode** (`koreasim run --url <기사 URL>`) — fetches a real
  Korean news article via `httpx` + `trafilatura`, generates a structured
  brief (행위자 · 조치 · 규모 · 대상 · 시점 · 범위 + key_numbers + quotes)
  via the same LLM backend, and runs N personas against the brief's summary.
- **Verbatim guard** for brief generation — every `key_numbers` and `quotes`
  item must appear verbatim in the source article (whitespace-tolerant).
  One automatic retry on failure; remaining unverified items are dropped
  and surfaced in the dashboard.
- **Disk cache** for fetched articles at `~/.cache/koreasim/articles/`
  (override with `KOREASIM_CACHE_DIR`).
- **Source attribution box** in the dashboard — clickable URL, structured
  brief slots panel (collapsible), and warning if any verbatim check failed.
- `source_url` and `brief` fields on `ScenarioResult` (default `None`,
  backward-compatible with v0.1.0 saved JSONs).
- Continuous Integration via GitHub Actions (`pytest` + `ruff` on Python
  3.10 / 3.11 / 3.12).
- `CONTRIBUTING.md`, `CHANGELOG.md`.

### Changed
- New LLM prompt convention: instructions in English, output in Korean.
  Existing `REACTION_USER_PROMPT` stays Korean for backward compatibility.
- `runner.py` uses `asyncio.get_running_loop()` (no more deprecated
  `get_event_loop()` inside coroutines).
- Module docstring on `llm/backend.py` now names Ollama as the default
  recommendation (was bitnet.cpp).
- `list-models` description rephrased — Qwen3 8B is the default; BitNet
  presets are listed alongside.

### Fixed
- Brief generation merges retried responses with the previous attempt so a
  thin retry doesn't blank out richer earlier slots (e.g. retried
  `key_numbers` correction wouldn't accidentally clear `actor` / `summary`).
- `BriefGenerationError` is now caught at the CLI layer with a clean error
  message instead of crashing.

## [0.1.0] — Initial commit

- Persona loader (Nemotron-Personas-Korea + offline KOSIS-style sample).
- `OpenAICompatibleBackend` for Ollama / bitnet.cpp / vLLM / NIM.
- `ScenarioRunner` with async-parallel generation, robust JSON parsing,
  rejection sampling.
- 5 built-in scenarios (`pension_age`, `housing_price`, `kospi_crash`,
  `minimum_wage`, `ai_replacement`).
- HTML dashboard with Korea province choropleth, emoji people wall,
  demographic stacked bars, and group quotes.
- 1200×630 social card PNG generator.
- Computation receipt (agents/sec, token throughput).
- 19 tests (persona loader, scenario runner, JSON parser).
