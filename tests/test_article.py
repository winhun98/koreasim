"""Article fetch + extraction + caching tests."""

from __future__ import annotations

import pytest

from koreasim.scenario.article import (
    ArticleExtractionError,
    ArticleFetchError,
    ArticleSource,
    fetch_article,
)

# Long enough to pass the trafilatura `>= 200 chars` extraction floor.
_FULL_HTML = """<!doctype html>
<html lang="ko"><head>
<title>자동차 보험료 30% 인상</title>
<meta charset="utf-8">
</head><body>
<header><nav>홈 / 뉴스 / 경제</nav></header>
<article>
<h1>자동차 보험료 30% 인상 발표</h1>
<p class="byline">홍길동 기자 · 2026-04-29</p>
<p>정부가 자동차 보험료를 내년 1월부터 평균 30% 인상한다고 발표했습니다.
운전자 1,200만 명이 영향을 받을 것으로 예상됩니다.
김모 운전자는 "부담이 너무 크다"며 반대 입장을 밝혔습니다.
전문가들은 손해율 상승을 그 배경으로 지목했습니다.
보험료 인상은 2026년 1월 1일부터 단계적으로 적용될 예정입니다.
정부 관계자는 추가 보완책도 검토 중이라고 밝혔습니다.</p>
</article>
<footer>copyright 2026</footer>
</body></html>"""


async def test_fetch_article_extracts_text(httpx_mock, tmp_path):
    httpx_mock.add_response(
        url="https://example.com/news/1",
        text=_FULL_HTML,
        headers={"content-type": "text/html; charset=utf-8"},
    )
    article = await fetch_article("https://example.com/news/1", cache_dir=tmp_path)
    assert isinstance(article, ArticleSource)
    assert article.url == "https://example.com/news/1"
    assert "보험료" in article.text
    assert "30%" in article.text
    assert len(article.text) >= 200
    # Boilerplate should be stripped.
    assert "copyright 2026" not in article.text


async def test_fetch_article_caches_to_disk(httpx_mock, tmp_path):
    httpx_mock.add_response(url="https://example.com/news/2", text=_FULL_HTML)
    a1 = await fetch_article("https://example.com/news/2", cache_dir=tmp_path)
    # Don't register a 2nd response — cache must serve it.
    a2 = await fetch_article("https://example.com/news/2", cache_dir=tmp_path)
    assert a1.text == a2.text
    assert a1.url == a2.url
    # Cache file should exist on disk.
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1


async def test_fetch_article_force_bypasses_cache(httpx_mock, tmp_path):
    v1_html = _FULL_HTML.replace("30% 인상한다고", "30% 인상한다고 (v1)")
    v2_html = _FULL_HTML.replace("30% 인상한다고", "30% 인상한다고 (v2)")
    httpx_mock.add_response(url="https://example.com/news/3", text=v1_html)
    a1 = await fetch_article("https://example.com/news/3", cache_dir=tmp_path)
    assert "(v1)" in a1.text

    httpx_mock.add_response(url="https://example.com/news/3", text=v2_html)
    a2 = await fetch_article("https://example.com/news/3", cache_dir=tmp_path, force=True)
    assert "(v2)" in a2.text


async def test_fetch_article_raises_on_404(httpx_mock, tmp_path):
    httpx_mock.add_response(url="https://example.com/dead", status_code=404)
    with pytest.raises(ArticleFetchError):
        await fetch_article("https://example.com/dead", cache_dir=tmp_path)


async def test_fetch_article_raises_on_thin_extraction(httpx_mock, tmp_path):
    httpx_mock.add_response(
        url="https://example.com/empty",
        text="<html><body><p>짧음</p></body></html>",
    )
    with pytest.raises(ArticleExtractionError):
        await fetch_article("https://example.com/empty", cache_dir=tmp_path)


def test_article_source_to_dict_round_trip():
    a = ArticleSource(
        url="https://x.com/y", text="본문 내용입니다.",
        title="제목", fetched_at="2026-04-29T00:00:00",
    )
    d = a.to_dict()
    assert d["url"] == "https://x.com/y"
    assert d["text"] == "본문 내용입니다."
    a2 = ArticleSource.from_dict(d)
    assert a2 == a
