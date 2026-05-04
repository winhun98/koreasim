"""Build a single-file HTML dashboard summarizing a ScenarioResult.

Sections (top → bottom):
1. Hero stats card  — N · elapsed · throughput · "$0 vs GPT-4 $X"
2. Korea map       — bubble per province, color = net sentiment
3. People grid     — emoji avatars, click to read individual reasoning
4. Demographic bars — age / region / occupation / political lean
5. Quotes by group — high-intensity sample reasoning per bucket

Plotly is an optional dependency — install with `pip install koreasim[viz]`.
A text-mode report (Rich) is always available without plotly.
"""

from __future__ import annotations

import logging
from pathlib import Path

from koreasim.analysis.aggregate import aggregate_by, summarize
from koreasim.analysis.compute import ComputeReceipt, receipt_for_run
from koreasim.llm.models import ModelPreset
from koreasim.scenario.runner import ScenarioResult
from koreasim.viz.korea_map import build_korea_map
from koreasim.viz.people_grid import render_people_grid_html

logger = logging.getLogger(__name__)


_SENTIMENT_COLORS = {
    "supportive": "#5a7333",
    "neutral": "#b8a98a",
    "opposed": "#9c3a14",
}


def build_dashboard(
    result: ScenarioResult,
    out_path: str | Path,
    *,
    title: str = "KoreaSim — Scenario Reaction Dashboard",
    receipt: ComputeReceipt | None = None,
    model: ModelPreset | None = None,
) -> Path:
    """Render an interactive HTML dashboard. Requires plotly."""
    try:
        from plotly.subplots import make_subplots
    except ImportError as e:
        raise ImportError(
            "Dashboard requires the optional `viz` extra: pip install koreasim[viz]"
        ) from e

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = summarize(result)
    by_age = aggregate_by(result, by="age_bucket")
    by_region = aggregate_by(result, by="region")
    by_occ = aggregate_by(result, by="occupation_group")
    by_political = aggregate_by(result, by="political_lean")

    receipt = receipt or receipt_for_run(result.n, result.elapsed_s)

    # ----- Korea map (top, full width) -----
    korea_fig = build_korea_map(by_region)
    korea_html = korea_fig.to_html(
        include_plotlyjs="cdn", full_html=False, div_id="korea-map",
    )

    # ----- Demographic 2x2 -----
    fig = make_subplots(
        rows=2, cols=2,
        specs=[[{"type": "bar"}, {"type": "bar"}],
               [{"type": "bar"}, {"type": "bar"}]],
        subplot_titles=(
            "연령대별 반응", "지역별 반응 (상위 10)",
            "직업군별 반응", "정치 성향별 반응",
        ),
        horizontal_spacing=0.12, vertical_spacing=0.20,
    )
    _stacked_sentiment_bar(fig, by_age, row=1, col=1, sort_groups=_AGE_ORDER)
    _stacked_sentiment_bar(fig, by_region[:10], row=1, col=2)
    _stacked_sentiment_bar(fig, by_occ, row=2, col=1)
    _stacked_sentiment_bar(fig, by_political, row=2, col=2, sort_groups=_POL_ORDER)

    fig.update_layout(
        barmode="stack",
        height=820,
        showlegend=True,
        legend=dict(orientation="h", y=-0.10, x=0.5, xanchor="center",
                    font=dict(color="#5b5347", size=12)),
        font=dict(family="Inter, 'Noto Sans KR', sans-serif",
                  color="#1f1a13"),
        margin=dict(t=50, b=80, l=60, r=20),
        paper_bgcolor="#f5efe1",
        plot_bgcolor="#f5efe1",
    )
    fig.update_yaxes(title_text="", range=[0, 100], gridcolor="#d8cdb3",
                     color="#8a8175", showline=True, linecolor="#d8cdb3",
                     zeroline=False)
    fig.update_xaxes(gridcolor="#d8cdb3", color="#5b5347",
                     showline=True, linecolor="#d8cdb3")
    for ann in fig.layout.annotations:
        ann.font = dict(size=13, color="#1f1a13", family="Noto Serif KR, serif")

    bars_html = fig.to_html(include_plotlyjs=False, full_html=False, div_id="dem-bars")

    # ----- People grid -----
    people_html = render_people_grid_html(result, max_display=400)

    # ----- Annotations (finding-style captions) -----
    map_finding = _finding_caption(by_region, label="지역", min_n=3)
    bars_finding = _bars_finding_caption(by_age, by_occ, by_political)

    # ----- HTML compose -----
    hero_html = _hero_card_html(result, summary, receipt, model)
    quotes_html = _quotes_html(by_age, by_occ)
    source_html = _source_box_html(result)

    html = _PAGE_TEMPLATE.format(
        title=title,
        scenario=result.scenario,
        n_label=f"{result.n:,}",
        source_box=source_html,
        hero=hero_html,
        korea_map=korea_html,
        map_finding=map_finding,
        people_grid=people_html,
        bars=bars_html,
        bars_finding=bars_finding,
        quotes=quotes_html,
    )
    out_path.write_text(html, encoding="utf-8")
    logger.info("Dashboard saved to %s", out_path)
    return out_path


