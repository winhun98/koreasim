"""Locale abstraction — extension point for non-Korean simulations.

KoreaSim's *pipeline* is locale-agnostic: persona sampling → prompt rendering
→ async LLM fan-out → demographic aggregation. Only the *content* (regions,
demographic distributions, prompt language) is locale-specific.

To add a new locale:

1. Subclass `Persona` with locale-specific fields if needed (or use as-is).
2. Subclass `Locale` and implement the four required methods.
3. Optionally register in `koreasim.locales.__init__` for `--locale <name>`.

See `koreasim/locales/us.py` for a working stub and `docs/LOCALES.md` for
the full extension guide.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class Persona:
    """Universal persona fields. Locales may subclass to add locale-specific data.

    Only `persona_id`, `name`, `age`, and `region` are required. Everything
    else has a sensible default so that locales can fill in what they have.
    """

    persona_id: str
    name: str
    age: int
    region: str
    gender: str = ""
    occupation: str = ""
    education: str = ""
    narrative: str = ""
    income_bracket: Literal["low", "mid", "high"] = "mid"
    locale: str = "xx"  # ISO 639-1 lowercase, e.g. "ko", "en"
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Locale(ABC):
    """Locale = (regions, persona generator, prompt language).

    A locale fully describes how to sample demographically-grounded personas
    for one country/region/language. Pipelines downstream (prompts, runner,
    aggregation) read from this interface and never assume Korea.
    """

    #: ISO 639-1 lowercase language code (e.g. "ko", "en", "ja").
    language: str = "xx"

    #: ISO 3166-1 alpha-2 country code (e.g. "KR", "US", "JP").
    country: str = "XX"

    #: Human-readable name for CLI listings.
    display_name: str = "Unknown"

    @abstractmethod
    def regions(self) -> list[str]:
        """Return the canonical list of administrative regions for this locale."""

    @abstractmethod
    def generate_personas(self, count: int, seed: int | None = 42) -> list[Persona]:
        """Synthesize `count` demographically-grounded personas for this locale.

        Implementations should match the locale's actual demographic
        distributions (age, region, occupation) to the extent possible. Used
        for offline demos and tests; production should use real datasets via
        each locale's own loader (e.g. `from_huggingface()` for KR).
        """

    @abstractmethod
    def system_prompt_template(self) -> str:
        """Return the system prompt template for this locale, in its language.

        Must include placeholders for persona fields (`{name}`, `{age}`,
        `{region}`, `{occupation}`, `{narrative}`). The runner formats this
        per persona before each call.
        """

    @abstractmethod
    def reaction_user_prompt(self) -> str:
        """Return the per-call user prompt template (scenario → JSON reaction).

        Must include a `{scenario}` placeholder. JSON shape must match the
        Reaction schema: {sentiment, intensity, reasoning}.
        """

    def __repr__(self) -> str:
        return f"<Locale {self.country}/{self.language} {self.display_name}>"
