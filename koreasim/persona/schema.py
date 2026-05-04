"""KoreanPersona — schema mirroring Nemotron-Personas-Korea + helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# 17개 광역시도 — Nemotron-Personas-Korea region 필드 표준값
REGIONS = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시",
    "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
    "경기도", "강원특별자치도", "충청북도", "충청남도",
    "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도",
)

LIFE_STAGES = ("학생", "군복무", "취업", "미취업", "퇴직")
PERSONA_TYPES = ("professional", "family", "sports", "arts", "travel", "culinary", "concise")
GENDERS = ("남성", "여성")


@dataclass
class KoreanPersona:
    """A single demographically-grounded Korean persona.

    Maps directly to Nemotron-Personas-Korea row fields. Designed so that
    `narrative` (자연어 페르소나 서술) can be dropped straight into a
    BitNet system prompt for grounded reactions.
    """

    persona_id: str
    name: str
    age: int
    gender: str  # "남성" | "여성"
    region: str  # 17개 광역시도 중 하나
    district: str = ""  # 자치구 (선택)
    occupation: str = "무직"
    education: str = ""  # 예: "대학교 졸업"
    marital_status: str = ""  # "기혼" | "미혼" | "이혼" | "사별"
    life_stage: str = "취업"
    skills: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    persona_type: str = "concise"
    narrative: str = ""  # 자유 형식 한국어 페르소나 서술 (Gemma 생성)

    # 시뮬레이션용 행동 파라미터 (옵션, demographic priors에서 추정)
    income_bracket: Literal["low", "mid", "high"] = "mid"
    political_lean: Literal["progressive", "moderate", "conservative"] = "moderate"

    # ----- 직렬화 -----

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KoreanPersona:
        # Tolerant of extra fields (HF dataset rows often carry more).
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        # Provide sensible defaults for missing required-ish fields.
        clean.setdefault("persona_id", str(data.get("id", "unknown")))
        clean.setdefault("name", data.get("name", "익명"))
        clean.setdefault("age", int(data.get("age", 35)))
        clean.setdefault("gender", data.get("gender", "남성"))
        clean.setdefault("region", data.get("region", "서울특별시"))
        return cls(**clean)

    # ----- 프롬프트 빌더 -----

    def to_system_prompt(self) -> str:
        """Render this persona as a Korean system prompt for BitNet."""
        parts = [
            "당신은 한국의 한 시민으로서, 아래 신원과 일치하는 시각으로만 답변합니다.",
            "",
            "[신원]",
            f"- 이름: {self.name}",
            f"- 나이: {self.age}세 ({self.gender})",
            f"- 거주지: {self.region}{(' ' + self.district) if self.district else ''}",
            f"- 직업: {self.occupation}",
        ]
        if self.education:
            parts.append(f"- 학력: {self.education}")
        if self.marital_status:
            parts.append(f"- 혼인 상태: {self.marital_status}")
        if self.life_stage:
            parts.append(f"- 생애 단계: {self.life_stage}")
        if self.skills:
            parts.append(f"- 주요 스킬/관심: {', '.join(self.skills[:5])}")
        if self.narrative:
            parts.extend(["", "[배경 서사]", self.narrative.strip()])
        parts.extend(
            [
                "",
                "[행동 지침]",
                "- 위 신원에 충실한 한 사람의 시민으로서 답변하세요.",
                "- 통계 일반론이 아닌, 본인 입장에서의 솔직한 반응을 답하세요.",
                "- 반드시 한국어 존댓말을 사용하세요.",
            ]
        )
        return "\n".join(parts)

    # ----- 데모그래픽 그룹 키 -----

    def age_bucket(self) -> str:
        if self.age < 20:
            return "10대"
        if self.age < 30:
            return "20대"
        if self.age < 40:
            return "30대"
        if self.age < 50:
            return "40대"
        if self.age < 60:
            return "50대"
        if self.age < 70:
            return "60대"
        return "70대+"

    def occupation_group(self) -> str:
        """Coarse occupation bucket for demographic breakdown."""
        occ = self.occupation
        if any(k in occ for k in ("학생",)):
            return "학생"
        if any(k in occ for k in ("의사", "간호", "약사", "보건", "의료")):
            return "의료직"
        if any(k in occ for k in ("교사", "교수", "강사", "교육")):
            return "교육직"
        if any(k in occ for k in ("개발자", "엔지니어", "프로그래머", "IT", "데이터")):
            return "IT/엔지니어"
        if any(k in occ for k in ("공무원", "공직")):
            return "공무원"
        if any(k in occ for k in ("자영업", "사장", "대표", "사업")):
            return "자영업/사업"
        if any(k in occ for k in ("농업", "어업", "임업", "축산")):
            return "농수축산업"
        if any(k in occ for k in ("주부", "전업")):
            return "전업주부"
        if any(k in occ for k in ("무직", "구직", "퇴직", "은퇴")):
            return "무직/은퇴"
        return "사무/기타"


@dataclass
class Reaction:
    """A persona's reaction to a scenario."""

    persona_id: str
    sentiment: Literal["supportive", "neutral", "opposed"]  # 찬성/중립/반대
    intensity: int  # 0-100, 반응 강도
    reasoning: str  # 한국어 자기 설명
    raw_response: str = ""  # LLM 원응답 (디버깅용)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Reaction:
        return cls(
            persona_id=str(data["persona_id"]),
            sentiment=data.get("sentiment", "neutral"),
            intensity=int(data.get("intensity", 50)),
            reasoning=data.get("reasoning", ""),
            raw_response=data.get("raw_response", ""),
        )
