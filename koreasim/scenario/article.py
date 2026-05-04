"""Article fetcher — turn a news URL into clean text for brief generation.

Two-stage pipeline:
1. `httpx` fetches the raw HTML (async, with sane timeouts and a UA header).
2. `trafilatura.extract()` strips boilerplate and returns the article body.

A small JSON disk cache keyed by SHA-256 of the URL avoids re-fetching the same
article during iteration. Cache directory defaults to `~/.cache/koreasim/articles/`
and can be overridden by the `KOREASIM_CACHE_DIR` env var or the `cache_dir`
parameter (test fixtures use this).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import trafilatura

logger = logging.getLogger(__name__)

# Korean news sites often block default httpx UA. Mimic a desktop browser.
_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_MIN_TEXT_LEN = 200


class ArticleFetchError(Exception):
    """Network / HTTP-level failure (timeout, non-2xx status, DNS, ...)."""


class ArticleExtractionError(Exception):
    """HTML fetched OK but trafilatura found no usable article body."""


@dataclass(frozen=True)
class ArticleSource:
    url: str
    text: str
    title: str | None
    fetched_at: str  # ISO-8601 UTC

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "text": self.text,
            "title": self.title,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ArticleSource:
        return cls(
            url=d["url"],
            text=d["text"],
            title=d.get("title"),
            fetched_at=d["fetched_at"],
        )


def _default_cache_dir() -> Path:
    env = os.environ.get("KOREASIM_CACHE_DIR")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "koreasim" / "articles"


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _cache_path(url: str, cache_dir: Path) -> Path:
    return cache_dir / f"{_cache_key(url)}.json"


def _load_cache(path: Path) -> ArticleSource | None:
    if not path.exists():
        return None
    try:
        return ArticleSource.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Cache file %s unreadable (%s) — refetching.", path, e)
        return None


def _save_cache(path: Path, article: ArticleSource) -> None:
    """Atomic write: temp file + rename. Avoids partial-write corruption when
    two parallel fetches of the same URL race against each other."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(article.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


async def fetch_article(
    url: str,
    *,
    cache_dir: Path | None = None,
    force: bool = False,
    timeout: float = 30.0,
) -> ArticleSource:
    """URL → cached lookup → (miss) HTTP GET + trafilatura extract → save → return.

    Raises:
        ArticleFetchError: HTTP-layer failure (timeout, non-2xx, network).
        ArticleExtractionError: Page fetched but body too short / boilerplate-only.
    """
    cache_dir = Path(cache_dir) if cache_dir else _default_cache_dir()
    path = _cache_path(url, cache_dir)

    if not force:
        cached = _load_cache(path)
        if cached is not None:
            logger.info("article cache hit: %s", url)
            return cached

    logger.info("article fetch: %s", url)
    headers = {"User-Agent": _DEFAULT_UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers=headers,
            follow_redirects=True,
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text
    except httpx.HTTPError as e:
        raise ArticleFetchError(f"failed to fetch {url}: {e}") from e

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_recall=True,
    )
    if not text or len(text.strip()) < _MIN_TEXT_LEN:
        raise ArticleExtractionError(
            f"extracted text too short ({len(text or '')} chars) for {url}"
        )

    title = _extract_title(html)
    article = ArticleSource(
        url=url,
        text=text.strip(),
        title=title,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    _save_cache(path, article)
    return article


def _extract_title(html: str) -> str | None:
    """Best-effort <title> tag extraction without pulling in another parser."""
    metadata = trafilatura.extract_metadata(html)
    if metadata and metadata.title:
        return metadata.title.strip()
    return None
