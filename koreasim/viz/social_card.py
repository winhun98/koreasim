"""Auto-generate a 1200×630 social card PNG suitable for X / OG previews.

The card is the single asset that has to do all the heavy lifting on social
media: a casual scroll-by viewer should immediately see the *scale* claim and
the headline finding without opening the dashboard.

Layout:
  ┌──────────────────────────────────────────────────────────┐
  │  🇰🇷  KoreaSim                                              │
  │                                                              │
  │     10,247  Korean agents                                    │
  │     simulated in 2.3 minutes — on a laptop                   │
  │                                                              │
  │     [scenario one-liner]                                     │
  │                                                              │
  │   net +12 (찬성 38% / 중립 36% / 반대 26%)                    │
  │   ▓▓▓▓▓░░░░░░░░░░░░░ stacked bar                             │
  │                                                              │
  │  BitNet 1.58-bit · local laptop                              │
  └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

from koreasim.analysis.aggregate import summarize
from koreasim.analysis.compute import ComputeReceipt, receipt_for_run
from koreasim.llm.models import ModelPreset
from koreasim.scenario.runner import ScenarioResult

logger = logging.getLogger(__name__)


def build_social_card(
    result: ScenarioResult,
    out_path: str | Path,
    *,
    receipt: ComputeReceipt | None = None,
    model: ModelPreset | None = None,
    width: int = 1200,
    height: int = 630,
) -> Path:
    """Render a 1200×630 PNG suitable for X / OG. Requires plotly + kaleido."""
    try:
        import plotly.graph_objects as go
    except ImportError as e:
        raise ImportError(
            "Social card requires the optional `viz` extra: pip install koreasim[viz]"
        ) from e

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary = summarize(result)
    receipt = receipt or receipt_for_run(result.n, result.elapsed_s)

    elapsed = result.elapsed_s
    if elapsed < 60:
        elapsed_str = f"{elapsed:.1f}s"
    elif elapsed < 3600:
        elapsed_str = f"{elapsed/60:.1f} min"
    else:
        elapsed_str = f"{elapsed/3600:.1f} h"

    # Wrap scenario into 2 short lines (truncate to ~120 chars total).
    scenario_short = result.scenario
    if len(scenario_short) > 120:
        scenario_short = scenario_short[:117].rstrip() + "…"
    wrapped = "<br>".join(textwrap.wrap(scenario_short, width=52)[:2])

    net = summary.net_score
    net_color = "#4ade80" if net > 20 else "#f87171" if net < -20 else "#fbbf24"
    net_sign = "+" if net >= 0 else ""

    # Stacked bar at y≈0.22 (above the footer text). Thin 0.06-tall track.
    bar_y = 0.22
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[summary.supportive_pct], y=[bar_y], orientation="h",
        marker_color="#22c55e", name="찬성", showlegend=False,
        hoverinfo="skip", width=0.06,
    ))
    fig.add_trace(go.Bar(
        x=[summary.neutral_pct], y=[bar_y], orientation="h",
        marker_color="#94a3b8", name="중립", showlegend=False,
        hoverinfo="skip", width=0.06,
    ))
    fig.add_trace(go.Bar(
        x=[summary.opposed_pct], y=[bar_y], orientation="h",
        marker_color="#ef4444", name="반대", showlegend=False,
        hoverinfo="skip", width=0.06,
    ))

    if model:
        model_label = f"📦 {model.display_name} · {model.params_b:.0f}B · 1.58-bit"
    else:
        model_label = "📦 BitNet 1.58-bit"

    annotations = [
        # Title
        dict(
            x=0.04, y=0.93, xref="paper", yref="paper",
            text="🇰🇷  <b>KoreaSim</b>",
            showarrow=False,
            font=dict(size=36, color="#38bdf8"),
            xanchor="left", yanchor="top",
        ),
        # Model badge (top-right corner)
        dict(
            x=0.96, y=0.93, xref="paper", yref="paper",
            text=model_label,
            showarrow=False,
            font=dict(size=18, color="#c7d2fe"),
            xanchor="right", yanchor="top",
            bgcolor="rgba(67, 56, 202, 0.18)",
            bordercolor="#4338ca",
            borderwidth=1,
            borderpad=8,
        ),
        # Big number
        dict(
            x=0.04, y=0.78, xref="paper", yref="paper",
            text=f"<b>{result.n:,}</b>",
            showarrow=False,
            font=dict(size=120, color="#f1f5f9"),
            xanchor="left", yanchor="top",
        ),
        # "Korean agents · in N min · on a laptop"
        dict(
            x=0.04, y=0.55, xref="paper", yref="paper",
            text="demographically-grounded Korean agents",
            showarrow=False,
            font=dict(size=24, color="#cbd5e1"),
            xanchor="left", yanchor="top",
        ),
        dict(
            x=0.04, y=0.49, xref="paper", yref="paper",
            text=f"simulated in <b>{elapsed_str}</b> — on a laptop",
            showarrow=False,
            font=dict(size=22, color="#94a3b8"),
            xanchor="left", yanchor="top",
        ),
        # Scenario
        dict(
            x=0.04, y=0.38, xref="paper", yref="paper",
            text=f"<i>{wrapped}</i>",
            showarrow=False,
            font=dict(size=18, color="#e0f2fe"),
            xanchor="left", yanchor="top",
        ),
        # Net score badge
        dict(
            x=0.96, y=0.78, xref="paper", yref="paper",
            text=f"net <b>{net_sign}{net:.0f}</b>",
            showarrow=False,
            font=dict(size=70, color=net_color),
            xanchor="right", yanchor="top",
        ),
        dict(
            x=0.96, y=0.61, xref="paper", yref="paper",
            text=(f"찬성 <b>{summary.supportive_pct:.0f}%</b>  ·  "
                  f"중립 {summary.neutral_pct:.0f}%  ·  "
                  f"반대 <b>{summary.opposed_pct:.0f}%</b>"),
            showarrow=False,
            font=dict(size=18, color="#cbd5e1"),
            xanchor="right", yanchor="top",
        ),
        # Footer — split into 3 separate annotations so each segment can carry
        # its own color (plotly annotations don't honor inline-styled spans).
        dict(
            x=0.04, y=0.07, xref="paper", yref="paper",
            text="Qwen3 8B (Q4_K_M) · Ollama · local laptop",
            showarrow=False,
            font=dict(size=20, color="#94a3b8"),
            xanchor="left", yanchor="bottom",
        ),
        dict(
            x=0.96, y=0.07, xref="paper", yref="paper",
            text="github.com/winhun98/koreasim",
            showarrow=False,
            font=dict(size=15, color="#64748b"),
            xanchor="right", yanchor="bottom",
        ),
    ]

    fig.update_layout(
        width=width, height=height,
        barmode="stack",
        paper_bgcolor="#0b0f17",
        plot_bgcolor="#0b0f17",
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
        annotations=annotations,
        xaxis=dict(visible=False, range=[0, 100]),
        yaxis=dict(visible=False, range=[0, 1]),
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"),
    )

    fig.write_image(str(out_path), format="png", width=width, height=height, scale=2)
    logger.info("Social card saved to %s", out_path)
    return out_path
