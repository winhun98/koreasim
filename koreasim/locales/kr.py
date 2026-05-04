"""Korea locale — adapter over the existing `koreasim.persona` module.

This file is purely additive: it does not modify `koreasim.persona` or
`koreasim.scenario.prompts`. It exposes the existing Korean implementation
through the generic `Locale` interface so that downstream code can iterate
locales uniformly.

For Korea, the *real* implementation lives in:
- `koreasim.persona.schema.KoreanPersona` — rich Korean-specific fields
- `koreasim.persona.sample.generate_sample_personas` — KOSIS-inspired sampler
- `koreasim.scenario.prompts.REACTION_USER_PROMPT` — Korean JSON-output prompt

`KoreaLocale.generate_personas()` wraps these and adapts the rich
`KoreanPersona` into the universal `Persona` shape. Use the locale-specific
classes directly when you need full Korean fidelity (life_stage, persona_type,
political_lean, etc.).
"""

from __future__ import annotations

from koreasim.locales.base import Locale, Persona
from koreasim.persona.sample import generate_sample_personas
from koreasim.persona.schema import REGIONS as KR_REGIONS
from koreasim.scenario.prompts import REACTION_USER_PROMPT


class KoreaLocale(Locale):
    language = "ko"
    country = "KR"
    display_name = "Republic of Korea (Nemotron-Personas-Korea + KOSIS)"

    def regions(self) -> list[str]:
        return list(KR_REGIONS)

    def generate_personas(self, count: int, seed: int | None = 42) -> list[Persona]:
        kr_personas = generate_sample_personas(count=count, seed=seed)
        return [
            Persona(
                persona_id=p.persona_id,
                name=p.name,
                age=p.age,
                region=p.region,
                gender=p.gender,
                occupation=p.occupation,
                education=p.education,
                narrative=p.narrative,
                income_bracket=p.income_bracket,
                locale=self.language,
                extras={
                    "district": p.district,
                    "marital_status": p.marital_status,
                    "life_stage": p.life_stage,
                    "skills": p.skills,
                    "interests": p.interests,
                    "persona_type": p.persona_type,
                    "political_lean": p.political_lean,
                },
            )
            for p in kr_personas
        ]

    def system_prompt_template(self) -> str:
        return (
            "당신은 한국의 한 시민으로서, 아래 신원과 일치하는 시각으로만 답변합니다.\n"
            "\n"
            "[신원]\n"
            "- 이름: {name}\n"
            "- 나이: {age}세 ({gender})\n"
            "- 거주지: {region}\n"
            "- 직업: {occupation}\n"
            "\n"
            "[배경 서사]\n"
            "{narrative}\n"
            "\n"
            "[행동 지침]\n"
            "- 위 신원에 충실한 한 사람의 시민으로서 답변하세요.\n"
            "- 통계 일반론이 아닌, 본인 입장에서의 솔직한 반응을 답하세요.\n"
            "- 반드시 한국어 존댓말을 사용하세요."
        )

    def reaction_user_prompt(self) -> str:
        return REACTION_USER_PROMPT


KOREA_LOCALE = KoreaLocale()
