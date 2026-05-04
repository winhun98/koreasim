"""LLM backend — talks to any OpenAI-compatible /v1/chat/completions server.

Defaults to Ollama's local server with `qwen3:8b` (the recommended setup for
KoreaSim — strong Korean output, ~5.2 GB). Anything that speaks the OpenAI
Chat Completions schema works: vLLM, llama.cpp / llama-server, bitnet.cpp,
TGI, NVIDIA NIM, OpenAI itself, etc.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re as _re
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Connection + sampling defaults for the LLM backend.

    `model` may be a KoreaSim preset key (`bitnet-2b`, `bitnet-3b`, `llama3-8b`)
    or an explicit HuggingFace id (`org/model-name`). Use the
    `LLMConfig.from_preset(name)` factory to pin an exact preset.
    """

    base_url: str = "http://127.0.0.1:11434"   # default to Ollama
    api_key: str | None = None  # ignored by Ollama / bitnet.cpp; required for hosted APIs
    model: str = "qwen3:8b"   # default = `qwen3-8b` preset
    # Sampling tuned to break Qwen3's RLHF "neutral attractor" while staying
    # fluent. Empirical results (5 scenarios × N=100): mean neutral 64% → 51%,
    # avg intensity 41 → 52. See docs/SAMPLING.md for details.
    temperature: float = 0.9
    top_p: float = 0.95
    # min_p clips low-probability tokens *relative to the top token*. 0.03~0.05
    # is the sweet spot — high enough to break "always neutral" without making
    # Qwen3 freeze. 0 = disabled. Ollama's OpenAI-compat endpoint accepts this
    # as a top-level extra body field.
    min_p: float = 0.03
    # 800 needed for Korean prompts: 400-500 tokens for reasoning + JSON
    # boilerplate. 256 truncates ~80% of responses; 600 truncates ~20%.
    max_tokens: int = 800
    n_parallel: int = 4  # 8 caused Ollama to truncate under contention
    timeout_s: float = 180.0
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_preset(cls, preset_key: str, **overrides) -> LLMConfig:
        """Build a config pinned to a known 1.58-bit model preset."""
        from koreasim.llm.models import resolve_model

        model_id, _ = resolve_model(preset_key)
        return cls(model=model_id, **overrides)


@dataclass
class LLMResponse:
    text: str
    tokens_used: int = 0
    finish_reason: str = "stop"


