"""Emoji-avatar people grid — render each persona as a small clickable avatar.

Job category and age bucket map to an emoji; sentiment maps to the border color.
The HTML output is self-contained (inline CSS, no JS framework) so it embeds
cleanly into the dashboard.

For very large N, we stratify-sample down to `max_display` so the grid stays
screenshot-friendly (and doesn't blow up the browser DOM).
"""

from __future__ import annotations

import html
import random
from collections import defaultdict

from koreasim.persona.schema import KoreanPersona, Reaction
from koreasim.scenario.runner import ScenarioResult

# 직업군 → emoji (성별별)
_JOB_EMOJI: dict[str, tuple[str, str]] = {
    # group: (남성, 여성)
    "IT/엔지니어":   ("👨‍💻", "👩‍💻"),
    "의료직":        ("👨‍⚕️", "👩‍⚕️"),
    "교육직":        ("👨‍🏫", "👩‍🏫"),
    "공무원":        ("🧑‍💼", "🧑‍💼"),
    "자영업/사업":   ("🧑‍🍳", "🧑‍🍳"),
    "농수축산업":    ("👨‍🌾", "👩‍🌾"),
    "학생":          ("🧑‍🎓", "🧑‍🎓"),
    "전업주부":      ("🧑‍🍼", "🧑‍🍼"),
    "무직/은퇴":     ("🧓", "👵"),
    "사무/기타":     ("🧑‍💼", "🧑‍💼"),
}

# 연령대별 변형 (override 직업 emoji when stage is dominant)
_AGE_EMOJI_OVERRIDE: dict[str, tuple[str, str]] = {
    "10대": ("👦", "👧"),
    "70대+": ("🧓", "👵"),
}

_SENTIMENT_CLASS = {
    "supportive": "supp",
    "neutral": "neu",
    "opposed": "opp",
}


def _emoji_for(persona: KoreanPersona) -> str:
    age_bucket = persona.age_bucket()
    male = persona.gender == "남성"
    if age_bucket in _AGE_EMOJI_OVERRIDE:
        m, f = _AGE_EMOJI_OVERRIDE[age_bucket]
        return m if male else f
    job = persona.occupation_group()
    m, f = _JOB_EMOJI.get(job, ("🧑", "🧑"))
    return m if male else f


