"""United States locale — working stub built on US Census-inspired distributions.

This is a *stub* — it demonstrates that KoreaSim's pipeline generalizes beyond
Korea. The persona pool here is synthetic, not drawn from a real dataset
(unlike Korea, which uses Nemotron-Personas-Korea). To use this for serious
work, swap `generate_personas()` to read from a real persona/census dataset
(e.g. PUMS, Synthea, or any locale-appropriate equivalent).

What this file proves:
1. The `Locale` interface is real, not just documentation.
2. Adding a new country requires writing one ~150-LOC file plus prompt
   translations — not a re-architecture.
3. The downstream pipeline (LLM call, JSON parsing, aggregation, dashboard
   demographic groupings) is locale-agnostic.

What this file does NOT yet do:
- Sample from real US Census PUMS data
- Validate persona names against US Social Security Administration name lists
- Provide locale-tuned occupation × region distributions

Contributions welcome — see `docs/LOCALES.md`.
"""

from __future__ import annotations

import random
import uuid

from koreasim.locales.base import Locale, Persona

# --- US demographic skeleton (Census-inspired, simplified) ----------------------

# 50 states + DC, with weights ≈ 2024 ACS population shares (truncated to top 20
# for sample variety; remaining 31 share the residual uniformly).
_STATE_WEIGHTS = [
    ("California", 11.7),
    ("Texas", 9.0),
    ("Florida", 6.7),
    ("New York", 5.9),
    ("Pennsylvania", 3.9),
    ("Illinois", 3.8),
    ("Ohio", 3.5),
    ("Georgia", 3.3),
    ("North Carolina", 3.2),
    ("Michigan", 3.0),
    ("New Jersey", 2.8),
    ("Virginia", 2.6),
    ("Washington", 2.3),
    ("Arizona", 2.2),
    ("Massachusetts", 2.1),
    ("Tennessee", 2.0),
    ("Indiana", 2.0),
    ("Maryland", 1.9),
    ("Missouri", 1.9),
    ("Wisconsin", 1.8),
]
_REGIONS = [s for s, _ in _STATE_WEIGHTS] + [
    "Alabama", "Colorado", "South Carolina", "Minnesota", "Louisiana",
    "Kentucky", "Oregon", "Oklahoma", "Connecticut", "Utah",
    "Iowa", "Nevada", "Arkansas", "Mississippi", "Kansas",
    "New Mexico", "Nebraska", "Idaho", "West Virginia", "Hawaii",
    "New Hampshire", "Maine", "Montana", "Rhode Island", "Delaware",
    "South Dakota", "North Dakota", "Alaska", "Vermont", "Wyoming",
    "District of Columbia",
]

# Coarse age-band → likely occupation buckets (US Bureau of Labor Statistics-inspired).
_OCCUPATIONS_BY_AGE = {
    "teen": ["High school student", "Part-time retail worker"],
    "20s": ["Software engineer", "Registered nurse", "Marketing associate",
            "Graduate student", "Customer service rep", "Construction worker",
            "Restaurant server", "Elementary teacher"],
    "30s": ["Software engineer", "Project manager", "Physician", "Lawyer",
            "Accountant", "Entrepreneur", "Stay-at-home parent", "Police officer"],
    "40s": ["Senior engineer", "Sales director", "School principal", "Surgeon",
            "Real estate agent", "Operations manager", "Tradesperson (electrician/plumber)"],
    "50s": ["VP / Director", "Small business owner", "Farmer", "Pastor",
            "Veteran (retired military)", "Adjunct professor"],
    "60s": ["Retired", "Consultant", "Part-time worker", "Volunteer coordinator"],
    "70s+": ["Retired", "Volunteer", "Part-time hobbyist worker"],
}

# Top US first names from SSA 2020 + common surnames from US Census.
_FIRST_NAMES_M = [
    "Liam", "Noah", "Oliver", "Elijah", "James", "William", "Benjamin", "Lucas",
    "Henry", "Theodore", "Mason", "Michael", "Ethan", "Daniel", "Jacob",
]
_FIRST_NAMES_F = [
    "Olivia", "Emma", "Charlotte", "Amelia", "Ava", "Sophia", "Isabella",
    "Mia", "Evelyn", "Harper", "Luna", "Camila", "Gianna", "Elizabeth",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
]

