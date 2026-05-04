"""Smoke tests for persona schema, sample generator, loader."""

from __future__ import annotations

from pathlib import Path

from koreasim.persona.loader import PersonaLoader
from koreasim.persona.sample import generate_sample_personas
from koreasim.persona.schema import REGIONS, KoreanPersona


def test_sample_personas_deterministic():
    a = generate_sample_personas(50, seed=42)
    b = generate_sample_personas(50, seed=42)
    assert len(a) == len(b) == 50
    assert [p.persona_id for p in a] == [p.persona_id for p in b]
    assert [p.name for p in a] == [p.name for p in b]


def test_sample_personas_distribution():
    personas = generate_sample_personas(500, seed=42)
    # All regions should be in the official list.
    for p in personas:
        assert p.region in REGIONS
        assert p.gender in ("남성", "여성")
        assert 15 <= p.age <= 80


def test_persona_system_prompt_contains_identity():
    p = KoreanPersona(
        persona_id="test-1",
        name="홍길동",
        age=42,
        gender="남성",
        region="서울특별시",
        occupation="소프트웨어 개발자",
        narrative="테스트용 페르소나입니다.",
    )
    sp = p.to_system_prompt()
    assert "홍길동" in sp
    assert "42세" in sp
    assert "서울특별시" in sp
    assert "한국어 존댓말" in sp


def test_persona_age_bucket():
    cases = [(15, "10대"), (25, "20대"), (35, "30대"), (45, "40대"),
             (55, "50대"), (65, "60대"), (75, "70대+")]
    for age, expected in cases:
        p = KoreanPersona(persona_id="x", name="x", age=age, gender="남성", region="서울특별시")
        assert p.age_bucket() == expected


def test_persona_occupation_group():
    cases = [
        ("소프트웨어 개발자", "IT/엔지니어"),
        ("의사", "의료직"),
        ("교사", "교육직"),
        ("공무원", "공무원"),
        ("자영업 사장", "자영업/사업"),
        ("농업인", "농수축산업"),
        ("전업주부", "전업주부"),
        ("퇴직자", "무직/은퇴"),
        ("회사원 (부장)", "사무/기타"),
    ]
    for occ, expected in cases:
        p = KoreanPersona(persona_id="x", name="x", age=40, gender="남성",
                          region="서울특별시", occupation=occ)
        assert p.occupation_group() == expected


def test_persona_loader_sample():
    loader = PersonaLoader.sample(count=30)
    assert len(loader) == 30
    assert all(isinstance(p, KoreanPersona) for p in loader.personas)


def test_persona_loader_filter():
    loader = PersonaLoader.sample(count=200, seed=42)
    seoul = loader.filter(regions=["서울특별시"])
    assert len(seoul) > 0
    assert all(p.region == "서울특별시" for p in seoul.personas)

    young_male = loader.filter(age_max=29, genders=["남성"])
    assert all(p.age <= 29 and p.gender == "남성" for p in young_male.personas)


def test_persona_loader_stratified_sample():
    loader = PersonaLoader.sample(count=200, seed=42)
    sub = loader.stratified_sample(20, by="age_bucket")
    assert 1 <= len(sub) <= 25  # Allow rounding wiggle


def test_persona_loader_jsonl_roundtrip(tmp_path: Path):
    loader = PersonaLoader.sample(count=20)
    path = tmp_path / "p.jsonl"
    loader.to_jsonl(path)
    reloaded = PersonaLoader.from_jsonl(path)
    assert len(reloaded) == 20
    assert reloaded.personas[0].name == loader.personas[0].name


def test_persona_from_dict_tolerates_extra_fields():
    data = {
        "persona_id": "x",
        "name": "테스트",
        "age": 30,
        "gender": "여성",
        "region": "부산광역시",
        "extra_unknown_field": "ignored",
    }
    p = KoreanPersona.from_dict(data)
    assert p.name == "테스트"
    assert p.region == "부산광역시"
