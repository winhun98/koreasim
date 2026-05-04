"""Dashboard / visualization helpers (plotly-based, optional dep)."""

from koreasim.viz.dashboard import build_dashboard, render_text_report
from koreasim.viz.korea_map import build_korea_map
from koreasim.viz.people_grid import render_people_grid_html
from koreasim.viz.social_card import build_social_card

__all__ = [
    "build_dashboard",
    "render_text_report",
    "build_korea_map",
    "render_people_grid_html",
    "build_social_card",
]
