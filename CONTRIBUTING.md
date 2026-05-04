# Contributing to KoreaSim

Thanks for taking interest. KoreaSim is small enough that contributions land
fast — the bar is "does it pass the tests, does the dashboard still look right,
and does it stay laptop-runnable?"

## Quick setup

```bash
git clone https://github.com/winhun98/koreasim.git
cd koreasim
python -m venv .venv && source .venv/bin/activate
pip install -e ".[viz]" pytest pytest-asyncio pytest-httpx ruff
```

## Running checks before you push

```bash
pytest                       # 41+ tests, all should pass
ruff check koreasim/ tests/  # lint must be clean
```

CI runs the same two commands across Python 3.10 / 3.11 / 3.12 — see
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Code conventions

- `from __future__ import annotations` at the top of every file.
- Korean strings for user-facing text and existing `REACTION_USER_PROMPT`s.
  **New LLM prompts** (system / user instructions) go in **English** —
  Korean stays for the data and the model's output.
- Type hints on public functions. We don't run mypy in CI (yet) but the
  hints are read by humans.
- Comments explain *why*, not *what*. The code says what it does. Keep
  comments to non-obvious invariants, hidden constraints, or recorded
  rationale ("this temperature was tuned because...").
- Don't add error handling for cases that can't happen. Trust the caller.
  Validate at user-facing boundaries (CLI args, URL fetch, LLM responses).

## What's a good first PR?

- A new built-in scenario (`koreasim/scenario/prompts.py:SCENARIO_TEMPLATES`).
- A new model preset (`koreasim/llm/models.py:PRESETS`).
- An additional persona aggregation axis (`koreasim/analysis/aggregate.py`).
- More Korean news outlet support — `trafilatura` already handles the major
  ones, but if a paywall / non-standard layout breaks fetching, a focused
  fix in `koreasim/scenario/article.py` is welcome.

## What needs discussion before you start

- Persona schema changes (`koreasim/persona/schema.py`) — these break saved
  JSONs.
- Dashboard layout (`koreasim/viz/dashboard.py`) — open an issue with a
  mockup first.
- New runtime dependencies — keep the laptop-runnable promise honest.

## Issue / PR etiquette

- Issues: include the command you ran, what you expected, what happened,
  and your `koreasim --version` + Python version.
- PRs: link to the issue, include a one-line "what changed and why",
  and update the [CHANGELOG.md](CHANGELOG.md) under `[Unreleased]`.

## License

Apache 2.0. By contributing, you agree your contributions are licensed under
the same terms.
