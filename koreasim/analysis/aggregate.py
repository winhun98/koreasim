"""Aggregate `ScenarioResult` reactions into demographic group summaries."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from koreasim.persona.schema import KoreanPersona, Reaction
from koreasim.scenario.runner import ScenarioResult

GroupFn = Callable[[KoreanPersona], str]


GROUP_FUNCTIONS: dict[str, GroupFn] = {
    "region": lambda p: p.region,
    "age_bucket": lambda p: p.age_bucket(),
    "gender": lambda p: p.gender,
    "occupation_group": lambda p: p.occupation_group(),
    "life_stage": lambda p: p.life_stage,
    "income_bracket": lambda p: p.income_bracket,
    "political_lean": lambda p: p.political_lean,
}


@dataclass
class AggregateRow:
    """One row of an aggregate breakdown — pivoted around a single group key."""

    group: str
    n: int = 0
    supportive: int = 0
    neutral: int = 0
    opposed: int = 0
    avg_intensity: float = 0.0
    sample_quotes: list[str] = field(default_factory=list)

    @property
    def supportive_pct(self) -> float:
        return 100 * self.supportive / self.n if self.n else 0.0

    @property
    def opposed_pct(self) -> float:
        return 100 * self.opposed / self.n if self.n else 0.0

    @property
    def neutral_pct(self) -> float:
        return 100 * self.neutral / self.n if self.n else 0.0

    @property
    def net_score(self) -> float:
        """+100 = all supportive, -100 = all opposed, 0 = balanced."""
        if not self.n:
            return 0.0
        return 100 * (self.supportive - self.opposed) / self.n

    def to_dict(self) -> dict:
        return {
            "group": self.group,
            "n": self.n,
            "supportive": self.supportive,
            "neutral": self.neutral,
            "opposed": self.opposed,
            "supportive_pct": round(self.supportive_pct, 1),
            "neutral_pct": round(self.neutral_pct, 1),
            "opposed_pct": round(self.opposed_pct, 1),
            "avg_intensity": round(self.avg_intensity, 1),
            "net_score": round(self.net_score, 1),
            "sample_quotes": self.sample_quotes,
        }


@dataclass
class SentimentSummary:
    """Top-level summary of a scenario run."""

    n: int
    supportive_pct: float
    neutral_pct: float
    opposed_pct: float
    avg_intensity: float
    net_score: float
    headline: str

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "supportive_pct": round(self.supportive_pct, 1),
            "neutral_pct": round(self.neutral_pct, 1),
            "opposed_pct": round(self.opposed_pct, 1),
            "avg_intensity": round(self.avg_intensity, 1),
            "net_score": round(self.net_score, 1),
            "headline": self.headline,
        }


def aggregate_by(
    result: ScenarioResult,
    by: str = "age_bucket",
    *,
    max_quotes_per_group: int = 2,
) -> list[AggregateRow]:
    """Group reactions by a demographic key and compute per-group stats.

    `by` may be a key in `GROUP_FUNCTIONS` or a `KoreanPersona` attribute name.
    """
    group_fn = GROUP_FUNCTIONS.get(by)
    if group_fn is None:
        # Fallback: attribute lookup.
        def group_fn(p: KoreanPersona) -> str:  # noqa: D401
            return str(getattr(p, by, "unknown"))

    buckets: dict[str, list[Reaction]] = defaultdict(list)
    bucket_personas: dict[str, list[KoreanPersona]] = defaultdict(list)

    for reaction in result.reactions:
        persona = result.persona_for(reaction)
        if persona is None:
            continue
        key = group_fn(persona)
        buckets[key].append(reaction)
        bucket_personas[key].append(persona)

    rows: list[AggregateRow] = []
    for key, rs in buckets.items():
        sentiments = Counter(r.sentiment for r in rs)
        intensities = [r.intensity for r in rs]
        # Pull a few high-intensity quotes — most informative for the dashboard.
        sorted_rs = sorted(rs, key=lambda r: -r.intensity)
        quotes = [r.reasoning[:160] for r in sorted_rs[:max_quotes_per_group] if r.reasoning]

        rows.append(
            AggregateRow(
                group=key,
                n=len(rs),
                supportive=sentiments.get("supportive", 0),
                neutral=sentiments.get("neutral", 0),
                opposed=sentiments.get("opposed", 0),
                avg_intensity=sum(intensities) / len(intensities) if intensities else 0.0,
                sample_quotes=quotes,
            )
        )

    rows.sort(key=lambda r: -r.n)
    return rows


def summarize(result: ScenarioResult) -> SentimentSummary:
    """One-line summary: how does Korea (this sample) feel about the scenario?"""
    n = result.n
    if n == 0:
        return SentimentSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0, "응답 없음")

    sentiments = Counter(r.sentiment for r in result.reactions)
    sup = sentiments.get("supportive", 0)
    neu = sentiments.get("neutral", 0)
    opp = sentiments.get("opposed", 0)
    intensities = [r.intensity for r in result.reactions]
    avg_int = sum(intensities) / len(intensities)
    net = 100 * (sup - opp) / n

    headline = _headline(net, avg_int, sup, neu, opp, n)
    return SentimentSummary(
        n=n,
        supportive_pct=100 * sup / n,
        neutral_pct=100 * neu / n,
        opposed_pct=100 * opp / n,
        avg_intensity=avg_int,
        net_score=net,
        headline=headline,
    )


def _headline(net: float, avg_int: float, sup: int, neu: int, opp: int, n: int) -> str:
    if net > 30:
        tone = "대체로 긍정적"
    elif net < -30:
        tone = "대체로 부정적"
    elif abs(net) < 10:
        tone = "의견 분열"
    else:
        tone = "약한 경향" if net > 0 else "약한 반발"
    return (
        f"표본 {n}명 — {tone} (찬성 {100*sup/n:.0f}% / 중립 {100*neu/n:.0f}% / 반대 {100*opp/n:.0f}%, "
        f"평균 강도 {avg_int:.0f})"
    )
