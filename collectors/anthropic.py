"""
Anthropic 공식 뉴스 스크래퍼.
https://www.anthropic.com/news

공식 RSS 피드가 없어서 HTML 직접 파싱.
is_official=True / reliability=5 → 중요 발표 시 Level 4~5 즉시 알림.
"""

import re
import aiohttp
from bs4 import BeautifulSoup
from scorer import NewsItem

_BASE     = "https://www.anthropic.com"
_NEWS_URL = "https://www.anthropic.com/news"
_HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

# 제목에서 날짜/카테고리 패턴 제거용
_DATE_RE  = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\s*"
)
_CAT_RE   = re.compile(
    r"^(Announcements|Products?|Research|News|Policy|Company|Safety)\s*[|·]?\s*",
    re.IGNORECASE,
)


def _clean_title(raw: str) -> str:
    """날짜·카테고리 prefix 제거 후 제목만 반환."""
    t = raw.strip()
    t = _DATE_RE.sub("", t)
    t = _CAT_RE.sub("", t)
    return t.strip()[:180]


async def fetch(limit: int = 5) -> list[NewsItem]:
    """Anthropic 뉴스 페이지에서 최신 포스트를 수집한다."""
    try:
        async with aiohttp.ClientSession(headers=_HEADERS) as session:
            async with session.get(
                _NEWS_URL, timeout=aiohttp.ClientTimeout(total=12)
            ) as resp:
                if resp.status != 200:
                    print(f"[anthropic] HTTP {resp.status}")
                    return []
                html = await resp.text()
    except Exception as e:
        print(f"[anthropic] 요청 실패: {e}")
        return []

    soup  = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    items: list[NewsItem] = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("/news/"):
            continue

        url = _BASE + href
        if url in seen:
            continue
        seen.add(url)

        # 제목: 링크 텍스트 → 부모 텍스트 → 슬러그 순으로 시도
        raw_text = a.get_text(separator=" ", strip=True)
        title    = _clean_title(raw_text)

        if len(title) < 8:
            parent_text = (a.parent or a).get_text(separator=" ", strip=True)
            title = _clean_title(parent_text)

        if len(title) < 8:
            slug  = href.split("/news/")[-1]
            title = slug.replace("-", " ").title()

        if not title:
            continue

        items.append(NewsItem(
            title=title,
            source="Anthropic",
            url=url,
            summary="",
            is_official=True,
            is_rumor=False,
            reliability=5,
            singularity_impact=4,
        ))

        if len(items) >= limit:
            break

    if items:
        print(f"[anthropic] {len(items)}건 수집")
    return items