_AGE_ORDER = ["10대", "20대", "30대", "40대", "50대", "60대", "70대+"]
_POL_ORDER = ["progressive", "moderate", "conservative"]


def _stacked_sentiment_bar(fig, rows, *, row, col, sort_groups: list[str] | None = None):
    if sort_groups:
        order = {g: i for i, g in enumerate(sort_groups)}
        rows = sorted(rows, key=lambda r: order.get(r.group, 999))

    import plotly.graph_objects as go

    groups = [r.group for r in rows]
    fig.add_trace(go.Bar(
        x=groups, y=[r.supportive_pct for r in rows], name="찬성",
        marker_color=_SENTIMENT_COLORS["supportive"],
        showlegend=(row == 1 and col == 1), legendgroup="sup",
        hovertemplate="<b>%{x}</b><br>찬성: %{y:.1f}%<extra></extra>",
    ), row=row, col=col)
    fig.add_trace(go.Bar(
        x=groups, y=[r.neutral_pct for r in rows], name="중립",
        marker_color=_SENTIMENT_COLORS["neutral"],
        showlegend=(row == 1 and col == 1), legendgroup="neu",
        hovertemplate="<b>%{x}</b><br>중립: %{y:.1f}%<extra></extra>",
    ), row=row, col=col)
    fig.add_trace(go.Bar(
        x=groups, y=[r.opposed_pct for r in rows], name="반대",
        marker_color=_SENTIMENT_COLORS["opposed"],
        showlegend=(row == 1 and col == 1), legendgroup="opp",
        hovertemplate="<b>%{x}</b><br>반대: %{y:.1f}%<extra></extra>",
    ), row=row, col=col)


def _source_box_html(result: ScenarioResult) -> str:
    """Render a small attribution box when the scenario came from a fetched article.

    Returns an empty string when `result.source_url` is None (i.e. classic scenario
    text mode), so the same template works for both paths.
    """
    url = result.source_url
    brief = result.brief
    if not url:
        return ""

    import html as _html
    from urllib.parse import urlparse

    safe_url = _html.escape(url)
    parsed = urlparse(url)
    display = (parsed.netloc + parsed.path).rstrip("/") or url
    if len(display) > 80:
        display = display[:77] + "…"
    display = _html.escape(display)

    warn_html = ""
    if brief and brief.get("unverified"):
        warn_html = (
            f'<span class="source-warn">검증 실패 {len(brief["unverified"])}개 항목 드롭됨</span>'
        )

    slots_html = ""
    if brief:
        rows = [
            ("행위자", brief.get("actor")),
            ("조치", brief.get("action")),
            ("규모", brief.get("magnitude")),
            ("대상", brief.get("target")),
            ("시점", brief.get("time")),
            ("범위", brief.get("scope")),
        ]
        dl_rows = "".join(
            f"<dt>{label}</dt><dd>{_html.escape(str(value))}</dd>"
            for label, value in rows if value
        )
        if dl_rows:
            slots_html = (
                '<details class="brief-slots">'
                "<summary>구조화된 brief 보기</summary>"
                f"<dl>{dl_rows}</dl>"
                "</details>"
            )

    return (
        '<div class="source-box">'
        '<div class="source-line">'
        '<span class="source-label">출처</span>'
        f'<a href="{safe_url}" target="_blank" rel="noopener">{display}</a>'
        f"{warn_html}"
        "</div>"
        f"{slots_html}"
        "</div>"
    )


