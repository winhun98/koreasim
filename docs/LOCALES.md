# Adding a Locale to KoreaSim

KoreaSim's pipeline is locale-agnostic. The default Korea path uses
[Nemotron-Personas-Korea](https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea)
+ KOSIS-weighted distributions + Korean prompts, but the abstractions in
`koreasim/locales/` let you swap in any other country.

This guide walks through adding a new locale end-to-end. As a reference, see
the existing implementations:

- `koreasim/locales/kr.py` — full implementation (real persona dataset)
- `koreasim/locales/us.py` — working stub (Census-inspired synthetic personas)

## What a Locale provides

A locale is a class subclassing `koreasim.locales.base.Locale` that fills in
four methods:

| Method | What it returns |
|---|---|
| `regions()` | Canonical list of administrative regions (states, provinces, prefectures, etc.) |
| `generate_personas(count, seed)` | A list of `Persona` objects, demographically distributed |
| `system_prompt_template()` | The persona system prompt template, in the locale's language |
| `reaction_user_prompt()` | The per-call prompt that asks for a JSON-shaped reaction |

Plus three class attributes:

| Attribute | Example |
|---|---|
| `language` | ISO 639-1 lowercase ("ko", "en", "ja", "zh", ...) |
| `country` | ISO 3166-1 alpha-2 uppercase ("KR", "US", "JP", "DE", ...) |
| `display_name` | Human-readable string for CLI listings |

## Step-by-step

### 1. Create `koreasim/locales/<cc>.py`

Use the country's ISO 3166-1 alpha-2 code in lowercase as the file name. e.g.
`jp.py` for Japan, `de.py` for Germany.

### 2. Define your `Persona` generator

Most locales can use the universal `Persona` dataclass directly. If you have
locale-specific fields (e.g. Japanese 都道府県 has a structured prefecture
hierarchy you want to preserve), put them under `Persona.extras`.

Distribution sources to consider:
- **Census/PUMS data** for accurate age × region × occupation joint distributions
- **Local SSA-equivalent name lists** for realistic names
- **National statistical office** for occupation × region patterns

If a real dataset is unavailable, ship a synthetic stub (like `us.py`) and
mark it as such in the docstring.

### 3. Translate the prompts

Two prompts must be translated:

**System prompt** — establishes persona identity. Must include placeholders
for `{name}`, `{age}`, `{gender}`, `{region}`, `{occupation}`, `{narrative}`.

**Reaction user prompt** — asks for a JSON reaction. Must include `{scenario}`
placeholder and request the same JSON shape:
```json
{"sentiment": "supportive|neutral|opposed", "intensity": 0-100, "reasoning": "..."}
```

Translation matters more than literal correspondence. The Korean prompt's
`"영향이 있는데 의견이 양가적이면 더 강하게 느끼는 쪽 선택"` ("if you have
stake but mixed feelings, pick the stronger side") is critical for
breaking the LLM's neutral-bias — keep the spirit, not the words, when
porting.

### 4. Subclass `Locale`

```python
from koreasim.locales.base import Locale, Persona

class JapanLocale(Locale):
    language = "ja"
    country = "JP"
    display_name = "Japan (...your data source here...)"

    def regions(self) -> list[str]:
        return [...]  # 47 prefectures

    def generate_personas(self, count: int, seed: int | None = 42) -> list[Persona]:
        ...

    def system_prompt_template(self) -> str:
        return "..."

    def reaction_user_prompt(self) -> str:
        return "..."

JAPAN_LOCALE = JapanLocale()
```

### 5. Register it

In `koreasim/locales/__init__.py`, add to the `LOCALES` registry:

```python
from koreasim.locales.jp import JAPAN_LOCALE, JapanLocale

LOCALES: dict[str, Locale] = {
    "kr": KOREA_LOCALE,
    "us": US_LOCALE,
    "jp": JAPAN_LOCALE,  # NEW
}
```

### 6. Add a test

Add a parameterized test to `tests/test_locales.py` to confirm the new
locale satisfies the protocol:

```python
@pytest.mark.parametrize("code", ["kr", "us", "jp"])
def test_locale_satisfies_protocol(code):
    loc = get_locale(code)
    personas = loc.generate_personas(count=5, seed=0)
    assert len(personas) == 5
    assert all(p.region in loc.regions() or True for p in personas)
    assert "{scenario}" in loc.reaction_user_prompt()
    for placeholder in ("{name}", "{age}", "{region}", "{occupation}"):
        assert placeholder in loc.system_prompt_template()
```

### 7. (Optional) wire `--locale` into the CLI

Today the CLI defaults to Korean. To opt-in another locale:

```bash
koreasim run --locale jp "次の地震について..." --n 100
```

CLI integration is on the roadmap — see open issues. For now, locales work
through the library API:

```python
from koreasim.locales import get_locale
locale = get_locale("jp")
personas = locale.generate_personas(count=200)
# ...feed to ScenarioRunner with locale.system_prompt_template()
```

## What's NOT abstracted (and why)

The following are *not* part of the Locale interface — by design:

- **The dashboard** assumes one bubble map / one set of demographic groupings.
  Korea's 17 광역시도 map is hardcoded. Adding a new locale's geo-vis is a
  separate task — see `koreasim/viz/korea_map.py` for the pattern.
- **The aggregation buckets** (`age_bucket`, `occupation_group`) on
  `KoreanPersona` are Korea-specific. The generic `Persona` doesn't have
  them. If you need cross-locale aggregation, write helpers per locale.
- **The scenario library** (`pension_age`, `housing_price`, `kospi_crash`,
  ...) is Korea-specific. New locales should ship their own scenario file.

In short: **persona generation + prompt language are abstracted; visualization
and scenario content are not.** If you want full feature parity for a new
locale, expect to also write the locale's geo-vis layer and a few canonical
scenarios.

## Contribution path

PRs adding new locales are welcome. Minimum bar for merge:

- [ ] `koreasim/locales/<cc>.py` with all four `Locale` methods
- [ ] Test in `tests/test_locales.py` proving protocol satisfaction
- [ ] Honest docstring naming the data source (or saying "synthetic stub")
- [ ] Listed in `LOCALES` registry

Geo-vis and scenario library can come in follow-up PRs.