def _stratified_sample(
    pairs: list[tuple[KoreanPersona, Reaction]],
    n: int,
    seed: int = 42,
) -> list[tuple[KoreanPersona, Reaction]]:
    """Stratify-sample to ~n pairs, balanced across (region, age_bucket)."""
    if len(pairs) <= n:
        return pairs

    rng = random.Random(seed)
    groups: dict[tuple[str, str], list[tuple[KoreanPersona, Reaction]]] = defaultdict(list)
    for p, r in pairs:
        key = (p.region, p.age_bucket())
        groups[key].append((p, r))

    per_group = max(1, n // max(len(groups), 1))
    out: list[tuple[KoreanPersona, Reaction]] = []
    for items in groups.values():
        rng.shuffle(items)
        out.extend(items[:per_group])
    rng.shuffle(out)
    return out[:n]


def render_people_grid_html(
    result: ScenarioResult,
    *,
    max_display: int = 400,
    seed: int = 42,
) -> str:
    """Render an HTML chunk: a wall of emoji avatars + a hidden details panel.

    Each avatar's tooltip carries name/age/region/job/reasoning. Click handler
    (a tiny inline script) reveals a panel below with the full reasoning.
    """
    pairs: list[tuple[KoreanPersona, Reaction]] = []
    for r in result.reactions:
        p = result.persona_for(r)
        if p is not None:
            pairs.append((p, r))

    total_n = len(pairs)
    sampled = _stratified_sample(pairs, max_display, seed=seed)
    showing = len(sampled)

    sentiment_order = {"supportive": 0, "neutral": 1, "opposed": 2}
    sampled = sorted(
        sampled,
        key=lambda pr: (
            sentiment_order.get(pr[1].sentiment, 9),
            -pr[1].intensity,
        ),
    )

    cards = []
    for p, r in sampled:
        e = _emoji_for(p)
        sent_class = _SENTIMENT_CLASS.get(r.sentiment, "neu")
        # Compact tooltip (browser-native title= attribute).
        tooltip = (
            f"{p.name} · {p.age}세 {p.gender}\n"
            f"{p.region} · {p.occupation_group()}\n"
            f"강도 {r.intensity} · {r.sentiment}\n"
            f"{r.reasoning[:120]}"
        )
        # Data attributes so the JS click handler can render full reasoning.
        cards.append(
            f'<button class="person {sent_class}" '
            f'title="{html.escape(tooltip)}" '
            f'data-name="{html.escape(p.name)}" '
            f'data-meta="{html.escape(f"{p.age}세 {p.gender} · {p.region} · {p.occupation_group()}")}" '
            f'data-sentiment="{r.sentiment}" '
            f'data-intensity="{r.intensity}" '
            f'data-reasoning="{html.escape(r.reasoning)}">'
            f'<span class="emoji">{e}</span>'
            f"</button>"
        )

    grid_html = "".join(cards)

    note = (
        f"전체 {total_n:,}명 중 {showing}명 표시 (지역·연령대로 stratified sampling)"
        if total_n > showing
        else f"{total_n:,}명 전원 표시"
    )

    return f"""
<div class="people-section">
  <div class="people-header">
    <span class="people-note">{note} · 정렬: 찬성 → 중립 → 반대</span>
    <div class="people-legend">
      <span class="lg supp"></span>찬성
      <span class="lg neu"></span>중립
      <span class="lg opp"></span>반대
    </div>
  </div>
  <div class="people-grid" id="people-grid">
    {grid_html}
  </div>
  <div id="person-detail" class="person-detail hidden">
    <button class="person-detail-close" onclick="document.getElementById('person-detail').classList.add('hidden');">×</button>
    <div class="pd-body"></div>
  </div>
</div>

<style>
.people-section {{ margin: 0; }}
.people-header {{
  display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
  margin: 0 0 14px 0;
}}
.people-note {{ color: #8a8175; font-size: 0.78rem; font-family: "JetBrains Mono", monospace; }}
.people-legend {{
  margin-left: auto; color: #5b5347; font-size: 0.78rem;
  display: flex; align-items: center; gap: 14px;
}}
.people-legend .lg {{
  display: inline-block; width: 9px; height: 9px;
  margin-right: 5px; vertical-align: middle;
}}
.people-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(34px, 1fr));
  gap: 3px;
  padding: 0;
  margin-bottom: 28px;
}}
.person {{
  display: flex; align-items: center; justify-content: center;
  aspect-ratio: 1 / 1;
  border: 1px solid transparent;
  padding: 0;
  cursor: pointer;
  transition: transform 0.1s ease, outline-color 0.1s ease;
  font: inherit;
  outline: 1px solid transparent;
  outline-offset: -1px;
}}
.person:hover {{
  transform: scale(1.5);
  z-index: 3;
  outline-color: #8b5a1f;
}}
.person .emoji {{ font-size: 16px; line-height: 1; filter: saturate(0.85); }}
.person.supp {{ background: #d4dfa8; border-color: #a3b56a; }}
.person.neu  {{ background: #ebe1c8; border-color: #c4b89e; }}
.person.opp  {{ background: #e6c0a8; border-color: #c08566; }}
.lg.supp {{ background: #5a7333; }}
.lg.neu  {{ background: #b8a98a; }}
.lg.opp  {{ background: #9c3a14; }}

.person-detail {{
  margin-top: 14px;
  padding: 18px 0;
  border-top: 1px solid #d8cdb3;
  border-bottom: 1px solid #d8cdb3;
  position: relative;
}}
.person-detail.hidden {{ display: none; }}
.person-detail-close {{
  position: absolute; top: 12px; right: 4px;
  background: transparent; border: none; color: #8a8175;
  font-size: 1.3rem; cursor: pointer; padding: 0;
  line-height: 1;
}}
.person-detail-close:hover {{ color: #8b5a1f; }}
.pd-body .pd-name {{
  font-family: "Noto Serif KR", Georgia, serif;
  font-size: 1.15rem; font-weight: 600; color: #1f1a13;
}}
.pd-body .pd-meta {{
  color: #8a8175; font-size: 0.82rem;
  font-family: "JetBrains Mono", monospace;
  margin: 4px 0 14px 0;
}}
.pd-body .pd-quote {{
  font-family: "Noto Serif KR", Georgia, serif;
  color: #1f1a13; line-height: 1.7; font-size: 1.02rem;
  margin: 8px 0 0 0;
}}
.pd-body .pd-tag {{
  display: inline-block; font-size: 0.78rem;
  font-family: "JetBrains Mono", monospace;
  margin-right: 0;
}}
.pd-body .pd-tag.supp {{ color: #5a7333; }}
.pd-body .pd-tag.opp {{ color: #9c3a14; }}
.pd-body .pd-tag.neu {{ color: #8a8175; }}
</style>

<script>
(function() {{
  const grid = document.getElementById('people-grid');
  const panel = document.getElementById('person-detail');
  const body = panel.querySelector('.pd-body');
  if (!grid) return;
  const sentLabel = {{ supportive: ['supp', '찬성'], neutral: ['neu', '중립'], opposed: ['opp', '반대'] }};
  grid.addEventListener('click', function(e) {{
    const btn = e.target.closest('.person');
    if (!btn) return;
    const sentiment = btn.dataset.sentiment;
    const [cls, label] = sentLabel[sentiment] || ['neu', '중립'];
    body.innerHTML = `
      <div class="pd-name">${{btn.dataset.name}}</div>
      <div class="pd-meta">${{btn.dataset.meta}}</div>
      <div>
        <span class="pd-tag ${{cls}}">${{label}} · 강도 ${{btn.dataset.intensity}}</span>
      </div>
      <p class="pd-quote">${{btn.dataset.reasoning || '(응답 없음)'}}</p>
    `;
    panel.classList.remove('hidden');
    panel.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  }});
}})();
</script>
"""
