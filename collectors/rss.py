"""
공식 AI 랩 블로그 RSS/Atom 수집기.

OpenAI, Anthropic, Google DeepMind, Meta AI, NVIDIA 공식 블로그의
최신 포스트를 피드로 수집한다. is_official=True / reliability=5 로 설정되므로
키워드 매칭 시 Level 4~5 즉시 알림으로 연결된다.
"""

import asyncio
import re
import time as _time
from datetime import datetime, timezone, timedelta

import aiohttp
import feedparser

from scorer import NewsItem

# (url, reliability)
# reliability=5: 순수 AI 랩 공식 블로그 → Level 5 즉시 알림 가능
# reliability=4: AI 관련 기술 블로그   → Level 4까지만 (Level 5 차단)
_FEEDS: dict[str, tuple[str, int]] = {
    "OpenAI Blog":      ("https://openai.com/blog/rss.xml",                              5),
    "Google DeepMind":  ("https://deepmind.google/blog/feed/basic/",                     5),
    "HuggingFace Blog": ("https://huggingface.co/blog/feed.xml",                         4),
    "NVIDIA AI Blog":   ("https://blogs.nvidia.com/blog/category/deep-learning/feed/",   4),
    "Meta Engineering": ("https://engineering.fb.com/feed/",                             4),
}
# Anthropic/Mistral/xAI는 공식 RSS 피드 없음 — 추후 스크래퍼로 보완

_MAX_AGE_HOURS = 24   # 24시간 이내 포스트만 수집 (초회 스팸 방지)
_HEADERS = {"User-Agent": "AIField-Bot/1.0 (AI news aggregator)"}
_HTML_RE = re.compile(r"<[^>]+>")


def _entry_time(entry: dict) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t is None:
        return None
    return datetime.fromtimestamp(_time.mktime(t), tz=timezone.utc)


def _strip_html(text: str) -> str:
    return _HTML_RE.sub("", text).strip()


async def _fetch_one(
    session: aiohttp.ClientSession, name: str, url: str, reliability: int, cutoff: datetime
) -> list[NewsItem]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                print(f"[rss] {name} HTTP {resp.status}")
                return []
            raw = await resp.read()
    except Exception as e:
        print(f"[rss] {name} 요청 실패: {e}")
        return []

    feed = feedparser.parse(raw)
    items: list[NewsItem] = []

    for entry in feed.entries:
        pub = _entry_time(entry)
        if pub and pub < cutoff:
            continue

        title = _strip_html(entry.get("title") or "").strip()
        if not title:
            continue

        link = entry.get("link", "")

        # summary 추출 — summary → content → 없으면 빈 문자열
        raw_summary = entry.get("summary", "")
        if not raw_summary:
            content_list = entry.get("content", [])
            raw_summary = content_list[0].get("value", "") if content_list else ""
        summary = _strip_html(raw_summary)[:600]

        items.append(NewsItem(
            title=title,
            source=name,
            url=link,
            summary=summary,
            is_official=True,
            is_rumor=False,
            reliability=reliability,
        ))

    return items


async def fetch() -> list[NewsItem]:
    """등록된 모든 RSS 피드에서 최신 공식 포스트를 수집한다."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_MAX_AGE_HOURS)

    async with aiohttp.ClientSession(headers=_HEADERS) as session:
        tasks = [
            _fetch_one(session, name, url, rel, cutoff)
            for name, (url, rel) in _FEEDS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    items: list[NewsItem] = []
    for name, result in zip(_FEEDS.keys(), results):
        if isinstance(result, Exception):
            print(f"[rss] {name} 수집 실패: {result}")
            continue
        items.extend(result)

    return items