_EDUCATION = [
    ("High school", 0.27),
    ("Some college", 0.15),
    ("Associate's degree", 0.10),
    ("Bachelor's degree", 0.25),
    ("Master's degree", 0.13),
    ("Doctorate / Professional", 0.10),
]


def _age_band(age: int) -> str:
    if age < 20:
        return "teen"
    if age < 30:
        return "20s"
    if age < 40:
        return "30s"
    if age < 50:
        return "40s"
    if age < 60:
        return "50s"
    if age < 70:
        return "60s"
    return "70s+"


def _weighted_choice(rng: random.Random, items: list[tuple[str, float]]) -> str:
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    cumulative = 0.0
    for item, weight in items:
        cumulative += weight
        if r <= cumulative:
            return item
    return items[-1][0]


def _sample_education(rng: random.Random) -> str:
    items = [(label, weight) for label, weight in _EDUCATION]
    return _weighted_choice(rng, items)


def _generate_one(rng: random.Random, idx: int) -> Persona:
    age = max(18, min(85, int(rng.gauss(42, 16))))
    band = _age_band(age)
    is_female = rng.random() < 0.51
    first = rng.choice(_FIRST_NAMES_F if is_female else _FIRST_NAMES_M)
    last = rng.choice(_LAST_NAMES)
    region = _weighted_choice(rng, _STATE_WEIGHTS)
    if rng.random() < 0.15:  # tail of less-populous states
        region = rng.choice(_REGIONS)
    occupation = rng.choice(_OCCUPATIONS_BY_AGE[band])
    education = _sample_education(rng)
    income_bracket = rng.choices(
        ["low", "mid", "high"], weights=[0.25, 0.55, 0.20]
    )[0]
    narrative = (
        f"{first} is a {age}-year-old {occupation.lower()} living in "
        f"{region}. Education: {education}. They follow current events "
        f"and have opinions shaped by their {band} life stage and "
        f"{income_bracket}-income perspective."
    )
    return Persona(
        persona_id=f"us-{idx:07d}-{uuid.uuid4().hex[:6]}",
        name=f"{first} {last}",
        age=age,
        region=region,
        gender="female" if is_female else "male",
        occupation=occupation,
        education=education,
        narrative=narrative,
        income_bracket=income_bracket,
        locale="en",
    )


# --- Locale class --------------------------------------------------------------

_REACTION_USER_PROMPT_EN = """Scenario: {scenario}

You are the persona described in your system prompt. React from THAT
person's specific perspective — age, region, occupation, life stage. Do not
hedge into a general statement.

Respond with ONLY a single JSON object, no preamble, no markdown fences:

{{
  "sentiment": "supportive" | "neutral" | "opposed",
  "intensity": <integer 0-100>,
  "reasoning": "<one or two sentences from your perspective, in English>"
}}

Rules:
- Choose the sentiment that best matches your honest gut reaction.
- If you have a real stake (positive or negative), pick supportive or opposed
  rather than neutral. "Neutral" is for genuine indifference, not safety.
- Keep reasoning grounded in your specific identity, not generic talking points.
"""

_SYSTEM_PROMPT_EN = """You are a US citizen. Answer ONLY from the perspective described below.

[Identity]
- Name: {name}
- Age: {age} ({gender})
- Lives in: {region}
- Occupation: {occupation}

[Background]
{narrative}

[Behavior]
- Stay in character. You are this specific person, not "the average American."
- Ground your reaction in your age, region, occupation, and life stage.
- Reply in conversational English — first person, honest gut reaction.
"""


class USLocale(Locale):
    language = "en"
    country = "US"
    display_name = "United States (Census-inspired stub — see docs/LOCALES.md)"

    def regions(self) -> list[str]:
        return list(_REGIONS)

    def generate_personas(self, count: int, seed: int | None = 42) -> list[Persona]:
        rng = random.Random(seed)
        return [_generate_one(rng, i) for i in range(count)]

    def system_prompt_template(self) -> str:
        return _SYSTEM_PROMPT_EN

    def reaction_user_prompt(self) -> str:
        return _REACTION_USER_PROMPT_EN


US_LOCALE = USLocale()