class LLMBackend:
    """Abstract base — swap implementations for testing / different runtimes."""

    async def start(self) -> None:  # pragma: no cover
        ...

    async def stop(self) -> None:  # pragma: no cover
        ...

    async def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:  # pragma: no cover
        raise NotImplementedError

    async def generate_batch(
        self,
        prompts: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> list[LLMResponse]:
        tasks = [
            self.generate(
                p["prompt"],
                system=p.get("system", ""),
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            for p in prompts
        ]
        return await asyncio.gather(*tasks)


class OpenAICompatibleBackend(LLMBackend):
    """Async client for any OpenAI-Chat-compatible endpoint (bitnet.cpp default)."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._client: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(self.config.n_parallel)

    async def start(self) -> None:
        headers = {"Content-Type": "application/json", **self.config.extra_headers}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=httpx.Timeout(self.config.timeout_s, connect=10.0),
            headers=headers,
        )

        # Best-effort health check — many bitnet.cpp builds expose /health.
        try:
            r = await self._client.get("/health")
            if r.status_code == 200:
                logger.info("LLM server healthy at %s", self.config.base_url)
            else:
                logger.info("LLM server reachable (status %d) at %s", r.status_code, self.config.base_url)
        except httpx.HTTPError:
            logger.warning(
                "LLM server unreachable at %s — start bitnet.cpp `llama-server` first.",
                self.config.base_url,
            )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        async with self._semaphore:
            return await self._call_chat(
                prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )

    async def _call_chat(
        self,
        prompt: str,
        *,
        system: str,
        temperature: float | None,
        max_tokens: int | None,
        json_mode: bool,
    ) -> LLMResponse:
        if not self._client:
            raise RuntimeError("Backend not started — call await backend.start() first.")

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "top_p": self.config.top_p,
        }
        if self.config.min_p > 0:
            body["min_p"] = self.config.min_p
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            r = await self._client.post("/v1/chat/completions", json=body)
            r.raise_for_status()
            data = r.json()
            choice = data["choices"][0]
            return LLMResponse(
                text=choice["message"]["content"],
                tokens_used=data.get("usage", {}).get("total_tokens", 0),
                finish_reason=choice.get("finish_reason", "stop"),
            )
        except httpx.HTTPError as e:
            logger.error("LLM API error: %s", e)
            raise
        except (KeyError, IndexError, ValueError) as e:
            logger.error("Unexpected LLM response shape: %s", e)
            raise


class MockBackend(LLMBackend):
    """Template-based mock backend — used by `koreasim demo` and tests.

    Real BitNet generates a unique reasoning per persona (the system prompt is
    different for every agent). The mock here is *templated*: it parses
    persona info (region / age / occupation / political lean) out of the
    system prompt and slot-fills one of ~30 reasoning templates per sentiment.

    The result is offline, deterministic, fast, and — unlike a 3-string mock
    — actually demographically-flavored when you click through avatars.
    It is NOT a substitute for real BitNet output.
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

    async def start(self) -> None:
        logger.info("MockBackend ready (no real LLM — templated reasoning)")

    async def stop(self) -> None:
        pass

    async def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        seed_text = system + prompt
        h = sum(ord(c) for c in seed_text)

        # Brief-generation request — detected by a token only present in
        # `BRIEF_GENERATION_PROMPT`. Returns a placeholder brief whose
        # key_numbers / quotes are empty so the verbatim guard always passes
        # in offline / mock mode.
        if "key_numbers" in prompt and "Article body" in prompt:
            payload = {
                "actor": "[mock] 행위자",
                "action": "[mock] 조치",
                "magnitude": "[mock] 규모",
                "target": "[mock] 대상",
                "time": "[mock] 시점",
                "scope": "[mock] 범위",
                "key_numbers": [],
                "quotes": [],
                "summary": "[Mock 시나리오] 기사 본문이 시뮬레이션 시나리오로 사용됩니다.",
            }
            return LLMResponse(text=json.dumps(payload, ensure_ascii=False), tokens_used=128)

        if json_mode:
            sentiment = "supportive" if (h % 100) < 35 else ("opposed" if (h % 100) < 70 else "neutral")
            intensity = 30 + ((h // 7) % 70)
            persona_info = _extract_persona_info(system)
            reasoning = _mock_reasoning(sentiment, intensity, persona_info, h, user_prompt=prompt)
            payload = {
                "sentiment": sentiment,
                "intensity": intensity,
                "reasoning": reasoning,
            }
            return LLMResponse(text=json.dumps(payload, ensure_ascii=False), tokens_used=64)

        return LLMResponse(text="[Mock] 한국어 모의 응답입니다.", tokens_used=10)


# ----- System-prompt parsing (for the mock to look demographically grounded) -----

_NAME_RE = _re.compile(r"이름:\s*(\S+)")
_AGE_RE = _re.compile(r"나이:\s*(\d+)세\s*\((\S+)\)")
_REGION_RE = _re.compile(r"거주지:\s*([^\n]+?)(?:\s*$|\n)")
_OCC_RE = _re.compile(r"직업:\s*([^\n]+)")
_MARITAL_RE = _re.compile(r"혼인 상태:\s*(\S+)")


def _extract_persona_info(system: str) -> dict[str, str]:
    """Best-effort extraction. Missing fields just become empty strings —
    templates are written to read fine without them."""
    if not system:
        return {}
    info: dict[str, str] = {}
    if (m := _NAME_RE.search(system)):
        info["name"] = m.group(1)
    if (m := _AGE_RE.search(system)):
        info["age"] = m.group(1)
        info["gender"] = m.group(2)
        info["age_bucket"] = _age_to_bucket(int(m.group(1)))
    if (m := _REGION_RE.search(system)):
        info["region"] = m.group(1).strip()
    if (m := _OCC_RE.search(system)):
        info["occupation"] = m.group(1).strip()
    if (m := _MARITAL_RE.search(system)):
        info["marital"] = m.group(1)
    return info


def _age_to_bucket(age: int) -> str:
    if age < 20:
        return "10대"
    if age < 30:
        return "20대"
    if age < 40:
        return "30대"
    if age < 50:
        return "40대"
    if age < 60:
        return "50대"
    if age < 70:
        return "60대"
    return "70대+"


# ----- Reasoning templates (mock only) -----
#
# Templates are bucketed by *scenario type* (policy / forecast / market_event)
# so a KOSPI crash doesn't get a "did you ask the field?" policy template.
#
# Slot variables: {age_bucket}, {occupation}, {region}, {marital}.
# Templates avoid `{occupation}로서/로` constructions because Korean particle
# 받침 rules would mis-render (`고등학생로서` is wrong). Use `{occupation} 입장에서`
# patterns instead.


# ----- POLICY (decision being made — pension, minimum wage, ...) -----

_POLICY_SUPPORTIVE = [
    "{age_bucket} 입장에서 장기적으로 안정에 도움이 될 변화라고 봅니다.",
    "{region}에서 살면서 이런 방향은 필요했다고 생각합니다.",
    "당장은 부담이 있어도, 다음 세대를 위해 불가피한 선택입니다.",
    "{occupation} 입장에서도 충분히 받아들일 만한 결정입니다.",
    "솔직히 우리 {age_bucket}에게는 환영할 만한 결정입니다.",
    "더 늦으면 더 큰 부담이 올 텐데 지금 받아들이는 게 낫습니다.",
    "감수할 가치가 있는 변화라고 판단합니다.",
    "큰 그림에서 사회 안정에 기여한다고 생각합니다.",
    "사회적 합의로 천천히 가는 방향이라면 받아들일 수 있습니다.",
    "이 정도 변화는 미리 대비할 시간이 있다고 봅니다.",
]

_POLICY_OPPOSED = [
    "{age_bucket} 입장에서 직접적인 부담이 너무 큽니다.",
    "{region} {occupation} 입장에서 당장 생계에 영향이 있습니다.",
    "이미 빠듯한 살림에 또 부담을 떠안으라는 건가 싶습니다.",
    "현장 의견은 충분히 들어본 건지 의문입니다.",
    "{region}처럼 형편이 다른 지역도 일률적으로 적용하는 건 무리입니다.",
    "우리 {age_bucket}는 평생 이런 변화의 손실만 감수해 온 세대입니다.",
    "{occupation} 입장에서는 직격탄입니다.",
    "이 결정으로 우리 가구의 가처분소득이 분명히 줄어듭니다.",
    "솔직히 분노가 먼저 듭니다. {age_bucket}에게 너무 가혹합니다.",
    "준비할 시간을 더 줬어야 한다고 생각합니다.",
]

_POLICY_NEUTRAL = [
    "{age_bucket} 입장이라 당장 큰 영향은 없을 것 같습니다.",
    "지켜봐야 알 것 같습니다. {region}에서는 좀 다르게 작용할 수도 있고요.",
    "{occupation} 입장에서 솔직히 직접 와닿지 않습니다.",
    "그동안 비슷한 변화가 많아서 그러려니 합니다.",
    "구체적인 시행안이 나와봐야 판단할 수 있겠습니다.",
    "다른 큰 이슈가 많아 이 변화는 우선순위가 낮습니다.",
    "한 번에 변화가 오는 건 아니니 일상대로 살 생각입니다.",
    "{region} 분위기는 아직 잠잠합니다.",
    "{age_bucket}는 이미 영향권 밖이라 큰 의견은 없습니다.",
    "장단점이 다 있어서 한쪽으로 단정하기 어렵습니다.",
]


# ----- FORECAST (prediction / report — housing, AI replacement, ...) -----

_FORECAST_SUPPORTIVE = [
    "예상된 흐름이라 새삼스럽지 않습니다. {region}에서는 이미 체감 중입니다.",
    "{age_bucket} 입장에서 큰 충격이라고 보기는 어렵습니다.",
    "이미 시장이 그렇게 흘러왔으니 자연스러운 결과라고 봅니다.",
    "전망은 전망일 뿐, 실제로는 더 완만하게 진행될 거라 봅니다.",
    "변화 자체가 무조건 나쁜 것만은 아니라고 생각합니다.",
    "이번 보고서 정도는 받아들이고 미리 대비하면 됩니다.",
    "결국엔 적응할 수 있는 수준이라고 봅니다.",
    "{occupation} 입장에서 새로운 기회로 보일 수도 있다고 생각합니다.",
    "{age_bucket}는 이런 변화에 비교적 빠르게 적응합니다.",
    "걱정만 한다고 해결되는 건 아니니 차분하게 준비할 생각입니다.",
]

_FORECAST_OPPOSED = [
    "{age_bucket} 입장에서 이런 전망이 현실이 되면 정말 막막합니다.",
    "{region} {occupation} 입장에서 가뜩이나 어려운데 추가 부담이 됩니다.",
    "{age_bucket} 청년층에게는 절망적인 전망입니다.",
    "이대로 가면 우리 세대는 정말 힘들 것 같습니다.",
    "전망대로라면 가계 부담이 한계를 넘어섭니다.",
    "{age_bucket} 가장 입장에서 너무 무겁습니다.",
    "정부 차원의 대책이 시급해 보입니다.",
    "{region}에 사는 입장에서 이런 흐름은 불공평하게 느껴집니다.",
    "주거든 일자리든 점점 손에 잡히지 않는 느낌입니다.",
    "예측이 빗나가길 바랄 뿐입니다. 이대로면 답이 없습니다.",
]

_FORECAST_NEUTRAL = [
    "전망은 전망이고 실제로 봐야 알 것 같습니다.",
    "{age_bucket}라 직접적인 영향은 적을 것 같습니다.",
    "예측은 자주 빗나가는 편이니 차분히 지켜보겠습니다.",
    "{region} 분위기는 아직 평소와 비슷합니다.",
    "{occupation} 입장에서 큰 의미를 두지 않습니다.",
    "걱정도 기대도 적당히 하려고 합니다.",
    "이런 보고서가 한두 번이 아니라 무덤덤합니다.",
    "변수가 많아서 단정하기 어렵습니다.",
    "당장은 일상에 영향이 없으니 평소대로 지냅니다.",
    "한참 뒤에나 보일 변화라고 생각합니다.",
]


# ----- MARKET_EVENT (a thing that just happened — KOSPI crash, etc.) -----

_MARKET_SUPPORTIVE = [
    "주식이나 펀드를 거의 안 해서 직접 영향은 없습니다.",
    "{age_bucket} 입장에서는 오히려 저점 매수 기회라고 봅니다.",
    "장기 투자자라 일시적 변동에는 흔들리지 않습니다.",
    "{region}에서는 부동산이 더 중요해서 코스피 등락은 멀게 느껴집니다.",
    "월급으로 사는 입장이라 주식 비중은 크지 않습니다.",
    "패닉 셀링은 피해야 한다고 봅니다. 지금이 기회일 수 있어요.",
    "{age_bucket}라 시간이 충분해서 회복을 기다릴 수 있습니다.",
    "{occupation} 일이 시장과 직접 연결되지 않아 평소대로 지냅니다.",
    "이런 변동은 처음이 아니라 차분하게 대응 중입니다.",
    "감정적으로 흔들릴 필요 없는 단기 변동이라고 봅니다.",
]

_MARKET_OPPOSED = [
    "{age_bucket} 입장에서 노후 자금이 흔들려 잠을 설치고 있습니다.",
    "퇴직금을 펀드에 넣어 둔 상태라 직격탄입니다.",
    "{occupation} 입장에서 사업 자금줄까지 흔들릴까 걱정입니다.",
    "이미 손실 폭이 커서 어떻게 회복해야 할지 막막합니다.",
    "{region}의 자영업자 분들이 더 힘들어질 거라 봅니다.",
    "우리 {age_bucket}는 손실을 메울 시간이 부족합니다.",
    "외국인 매도가 너무 거세서 단기 회복이 어려워 보입니다.",
    "이런 폭락이 한 번 더 오면 정말 위험합니다.",
    "주변에서도 큰 손실을 봤다는 얘기가 들려 분위기가 가라앉았습니다.",
    "단순 변동을 넘어 실물 경제로 번질까 두렵습니다.",
]

_MARKET_NEUTRAL = [
    "주식을 거의 안 해서 솔직히 와닿지 않습니다.",
    "지켜봐야 할 것 같습니다. 단기 반등이 있을 수도 있고요.",
    "{age_bucket}라 그동안 비슷한 일을 많이 봐서 담담합니다.",
    "{region} 분위기는 평소와 비슷합니다.",
    "당장 큰 결정을 내릴 필요는 없다고 봅니다.",
    "뉴스로만 듣고 있고, 직접 행동은 하지 않을 생각입니다.",
    "주변 반응이 과한 면도 있다고 느낍니다.",
    "{occupation} 일에 집중하느라 시장은 잠깐씩만 봅니다.",
    "이번 주가 지나봐야 윤곽이 잡힐 것 같습니다.",
    "투자 비중이 적어 큰 의미는 없습니다.",
]


# scenario_type → {sentiment → templates}
_TEMPLATE_BANK: dict[str, dict[str, list[str]]] = {
    "policy": {
        "supportive": _POLICY_SUPPORTIVE,
        "opposed": _POLICY_OPPOSED,
        "neutral": _POLICY_NEUTRAL,
    },
    "forecast": {
        "supportive": _FORECAST_SUPPORTIVE,
        "opposed": _FORECAST_OPPOSED,
        "neutral": _FORECAST_NEUTRAL,
    },
    "market_event": {
        "supportive": _MARKET_SUPPORTIVE,
        "opposed": _MARKET_OPPOSED,
        "neutral": _MARKET_NEUTRAL,
    },
}


# Keyword → scenario type. First match wins; defaults to "policy".
_TYPE_KEYWORDS = {
    "market_event": ("코스피", "코스닥", "급락", "폭락", "급등", "서킷브레이커", "환율", "비트코인"),
    "forecast":     ("전망", "보고서", "예측", "관측", "예상된다", "자동화", "추정"),
    "policy":       ("인상", "상향", "하향", "통과", "시행", "개정", "법안", "정책", "도입"),
}


def _detect_scenario_type(prompt: str) -> str:
    """Pick a template bank based on simple keyword matching on the user prompt."""
    for stype, kws in _TYPE_KEYWORDS.items():
        if any(k in prompt for k in kws):
            return stype
    return "policy"


# Intensity-suffix tails. Tone matches the type so a market crash doesn't get
# "이 방향에 동의합니다" (which only fits a policy decision).
_INTENSITY_SUFFIXES = {
    "policy": {
        "supportive": " 이 방향에 강하게 동의합니다.",
        "opposed": " 강도 높은 반발이 예상됩니다.",
    },
    "forecast": {
        "supportive": " 큰 무리 없는 전망이라고 봅니다.",
        "opposed": " 시급한 대책이 절실합니다.",
    },
    "market_event": {
        "supportive": " 차분하게 대응할 시점이라고 봅니다.",
        "opposed": " 손실 규모가 정말 큽니다.",
    },
}


def _mock_reasoning(
    sentiment: str,
    intensity: int,
    info: dict,
    seed_hash: int,
    *,
    user_prompt: str = "",
) -> str:
    stype = _detect_scenario_type(user_prompt)
    bank = _TEMPLATE_BANK[stype][sentiment]
    template = bank[seed_hash % len(bank)]

    slots = {
        "age_bucket": info.get("age_bucket", "한 시민"),
        "occupation": info.get("occupation") or "회사원",
        "region": info.get("region") or "수도권",
        "gender": info.get("gender") or "",
        "marital": info.get("marital") or "",
    }
    text = template
    for k, v in slots.items():
        text = text.replace("{" + k + "}", v)
    text = _re.sub(r"\s+,", ",", text).replace("()", "").strip()

    if intensity >= 80 and sentiment in ("supportive", "opposed"):
        text += _INTENSITY_SUFFIXES[stype][sentiment]
    return text