def _hero_card_html(result: ScenarioResult, summary, receipt: ComputeReceipt,
                    model: ModelPreset | None) -> str:
    n = result.n
    elapsed = result.elapsed_s

    if elapsed < 60:
        elapsed_str = f"{elapsed:.1f}s"
    elif elapsed < 3600:
        elapsed_str = f"{elapsed/60:.1f}분"
    else:
        elapsed_str = f"{elapsed/3600:.1f}시간"

    net = summary.net_score
    net_color = "#5a7333" if net > 20 else "#9c3a14" if net < -20 else "#8a8175"

    if model:
        model_line = (
            f'<span class="model-badge">{model.display_name}</span>'
            f'<span class="model-meta">{model.params_b:.1f}B params · {model.weight_size_gb:.1f}GB weights</span>'
        )
    else:
        model_line = '<span class="model-badge">로컬 LLM 사용</span>'

    return f"""
<div class="hero">
  <div class="model-strip">
    {model_line}
  </div>
  <div class="hero-row">
    <div class="hero-card">
      <div class="hero-num">{n:,}</div>
      <div class="hero-lbl">표본 수 (명)</div>
    </div>
    <div class="hero-card">
      <div class="hero-num">{elapsed_str}</div>
      <div class="hero-lbl">시뮬레이션 소요 시간</div>
    </div>
    <div class="hero-card net">
      <div class="hero-num" style="color:{net_color};">{net:+.0f}</div>
      <div class="hero-lbl">Net Sentiment</div>
    </div>
  </div>
  <div class="hero-summary">{summary.headline}</div>
</div>
"""


def _quotes_html(by_age, by_occ) -> str:
    parts = [
        '<section class="quotes-section">',
        '<h3>그룹별 대표 반응</h3>',
        '<p class="quotes-sub">각 그룹에서 가장 강도 높은 반응을 인용했습니다 — 화자는 그룹 라벨입니다.</p>',
    ]
    for label, rows in (("연령대", by_age), ("직업군", by_occ)):
        parts.append(f'<h4 class="quotes-facet">{label}</h4>')
        parts.append('<div class="quote-grid">')
        for r in rows[:6]:
            quotes = [q for q in r.sample_quotes[:1] if q]
            if not quotes:
                continue
            net_cls = _net_class(r.net_score)
            parts.append(
                '<figure class="quote-card">'
                f'<blockquote class="quote-body">{quotes[0]}</blockquote>'
                '<figcaption class="quote-foot">'
                f'<span class="quote-speaker">— {r.group}</span>'
                f'<span class="quote-meta">표본 {r.n}명 · 강도 {r.avg_intensity:.0f}</span>'
                f'<span class="quote-chip {net_cls}">net {r.net_score:+.0f}</span>'
                '</figcaption>'
                '</figure>'
            )
        parts.append('</div>')
    parts.append('</section>')
    return "\n".join(parts)


def _net_class(net: float) -> str:
    if net > 20:
        return "supp"
    if net < -20:
        return "opp"
    return "neu"


def _finding_caption(rows, *, label: str, min_n: int = 3) -> str:
    """Pull the most positive and most negative groups into a single caption."""
    eligible = [r for r in rows if r.n >= min_n]
    if not eligible:
        return ""
    most_pos = max(eligible, key=lambda r: r.net_score)
    most_neg = min(eligible, key=lambda r: r.net_score)

    if most_pos.group == most_neg.group:
        r = most_pos
        return (
            f'<span class="finding-pin">FINDING</span> '
            f'{label} <b>{r.group}</b>는 net <b style="color:{_net_color(r.net_score)};">'
            f'{r.net_score:+.0f}</b> (표본 {r.n}명) — 단일 그룹 분포'
        )

    return (
        f'<span class="finding-pin">FINDING</span> '
        f'가장 부정적: {label} <b>{most_neg.group}</b> '
        f'<span style="color:#9c3a14;">net {most_neg.net_score:+.0f}</span> '
        f'(표본 {most_neg.n}명) · '
        f'가장 우호적: {label} <b>{most_pos.group}</b> '
        f'<span style="color:{_net_color(most_pos.net_score)};">net {most_pos.net_score:+.0f}</span> '
        f'(표본 {most_pos.n}명)'
    )


