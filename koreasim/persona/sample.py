"""Synthetic sample personas for offline demos / CI.

Generates ~N personas with KOSIS-inspired demographic distributions so that
`koreasim demo` works out-of-the-box without a HuggingFace download.

For real research, use Nemotron-Personas-Korea via `PersonaLoader.from_huggingface()`.
The sample here is small (~100) and intentionally NOT a substitute.
"""

from __future__ import annotations

import random
from collections.abc import Iterator

from koreasim.persona.schema import KoreanPersona

# 광역시도 + KOSIS 2024 근사 인구 비중 (단순화)
_REGION_WEIGHTS = [
    ("서울특별시", 18.3),
    ("경기도", 26.2),
    ("부산광역시", 6.4),
    ("인천광역시", 5.9),
    ("경상남도", 6.3),
    ("경상북도", 5.0),
    ("대구광역시", 4.6),
    ("충청남도", 4.1),
    ("전라남도", 3.5),
    ("전북특별자치도", 3.4),
    ("충청북도", 3.1),
    ("강원특별자치도", 3.0),
    ("대전광역시", 2.8),
    ("광주광역시", 2.8),
    ("울산광역시", 2.2),
    ("제주특별자치도", 1.3),
    ("세종특별자치시", 0.7),
]

# 나이별 직업/생애단계 비중 (대략적)
_AGE_BUCKETS = [
    (15, 19, "학생"),
    (20, 29, "취업"),
    (30, 39, "취업"),
    (40, 49, "취업"),
    (50, 59, "취업"),
    (60, 69, "퇴직"),
    (70, 80, "퇴직"),
]

_OCCUPATIONS_BY_AGE = {
    "10대": ["고등학생", "대학생"],
    "20대": ["대학생", "소프트웨어 개발자", "간호사", "공무원", "사무직 직원", "디자이너", "영업사원", "학원 강사"],
    "30대": ["소프트웨어 개발자", "회계사", "마케터", "교사", "간호사", "의사", "자영업자", "공무원", "전업주부"],
    "40대": ["회사원 (부장)", "교사", "자영업자", "의사", "변호사", "공무원", "자영업 사장", "전업주부"],
    "50대": ["자영업 사장", "교장", "임원", "공무원", "농업인", "소상공인", "전업주부"],
    "60대": ["퇴직자", "농업인", "소상공인", "재취업 사무직", "전업주부"],
    "70대+": ["퇴직자", "농업인", "전업주부"],
}

_FAMILY_NAMES = [
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
    "한", "오", "서", "신", "권", "황", "안", "송", "전", "홍",
]
_GIVEN_NAMES_M = [
    "민준", "서준", "도윤", "예준", "시우", "주원", "하준", "지호", "지후", "준우",
    "건우", "현우", "도현", "지훈", "선우", "서진", "유준", "준호", "민재", "은우",
]
_GIVEN_NAMES_F = [
    "서연", "지우", "서윤", "하윤", "하은", "민서", "지유", "윤서", "지민", "채원",
    "수아", "지아", "예린", "시아", "예나", "서아", "은서", "다은", "유나", "유진",
]

_EDUCATION = [
    ("고등학교 졸업", 0.30),
    ("대학교 재학", 0.10),
    ("대학교 졸업", 0.45),
    ("대학원 석사", 0.10),
    ("대학원 박사", 0.05),
]

_PERSONA_NARRATIVES = {
    "professional": "업무에 몰입하며 커리어 성장에 가장 큰 관심을 둔다. 점심시간에도 업계 뉴스를 챙겨본다.",
    "family": "가족과 보내는 시간을 가장 소중히 여기며, 자녀 교육과 주거 안정에 민감하다.",
    "sports": "주말마다 등산이나 러닝을 즐기고, 건강과 자기관리에 관심이 많다.",
    "arts": "전시·공연·독서를 즐기며 새로운 문화 트렌드에 관심이 많다.",
    "travel": "1년에 두세 번 여행을 다녀오며, 다양한 지역 문화에 호기심이 많다.",
    "culinary": "요리와 맛집 탐방을 즐기며, 식재료의 원산지와 가격 변동에 민감하다.",
    "concise": "조용하고 실용적이며, 자신의 일상에 집중한다.",
}


