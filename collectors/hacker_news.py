"""
Hacker News 수집기.

HN Algolia API (무료, 인증 불필요).
search_by_date 엔드포인트로 최신 AI 관련 스토리를 최신순으로 가져온다.
"""

import asyncio
import aiohttp
from scorer import NewsItem

_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"
# 단어를 합치면 AND 처리돼 결과가 거의 없음 — 개별 쿼리로 분리 후 URL 기준 중복 제거
_QUERIES = ["AI", "LLM", "machine learning"]


async def _fetch_query(
    session: aiohttp.ClientSession, query: str, limit: int
) -> list[dict]:
    params = {"query": query, "tags": "story", "hitsPerPage": limit}
    async with session.get(
        _ALGOLIA_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
    return data.get("hits", [])


async def fetch(limit: int = 20) -> list[NewsItem]:
    """HN에서 AI 관련 최신 스토리를 최신순으로 반환한다."""
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[_fetch_query(session, q, limit) for q in _QUERIES],
            return_exceptions=True,
        )

    seen_urls: set[str] = set()
    items: list[NewsItem] = []

    for result in results:
        if isinstance(result, Exception):
            print(f"[hacker_news] 쿼리 실패: {result}")
            continue
        for hit in result:
            title = hit.get("title", "")
            if not title:
                continue

            hn_id = hit.get("objectID", "")
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hn_id}"

            if url in seen_urls:
                continue
            seen_urls.add(url)

            points = hit.get("points") or 0
            num_comments = hit.get("num_comments") or 0

            items.append(NewsItem(
                title=title,
                source="Hacker News",
                url=url,
                summary=(
                    f"Points: {points} | Comments: {num_comments}\n"
                    f"{(hit.get('story_text') or '')[:300]}"
                ).strip(),
                is_rumor=True,
                is_official=False,
                urgency=3 if points >= 200 else 2,
            ))

    return items