def _bars_finding_caption(by_age, by_occ, by_political) -> str:
    """Surface the strongest demographic split across age/occupation/politics."""
    candidates = []
    for label, rows in (("연령대", by_age), ("직업군", by_occ), ("정치성향", by_political)):
        eligible = [r for r in rows if r.n >= 3]
        if len(eligible) < 2:
            continue
        spread = max(r.net_score for r in eligible) - min(r.net_score for r in eligible)
        candidates.append((spread, label, eligible))

    if not candidates:
        return ""

    spread, label, eligible = max(candidates, key=lambda c: c[0])
    most_neg = min(eligible, key=lambda r: r.net_score)
    most_pos = max(eligible, key=lambda r: r.net_score)
    return (
        f'<span class="finding-pin">SPLIT</span> '
        f'{label} 차이가 가장 큼 — '
        f'<b>{most_neg.group}</b> <span style="color:#9c3a14;">net {most_neg.net_score:+.0f}</span> vs '
        f'<b>{most_pos.group}</b> <span style="color:{_net_color(most_pos.net_score)};">net {most_pos.net_score:+.0f}</span> '
        f'(격차 {spread:.0f}p)'
    )


def _net_color(net: float) -> str:
    if net > 20:
        return "#5a7333"
    if net < -20:
        return "#9c3a14"
    return "#8a8175"


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;700&family=Noto+Serif+KR:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --font-sans: "Inter", "Noto Sans KR", "Pretendard", -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif;
    --font-serif: "Noto Serif KR", "Iowan Old Style", Georgia, serif;
    --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
    --bg: #f5efe1;
    --panel: #f5efe1;
    --ink: #1f1a13;
    --ink-soft: #5b5347;
    --ink-mute: #8a8175;
    --rule: #d8cdb3;
    --accent: #8b5a1f;
    --pos: #5a7333;
    --neg: #9c3a14;
    --neu: #8a8175;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: var(--font-sans);
    background: var(--bg);
    color: var(--ink);
    margin: 0;
    padding: 56px 32px 72px;
    max-width: 1100px;
    margin: 0 auto;
    -webkit-font-smoothing: antialiased;
  }}
  h1 {{
    font-family: var(--font-serif);
    font-size: 2.4rem; font-weight: 700;
    margin: 0 0 4px 0; letter-spacing: -0.01em;
    color: var(--ink);
    line-height: 1.2;
  }}
  h1 .eyebrow {{
    display: block;
    font-family: var(--font-sans);
    font-size: 0.72rem; font-weight: 500;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--ink-mute); margin-bottom: 14px;
  }}
  h3 {{
    margin: 48px 0 14px 0; color: var(--ink);
    font-family: var(--font-serif);
    font-size: 1.35rem; font-weight: 600;
    letter-spacing: -0.005em;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--rule);
  }}
  h4 {{
    margin: 26px 0 10px 0; color: var(--ink-soft);
    font-size: 0.72rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.18em;
  }}
  .lede {{
    margin: 0 0 36px 0;
    color: var(--ink-soft);
    font-family: var(--font-serif);
    font-size: 1.05rem;
    line-height: 1.7;
    max-width: 760px;
  }}
  .scenario {{
    margin: 28px 0 40px 0;
    padding: 18px 0 4px 0;
    border-top: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    color: var(--ink);
    font-family: var(--font-serif);
    font-size: 1.12rem;
    line-height: 1.75;
    font-weight: 400;
  }}
  .scenario b {{
    display: block;
    font-family: var(--font-sans); font-weight: 600;
    font-size: 0.7rem; letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--ink-mute); margin-bottom: 8px;
  }}

  /* === SOURCE BOX (only shown when scenario came from a fetched article) === */
  .source-box {{
    margin: -28px 0 40px 0;
    padding: 14px 0 10px 0;
    border-bottom: 1px solid var(--rule);
    font-family: var(--font-mono);
    font-size: 0.78rem;
    color: var(--ink-soft);
  }}
  .source-line {{ display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }}
  .source-line .source-label {{
    font-weight: 600;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--ink-mute);
  }}
  .source-line a {{
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 3px;
    text-decoration-thickness: 1px;
    word-break: break-all;
  }}
  .source-line a:hover {{ color: var(--ink); }}
  .source-line .source-title {{ color: var(--ink); font-style: italic; }}
  .source-line .source-warn {{ color: var(--neg); }}
  details.brief-slots {{ margin-top: 10px; }}
  details.brief-slots summary {{
    cursor: pointer;
    color: var(--ink-mute);
    user-select: none;
  }}
  details.brief-slots summary:hover {{ color: var(--accent); }}
  details.brief-slots dl {{
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 4px 18px;
    margin: 10px 0 4px 0;
    font-family: var(--font-sans);
    font-size: 0.85rem;
  }}
  details.brief-slots dt {{
    color: var(--ink-mute);
    letter-spacing: 0.06em;
  }}
  details.brief-slots dd {{
    margin: 0;
    color: var(--ink);
  }}

  /* === HERO === */
  .hero {{ margin: 0 0 12px 0; }}
  .model-strip {{
    display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
    margin-bottom: 0; padding: 10px 0;
    border-bottom: 1px solid var(--rule);
    font-family: var(--font-mono);
  }}
  .model-badge {{
    font-weight: 500; color: var(--ink); font-size: 0.82rem;
    letter-spacing: -0.01em;
  }}
  .model-meta {{
    color: var(--ink-mute); font-size: 0.74rem;
  }}
  .hero-row {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
  }}
  @media (max-width: 720px) {{ .hero-row {{ grid-template-columns: 1fr; }} }}
  .hero-card {{
    padding: 24px 20px 22px 0;
    text-align: left;
    border-right: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
  }}
  .hero-card:last-child {{ border-right: none; }}
  .hero-card:nth-child(2), .hero-card:nth-child(3) {{ padding-left: 24px; }}
  .hero-num {{
    font-family: var(--font-serif);
    font-size: 2.6rem; font-weight: 600; letter-spacing: -0.025em;
    color: var(--ink); line-height: 1.05; margin-bottom: 8px;
    font-variant-numeric: tabular-nums;
  }}
  .hero-lbl {{
    color: var(--ink-mute); font-size: 0.7rem; line-height: 1.5;
    text-transform: uppercase; letter-spacing: 0.16em;
    font-weight: 500;
  }}
  .hero-summary {{
    margin: 18px 0 0 0;
    color: var(--ink-soft);
    font-family: var(--font-serif);
    font-size: 1.0rem;
    line-height: 1.7;
  }}

  /* === Sections === */
  .map-section, .bars-section {{
    margin-top: 0;
  }}
  .finding {{
    margin: 4px 0 18px 0;
    padding: 12px 0 12px 16px;
    border-left: 2px solid var(--accent);
    color: var(--ink-soft);
    font-size: 0.92rem;
    line-height: 1.65;
  }}
  .finding b {{ color: var(--ink); font-weight: 600; }}
  .finding-pin {{
    display: inline-block;
    margin-right: 12px;
    color: var(--accent);
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 500;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }}

  /* === Quotes (editorial cards) === */
  .quotes-section {{ margin-top: 0; }}
  .quotes-sub {{
    color: var(--ink-mute); font-size: 0.92rem;
    margin: 4px 0 24px 0; line-height: 1.65;
    font-family: var(--font-serif);
  }}
  .quotes-facet {{
    margin: 32px 0 16px 0; color: var(--ink-mute);
    font-size: 0.7rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.22em;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--rule);
  }}
  .quote-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 0;
  }}
  .quote-card {{
    margin: 0;
    padding: 22px 22px 18px 0;
    border-bottom: 1px solid var(--rule);
    position: relative;
    display: flex; flex-direction: column;
  }}
  .quote-card + .quote-card {{ padding-left: 22px; border-left: 1px solid var(--rule); }}
  .quote-body {{
    margin: 0 0 14px 0;
    font-family: var(--font-serif);
    font-size: 1.02rem;
    line-height: 1.7;
    color: var(--ink);
    flex: 1;
  }}
  .quote-body::before {{
    content: '\\201C';
    font-family: var(--font-serif);
    font-size: 1.3rem;
    color: var(--ink-mute);
    margin-right: 2px;
  }}
  .quote-body::after {{
    content: '\\201D';
    font-family: var(--font-serif);
    color: var(--ink-mute);
    margin-left: 2px;
  }}
  .quote-foot {{
    display: flex; align-items: baseline; flex-wrap: wrap;
    gap: 10px; padding-top: 10px;
  }}
  .quote-speaker {{
    color: var(--ink); font-weight: 600; font-size: 0.92rem;
    font-family: var(--font-sans);
  }}
  .quote-meta {{
    color: var(--ink-mute); font-size: 0.74rem;
    font-family: var(--font-mono);
  }}
  .quote-chip {{
    margin-left: auto;
    font-size: 0.74rem; font-weight: 500;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
  }}
  .quote-chip.supp {{ color: var(--pos); }}
  .quote-chip.opp  {{ color: var(--neg); }}
  .quote-chip.neu  {{ color: var(--neu); }}

  footer {{
    margin-top: 64px;
    padding-top: 22px;
    border-top: 1px solid var(--rule);
    color: var(--ink-mute);
    font-size: 0.78rem;
    font-family: var(--font-mono);
    line-height: 1.7;
  }}
  footer a {{ color: var(--ink-soft); text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 3px; }}
  footer a:hover {{ color: var(--accent); }}