def _weighted_choice(items: list[tuple[str, float]]) -> str:
    total = sum(w for _, w in items)
    r = random.random() * total
    acc = 0.0
    for value, weight in items:
        acc += weight
        if r <= acc:
            return value
    return items[-1][0]


def _pick_age() -> tuple[int, str, str]:
    """Returns (age, age_bucket, life_stage)."""
    bucket = random.choices(
        _AGE_BUCKETS,
        weights=[8, 14, 17, 18, 17, 14, 12],
    )[0]
    lo, hi, life = bucket
    age = random.randint(lo, hi)
    if age < 20:
        ab = "10대"
    elif age < 30:
        ab = "20대"
    elif age < 40:
        ab = "30대"
    elif age < 50:
        ab = "40대"
    elif age < 60:
        ab = "50대"
    elif age < 70:
        ab = "60대"
    else:
        ab = "70대+"
    return age, ab, life


def _income_bracket(age: int, occupation: str) -> str:
    """Heuristic income bracket from age + occupation."""
    if any(k in occupation for k in ("의사", "변호사", "임원", "교수")):
        return "high"
    if "학생" in occupation or "퇴직" in occupation or "주부" in occupation:
        return "low"
    if 30 <= age <= 55:
        return "mid"
    return "low" if age < 30 or age >= 60 else "mid"


def _political_lean(age: int, region: str) -> str:
    """Very rough heuristic — only for diversity in demo, not a serious model."""
    if age >= 60:
        return random.choices(["progressive", "moderate", "conservative"], [0.15, 0.30, 0.55])[0]
    if age < 30:
        return random.choices(["progressive", "moderate", "conservative"], [0.45, 0.40, 0.15])[0]
    if region in ("전라남도", "전북특별자치도", "광주광역시"):
        return random.choices(["progressive", "moderate", "conservative"], [0.50, 0.30, 0.20])[0]
    if region in ("경상북도", "경상남도", "대구광역시"):
        return random.choices(["progressive", "moderate", "conservative"], [0.20, 0.30, 0.50])[0]
    return random.choices(["progressive", "moderate", "conservative"], [0.30, 0.40, 0.30])[0]


def generate_sample_personas(
    count: int = 100,
    seed: int | None = 42,
) -> list[KoreanPersona]:
    """Generate `count` synthetic personas with rough KOSIS-inspired distributions.

    NOT a replacement for Nemotron-Personas-Korea — only for offline demo / tests.
    """
    rng = random.Random(seed) if seed is not None else random
    # Re-seed module-level random (used inside helpers) deterministically.
    if seed is not None:
        random.seed(seed)

    personas: list[KoreanPersona] = []
    for i in range(count):
        gender = rng.choice(["남성", "여성"])
        family = rng.choice(_FAMILY_NAMES)
        given = rng.choice(_GIVEN_NAMES_M if gender == "남성" else _GIVEN_NAMES_F)
        name = f"{family}{given}"

        age, ab, life = _pick_age()
        region = _weighted_choice([(r, w) for r, w in _REGION_WEIGHTS])
        occ = rng.choice(_OCCUPATIONS_BY_AGE[ab])
        edu = _weighted_choice(_EDUCATION)
        marital = (
            "미혼" if age < 30
            else rng.choices(["기혼", "미혼", "이혼"], [0.70, 0.22, 0.08])[0]
        )
        ptype = rng.choice(list(_PERSONA_NARRATIVES.keys()))

        personas.append(
            KoreanPersona(
                persona_id=f"sample-{i:04d}",
                name=name,
                age=age,
                gender=gender,
                region=region,
                district="",
                occupation=occ,
                education=edu,
                marital_status=marital,
                life_stage=life,
                skills=[],
                interests=[],
                persona_type=ptype,
                narrative=_PERSONA_NARRATIVES[ptype],
                income_bracket=_income_bracket(age, occ),
                political_lean=_political_lean(age, region),
            )
        )
    return personas


def stream_sample_personas(count: int = 100, seed: int | None = 42) -> Iterator[KoreanPersona]:
    """Streaming variant — yields one persona at a time."""
    yield from generate_sample_personas(count, seed)
