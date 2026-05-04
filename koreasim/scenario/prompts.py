"""Korean prompt templates for scenario reactions."""

REACTION_USER_PROMPT_FALLBACK = """[시나리오]
{scenario}

본인 신원에 비춰 위 시나리오에 대한 입장을 짧게 답하세요. JSON만 출력:

{{
  "sentiment": "supportive" | "neutral" | "opposed",
  "intensity": 0~100,
  "reasoning": "한 문장"
}}
"""


REACTION_USER_PROMPT = """[시나리오]
{scenario}

본인 신원(나이·지역·직업·소득·정치성향)에 비춰 위 시나리오가 본인 생활에 미치는
실제 영향을 바탕으로, 아래 JSON 형식으로만 응답하세요. (마크다운 펜스 없이 JSON만)

{{
  "sentiment": "supportive" | "neutral" | "opposed",
  "intensity": 0~100,
  "reasoning": "본인이 체감하는 구체적 영향과 그에 따른 입장 (한 두 문장)"
}}

기준:
- "supportive": 본인에게 이득 / 찬성하는 입장
- "opposed": 본인에게 손해 / 반대하는 입장
- "neutral": 본인 생활에 직접 영향이 거의 없을 때만. 영향이 있는데 의견이 양가적이면
  더 강하게 느끼는 쪽(supportive 또는 opposed)을 선택. 회피용 중립 금지.
- "intensity": neutral이면 30 미만이 자연스러움. 100=극심.
- "reasoning": 통계·일반론이 아닌, 본인 신원에 비춘 구체적 이유. 한 두 문장.
"""


BRIEF_GENERATION_PROMPT = """You are extracting a structured brief from a Korean news article so it can be used as the stimulus for a society simulation.

[Article body]
{article_text}

Return ONLY a JSON object (no markdown fences, no prose). All string VALUES must be in Korean — only the JSON keys are English. Schema:

{{
  "actor": "Subject that decides/enacts the action (e.g. 정부, 한국은행, 회사명)",
  "action": "One-line description of the decision or event",
  "magnitude": "Headline magnitude (e.g. '30% 인상', '12,000원')",
  "target": "Who is affected (e.g. '운전자 전체', '20대 청년')",
  "time": "Effective time / horizon (e.g. '2026년 1월', '향후 5년 내')",
  "scope": "Geographic scope (e.g. '전국', '수도권')",
  "key_numbers": ["verbatim numeric expressions copied from the article", ...],
  "quotes": ["verbatim quotes (1-2 sentences) copied from the article, supporting AND opposing if both exist", ...],
  "summary": "A 5-8 sentence Korean paragraph that re-tells the article as a self-contained scenario suitable for asking a persona how they react"
}}

Strict rules:
- Every item in `key_numbers` and `quotes` MUST appear verbatim in the article body. Whitespace differences are tolerated; characters must match exactly.
- The `summary` must be in natural Korean and must not invent facts beyond the article.
- Output JSON only — no preamble, no explanation, no code fences."""


BRIEF_RETRY_PROMPT = """Your previous response contained items that do NOT appear verbatim in the source article:
{failed_items}

Regenerate the brief using ONLY expressions that occur verbatim in the article below. Same JSON schema as before. All values in Korean except the keys.

[Article body]
{article_text}

Output JSON only — no preamble. Every `key_numbers` and `quotes` item must be a substring of the article."""


SCENARIO_TEMPLATES = {
    "pension_age": (
        "정부가 국민연금 수령 개시 연령을 현행 65세에서 68세로 단계적으로 상향한다고 발표했습니다."
    ),
    "housing_price": (
        "수도권 아파트 가격이 향후 1년 내 평균 20% 추가 상승할 것으로 전망된다는 보고서가 발표되었습니다."
    ),
    "kospi_crash": (
        "코스피 지수가 단 하루 만에 8% 급락하며 서킷브레이커가 발동되었습니다. "
        "국내 주요 대형주가 일제히 하한가 근처까지 떨어졌고, 외국인 매도세가 거셉니다."
    ),
    "minimum_wage": (
        "내년 최저임금이 시급 12,000원으로 약 20% 인상되는 안이 통과되었습니다."
    ),
    "ai_replacement": (
        "AI가 향후 5년 내 사무직 일자리의 30%를 자동화할 것이라는 정부 보고서가 공개되었습니다."
    ),
}