</style>
</head>
<body>
  <header>
    <h1>
      <span class="eyebrow">KoreaSim · Scenario Dashboard</span>
      한국 시민 {n_label}명에게 물었습니다
    </h1>
    <p class="lede">
      인구통계 기반으로 합성된 한국인 페르소나에게 동일한 시나리오를 던지고,
      찬반·중립의 분포와 그 배경을 살펴봅니다.
    </p>
    <div class="scenario"><b>제시된 시나리오</b>{scenario}</div>
    {source_box}
  </header>

  {hero}

  <section class="map-section">
    <h3>지역별 분포 — 17개 광역시도</h3>
    <div class="finding">{map_finding}</div>
    {korea_map}
  </section>

  <section>
    <h3>개개인의 반응</h3>
    {people_grid}
  </section>

  <section class="bars-section">
    <h3>인구통계 분해</h3>
    <div class="finding">{bars_finding}</div>
    {bars}
  </section>

  {quotes}

  <footer>
    페르소나 출처:
    <a href="https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea">Nemotron-Personas-Korea</a> ·
    소스:
    <a href="https://github.com/winhun98/koreasim">github.com/winhun98/koreasim</a>
  </footer>
</body>
</html>
"""


# ----- Text-mode report (no plotly required) ---------------------------------


def render_text_report(result: ScenarioResult, receipt: ComputeReceipt | None = None) -> str:
    summary = summarize(result)
    by_age = aggregate_by(result, by="age_bucket")
    by_region = aggregate_by(result, by="region")
    by_occ = aggregate_by(result, by="occupation_group")
    receipt = receipt or receipt_for_run(result.n, result.elapsed_s)

    try:
        from io import StringIO

        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        buf = StringIO()
        console = Console(file=buf, force_terminal=True, width=110)

        # Hero panel — scale-first.
        hero = (
            f"[bold]{result.n:,}[/bold] demographically-grounded Korean agents · "
            f"[cyan]{result.elapsed_s:.1f}s[/cyan] on this machine "
            f"([dim]{receipt.agents_per_sec:.0f} agents/sec[/dim])\n\n"
            f"[bold cyan]시나리오[/bold cyan]\n{result.scenario}\n\n"
            f"[bold]요약[/bold] · {summary.headline}"
        )
        console.print(Panel.fit(hero, title="🇰🇷 KoreaSim", border_style="cyan"))

        for label, rows, sort in (
            ("연령대별 반응", by_age, _AGE_ORDER),
            ("지역별 반응 (상위 10)", by_region[:10], None),
            ("직업군별 반응", by_occ, None),
        ):
            if sort:
                order = {g: i for i, g in enumerate(sort)}
                rows = sorted(rows, key=lambda r: order.get(r.group, 999))
            t = Table(title=label, show_lines=False, expand=True)
            t.add_column("그룹", style="bold")
            t.add_column("N", justify="right")
            t.add_column("찬성%", justify="right", style="green")
            t.add_column("중립%", justify="right", style="white")
            t.add_column("반대%", justify="right", style="red")
            t.add_column("net", justify="right")
            t.add_column("강도", justify="right")
            for r in rows:
                t.add_row(
                    r.group, f"{r.n:,}",
                    f"{r.supportive_pct:.0f}",
                    f"{r.neutral_pct:.0f}",
                    f"{r.opposed_pct:.0f}",
                    f"{r.net_score:+.0f}",
                    f"{r.avg_intensity:.0f}",
                )
            console.print(t)
        return buf.getvalue()
    except ImportError:
        lines = [
            f"=== KoreaSim — {result.n:,} agents · {result.elapsed_s:.1f}s ===\n"
            f"시나리오: {result.scenario}\n{summary.headline}\n"
        ]
        for label, rows in (("연령대별", by_age), ("직업군별", by_occ)):
            lines.append(f"\n[{label}]")
            for r in rows:
                lines.append(
                    f"  {r.group:>10s}  N={r.n:<5d}  찬성={r.supportive_pct:5.1f}%  "
                    f"중립={r.neutral_pct:5.1f}%  반대={r.opposed_pct:5.1f}%  "
                    f"net={r.net_score:+6.1f}  강도={r.avg_intensity:.0f}"
                )
        return "\n".join(lines)
