"""Korea province choropleth — colors each 광역시도 polygon by net sentiment.

Uses a simplified GeoJSON of South Korea's 17 provinces (~120KB) bundled at
`koreasim/viz/data/skorea-provinces-simple.json`. Source: southkorea-maps
(MIT licensed). The GeoJSON ships the older 강원도 / 전라북도 names — we map
KoreaSim's current 특별자치도 names to those for the join.

Net sentiment maps to a divergent red↔gray↔green colorscale; sample size is
shown in the hover tooltip and as a small annotation badge per region.
"""

from __future__ import annotations

import json
from pathlib import Path

# 광역시도 → (lat, lon). Approximate centroids for label placement.
PROVINCE_COORDS: dict[str, tuple[float, float]] = {
    "서울특별시":       (37.5665, 126.9780),
    "부산광역시":       (35.1796, 129.0756),
    "대구광역시":       (35.8714, 128.6014),
    "인천광역시":       (37.4563, 126.7052),
    "광주광역시":       (35.1595, 126.8526),
    "대전광역시":       (36.3504, 127.3845),
    "울산광역시":       (35.5384, 129.3114),
    "세종특별자치시":   (36.4801, 127.2890),
    "경기도":           (37.4138, 127.5183),
    "강원특별자치도":   (37.8228, 128.1555),
    "충청북도":         (36.6357, 127.4912),
    "충청남도":         (36.5184, 126.8000),
    "전북특별자치도":   (35.7175, 127.1530),
    "전라남도":         (34.8679, 126.9910),
    "경상북도":         (36.4919, 128.8889),
    "경상남도":         (35.4606, 128.2132),
    "제주특별자치도":   (33.4996, 126.5312),
}

# KoreaSim canonical name → GeoJSON property name (older 도명 in 2018 source).
_NAME_TO_GEOJSON: dict[str, str] = {
    "강원특별자치도":  "강원도",
    "전북특별자치도":  "전라북도",
}

_GEOJSON_PATH = Path(__file__).parent / "data" / "skorea-provinces-simple.json"


def _load_geojson() -> dict:
    with open(_GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _to_geojson_name(name: str) -> str:
    return _NAME_TO_GEOJSON.get(name, name)


def build_korea_map(rows, *, height: int = 540):
    """Build a plotly choropleth Figure showing per-province net sentiment.

    Args:
        rows: Iterable[AggregateRow] — output of `aggregate_by(result, "region")`.
        height: Figure height in pixels.
    """
    import plotly.graph_objects as go

    geojson = _load_geojson()

    locations: list[str] = []
    values: list[float] = []
    texts: list[str] = []
    customdata: list[str] = []

    rows_by_name = {r.group: r for r in rows}
    for canonical in PROVINCE_COORDS.keys():
        r = rows_by_name.get(canonical)
        geo_name = _to_geojson_name(canonical)
        locations.append(geo_name)
        if r is None:
            values.append(0.0)
            texts.append(f"<b>{canonical}</b><br>표본 없음")
            customdata.append(canonical)
            continue
        values.append(r.net_score)
        customdata.append(canonical)
        texts.append(
            f"<b>{canonical}</b><br>"
            f"표본 {r.n}명<br>"
            f"찬성 {r.supportive_pct:.0f}% · 중립 {r.neutral_pct:.0f}% · "
            f"반대 {r.opposed_pct:.0f}%<br>"
            f"net <b>{r.net_score:+.0f}</b> · 강도 {r.avg_intensity:.0f}"
        )

    fig = go.Figure(
        go.Choropleth(
            geojson=geojson,
            featureidkey="properties.name",
            locations=locations,
            z=values,
            zmin=-100,
            zmax=100,
            text=texts,
            customdata=customdata,
            hovertemplate="%{text}<extra></extra>",
            colorscale=[
                [0.0, "#9c3a14"],
                [0.5, "#ebe1c8"],
                [1.0, "#5a7333"],
            ],
            marker=dict(line=dict(color="#b8a98a", width=0.5)),
            colorbar=dict(
                title=dict(text="net", side="right", font=dict(color="#5b5347", size=11)),
                tickfont=dict(color="#5b5347", size=10),
                thickness=8,
                len=0.5,
                y=0.5,
                x=1.0,
                bgcolor="rgba(0,0,0,0)",
                outlinewidth=0,
            ),
            showscale=True,
        )
    )

    label_lats: list[float] = []
    label_lons: list[float] = []
    label_texts: list[str] = []
    for canonical, (lat, lon) in PROVINCE_COORDS.items():
        r = rows_by_name.get(canonical)
        if r is None or r.n < 3:
            continue
        short = canonical.replace("특별자치도", "").replace("특별자치시", "")
        short = short.replace("광역시", "").replace("특별시", "")
        label_lats.append(lat)
        label_lons.append(lon)
        label_texts.append(f"{short}<br>{r.net_score:+.0f}")

    if label_texts:
        fig.add_trace(
            go.Scattergeo(
                lat=label_lats,
                lon=label_lons,
                text=label_texts,
                mode="text",
                textfont=dict(size=9, color="#1f1a13",
                              family="Inter, 'Noto Sans KR', sans-serif"),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    fig.update_geos(
        visible=False,
        projection_type="mercator",
        center=dict(lat=36.0, lon=127.8),
        lataxis=dict(range=[33.0, 39.0]),
        lonaxis=dict(range=[124.5, 131.5]),
        showframe=False,
        bgcolor="#f5efe1",
    )
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#f5efe1",
        font=dict(color="#1f1a13"),
    )
    return fig
