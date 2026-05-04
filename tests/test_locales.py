"""Verify every registered Locale satisfies the protocol contract."""

from __future__ import annotations

import pytest

from koreasim.locales import LOCALES, get_locale
from koreasim.locales.base import Locale, Persona


@pytest.mark.parametrize("code", sorted(LOCALES.keys()))
class TestLocaleProtocol:
    def test_get_locale_returns_locale_instance(self, code: str) -> None:
        locale = get_locale(code)
        assert isinstance(locale, Locale)
        assert locale.country.isupper() and len(locale.country) == 2
        assert locale.language.islower() and len(locale.language) == 2
        assert locale.display_name

    def test_regions_nonempty_strings(self, code: str) -> None:
        regions = get_locale(code).regions()
        assert len(regions) >= 5, "expected at least 5 regions"
        assert all(isinstance(r, str) and r for r in regions)
        assert len(set(regions)) == len(regions), "regions should be unique"

    def test_generate_personas_basic(self, code: str) -> None:
        locale = get_locale(code)
        personas = locale.generate_personas(count=10, seed=0)
        assert len(personas) == 10
        for p in personas:
            assert isinstance(p, Persona)
            assert p.persona_id
            assert p.name
            assert isinstance(p.age, int) and 0 < p.age < 130
            assert p.region
            assert p.locale == locale.language

    def test_generate_personas_seed_reproducible(self, code: str) -> None:
        locale = get_locale(code)
        a = locale.generate_personas(count=5, seed=123)
        b = locale.generate_personas(count=5, seed=123)
        assert [p.name for p in a] == [p.name for p in b]
        assert [p.region for p in a] == [p.region for p in b]

    def test_system_prompt_has_required_placeholders(self, code: str) -> None:
        template = get_locale(code).system_prompt_template()
        for placeholder in ("{name}", "{age}", "{region}", "{occupation}", "{narrative}"):
            assert placeholder in template, (
                f"{code} system prompt missing {placeholder}"
            )

    def test_reaction_prompt_has_scenario_placeholder(self, code: str) -> None:
        assert "{scenario}" in get_locale(code).reaction_user_prompt()

    def test_personas_can_format_into_system_prompt(self, code: str) -> None:
        """End-to-end: a generated persona can fill the system prompt without errors."""
        locale = get_locale(code)
        personas = locale.generate_personas(count=3, seed=7)
        template = locale.system_prompt_template()
        for p in personas:
            rendered = template.format(
                name=p.name,
                age=p.age,
                gender=p.gender or "—",
                region=p.region,
                occupation=p.occupation or "—",
                narrative=p.narrative or "—",
            )
            assert p.name in rendered
            assert str(p.age) in rendered
            assert p.region in rendered


def test_unknown_locale_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="Unknown locale"):
        get_locale("zz")


def test_get_locale_case_insensitive() -> None:
    assert get_locale("KR") is get_locale("kr")
    assert get_locale("US") is get_locale("us")


def test_us_locale_personas_use_english_names() -> None:
    """Sanity check: US stub generates English-looking names."""
    from koreasim.locales import US_LOCALE
    personas = US_LOCALE.generate_personas(count=20, seed=42)
    # Heuristic: US names are ASCII-only.
    for p in personas:
        assert p.name.isascii(), f"US persona name should be ASCII: {p.name}"
        assert " " in p.name, f"expected first + last name: {p.name}"


def test_korea_locale_personas_use_korean_names() -> None:
    """Sanity check: Korea adapter passes through Korean names."""
    from koreasim.locales import KOREA_LOCALE
    personas = KOREA_LOCALE.generate_personas(count=20, seed=42)
    # Heuristic: at least one persona has a Hangul character in their name.
    has_hangul = any(any("가" <= ch <= "힣" for ch in p.name) for p in personas)
    assert has_hangul, "expected Korean (Hangul) names from KoreaLocale"
