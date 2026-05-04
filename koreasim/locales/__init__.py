"""Locale registry for KoreaSim.

KoreaSim's pipeline (persona sampling → prompt rendering → LLM fan-out →
demographic aggregation) is locale-agnostic. Only the *content* — regions,
demographic distributions, prompt language — is locale-specific.

Two locales currently shipped:

- `KOREA_LOCALE` (`koreasim.locales.kr`) — the real implementation, backed
  by Nemotron-Personas-Korea + KOSIS distributions + Korean prompts. This is
  what the rest of KoreaSim (CLI, dashboard, examples) uses by default.

- `US_LOCALE` (`koreasim.locales.us`) — a working stub demonstrating that
  the architecture generalizes. Persona pool is synthetic Census-inspired,
  not drawn from a real dataset. Treat as a starting point for adding a
  proper locale, not as a finished product.

To add another locale, see `docs/LOCALES.md`.
"""

from __future__ import annotations

from koreasim.locales.base import Locale, Persona
from koreasim.locales.kr import KOREA_LOCALE, KoreaLocale
from koreasim.locales.us import US_LOCALE, USLocale

# Registry for `--locale <name>` CLI lookups (lowercase ISO 3166-1 alpha-2).
LOCALES: dict[str, Locale] = {
    "kr": KOREA_LOCALE,
    "us": US_LOCALE,
}


def get_locale(name: str) -> Locale:
    """Look up a locale by ISO 3166-1 alpha-2 code (case-insensitive)."""
    key = name.lower()
    if key not in LOCALES:
        available = ", ".join(sorted(LOCALES.keys()))
        raise KeyError(f"Unknown locale '{name}'. Available: {available}")
    return LOCALES[key]


__all__ = [
    "LOCALES",
    "Locale",
    "Persona",
    "KoreaLocale",
    "USLocale",
    "KOREA_LOCALE",
    "US_LOCALE",
    "get_locale",
]
