"""PersonaLoader — load personas from Nemotron-Personas-Korea or local samples.

Three supported sources:
1.  `from_huggingface()` — streams from `nvidia/Nemotron-Personas-Korea` (requires `datasets`).
2.  `from_jsonl(path)`   — load a local JSONL dump (offline, reproducible).
3.  `sample(n)`          — synthetic offline demo personas (no download).
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Iterable
from pathlib import Path

from koreasim.persona.sample import generate_sample_personas
from koreasim.persona.schema import KoreanPersona

logger = logging.getLogger(__name__)

DATASET_NAME = "nvidia/Nemotron-Personas-Korea"


class PersonaLoader:
    """Lazy loader for Korean personas with simple filtering."""

    def __init__(self, personas: list[KoreanPersona]):
        self.personas = personas

    def __len__(self) -> int:
        return len(self.personas)

    def __iter__(self):
        return iter(self.personas)

    # ----- Constructors -----

    @classmethod
    def sample(cls, count: int = 100, seed: int | None = 42) -> PersonaLoader:
        """Built-in synthetic sample — no download. Good for demos / CI."""
        return cls(generate_sample_personas(count=count, seed=seed))

    @classmethod
    def from_jsonl(cls, path: str | Path) -> PersonaLoader:
        """Load from a previously dumped JSONL (one persona per line)."""
        path = Path(path)
        personas: list[KoreanPersona] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                personas.append(KoreanPersona.from_dict(json.loads(line)))
        logger.info("Loaded %d personas from %s", len(personas), path)
        return cls(personas)

    @classmethod
    def from_huggingface(
        cls,
        count: int | None = 1000,
        split: str = "train",
        streaming: bool = True,
        seed: int | None = 42,
    ) -> PersonaLoader:
        """Load real Nemotron-Personas-Korea rows. Requires `datasets`.

        Args:
            count: Number of rows to take. None = full dataset (large!).
            split: Dataset split.
            streaming: Stream rows instead of materializing in RAM.
            seed: Sampling seed when shuffling for `count`.

        Raises:
            ImportError: if `datasets` is not installed (`pip install koreasim[data]`).
        """
        try:
            from datasets import load_dataset  # type: ignore
        except ImportError as e:
            raise ImportError(
                "Loading from HuggingFace requires the optional `datasets` extra. "
                "Install with `pip install koreasim[data]`."
            ) from e

        ds = load_dataset(DATASET_NAME, split=split, streaming=streaming)
        if seed is not None and not streaming:
            ds = ds.shuffle(seed=seed)

        personas: list[KoreanPersona] = []
        rng = random.Random(seed)
        for i, row in enumerate(ds):
            if count is not None and len(personas) >= count:
                break
            try:
                personas.append(_row_to_persona(row, idx=i, rng=rng))
            except Exception as exc:  # row schema drifts happen — keep going
                logger.debug("Skipping malformed row %d: %s", i, exc)
        logger.info("Loaded %d personas from %s", len(personas), DATASET_NAME)
        return cls(personas)

    # ----- Filtering -----

    def filter(
        self,
        *,
        regions: Iterable[str] | None = None,
        age_min: int | None = None,
        age_max: int | None = None,
        genders: Iterable[str] | None = None,
        occupation_contains: Iterable[str] | None = None,
        life_stages: Iterable[str] | None = None,
    ) -> PersonaLoader:
        """Return a new PersonaLoader with rows matching all given filters."""
        regions_set = set(regions) if regions else None
        genders_set = set(genders) if genders else None
        life_stages_set = set(life_stages) if life_stages else None
        occ_terms = list(occupation_contains) if occupation_contains else None

        def keep(p: KoreanPersona) -> bool:
            if regions_set and p.region not in regions_set:
                return False
            if genders_set and p.gender not in genders_set:
                return False
            if life_stages_set and p.life_stage not in life_stages_set:
                return False
            if age_min is not None and p.age < age_min:
                return False
            if age_max is not None and p.age > age_max:
                return False
            if occ_terms and not any(t in p.occupation for t in occ_terms):
                return False
            return True

        return PersonaLoader([p for p in self.personas if keep(p)])

    def stratified_sample(
        self,
        n: int,
        by: str = "region",
        seed: int | None = 42,
    ) -> PersonaLoader:
        """Stratified down-sample to roughly `n` rows, balanced across `by`."""
        rng = random.Random(seed)
        groups: dict[str, list[KoreanPersona]] = {}
        for p in self.personas:
            key = getattr(p, by, None) if hasattr(p, by) else p.age_bucket()
            key = key or "unknown"
            groups.setdefault(str(key), []).append(p)

        per_group = max(1, n // max(len(groups), 1))
        out: list[KoreanPersona] = []
        for ps in groups.values():
            rng.shuffle(ps)
            out.extend(ps[:per_group])
        rng.shuffle(out)
        return PersonaLoader(out[:n])

    # ----- Persistence -----

    def to_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for p in self.personas:
                f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
        logger.info("Wrote %d personas to %s", len(self.personas), path)


def load_personas(
    source: str = "sample",
    count: int = 100,
    **kwargs,
) -> PersonaLoader:
    """Convenience entry-point.

    Args:
        source: "sample" | "huggingface" | path to .jsonl
        count: max personas to load
        **kwargs: forwarded to the underlying loader
    """
    if source == "sample":
        return PersonaLoader.sample(count=count, **kwargs)
    if source == "huggingface":
        return PersonaLoader.from_huggingface(count=count, **kwargs)
    return PersonaLoader.from_jsonl(source)


# ----- HF row → KoreanPersona ---------------------------------------------------

# The Nemotron-Personas-Korea schema has 26 fields — these are the ones we map.
# Keys we look for, in order of preference. We're tolerant because field names
# may evolve across releases.
_FIELD_ALIASES = {
    "name": ["name", "full_name", "korean_name"],
    "age": ["age"],
    "gender": ["gender", "sex"],
    "region": ["region", "metro_area", "province"],
    "district": ["district", "city", "municipality"],
    "occupation": ["occupation", "job", "profession"],
    "education": ["education", "education_level"],
    "marital_status": ["marital_status", "marriage_status"],
    "life_stage": ["life_stage", "stage"],
    "narrative": [
        "professional_persona", "family_persona", "concise_persona",
        "sports_persona", "arts_persona", "travel_persona", "culinary_persona",
        "persona", "narrative", "description",
    ],
    "persona_type": ["persona_type", "type"],
    "skills": ["skills", "skill_set"],
    "interests": ["interests", "hobbies"],
}


def _first(row: dict, keys: list[str], default=None):
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return default


def _row_to_persona(row: dict, *, idx: int, rng: random.Random) -> KoreanPersona:
    name = _first(row, _FIELD_ALIASES["name"], default="익명")
    age = int(_first(row, _FIELD_ALIASES["age"], default=35))
    gender_raw = str(_first(row, _FIELD_ALIASES["gender"], default="남성"))
    gender = "여성" if gender_raw.lower() in ("female", "f", "여성", "여") else "남성"

    region = str(_first(row, _FIELD_ALIASES["region"], default="서울특별시"))
    district = str(_first(row, _FIELD_ALIASES["district"], default=""))
    occupation = str(_first(row, _FIELD_ALIASES["occupation"], default="무직"))
    education = str(_first(row, _FIELD_ALIASES["education"], default=""))
    marital = str(_first(row, _FIELD_ALIASES["marital_status"], default=""))
    life_stage = str(_first(row, _FIELD_ALIASES["life_stage"], default="취업"))

    skills = row.get("skills") or row.get("skill_set") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]
    interests = row.get("interests") or row.get("hobbies") or []
    if isinstance(interests, str):
        interests = [s.strip() for s in interests.split(",") if s.strip()]

    # The 7 persona narrative columns share the same row — pick the populated one
    # at random so we get diverse persona types per agent.
    narrative_candidates = [
        ("professional", row.get("professional_persona")),
        ("family", row.get("family_persona")),
        ("sports", row.get("sports_persona")),
        ("arts", row.get("arts_persona")),
        ("travel", row.get("travel_persona")),
        ("culinary", row.get("culinary_persona")),
        ("concise", row.get("concise_persona")),
    ]
    populated = [(t, n) for t, n in narrative_candidates if n]
    if populated:
        ptype, narrative = rng.choice(populated)
    else:
        ptype = str(_first(row, _FIELD_ALIASES["persona_type"], default="concise"))
        narrative = str(_first(row, _FIELD_ALIASES["narrative"], default=""))

    return KoreanPersona(
        persona_id=str(row.get("id", row.get("persona_id", f"hf-{idx:07d}"))),
        name=name,
        age=age,
        gender=gender,
        region=region,
        district=district,
        occupation=occupation,
        education=education,
        marital_status=marital,
        life_stage=life_stage,
        skills=list(skills) if skills else [],
        interests=list(interests) if interests else [],
        persona_type=ptype,
        narrative=str(narrative or ""),
    )
