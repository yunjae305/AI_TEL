"""
Reddit AI 커뮤니티 수집기.

r/LocalLLaMA, r/MachineLearning 핫 포스트 수집.
인증 불필요 (Reddit public JSON API).

수집 기준:
  - 추천수(score) 기준 이상인 글만 수집
  - 24시간 이내 포스트만
  - Meme / Discussion(잡담) 플레어 제외
"""

import asyncio
import re
from datetime import datetime, timezone, timedelta

import aiohttp

from scorer import NewsItem

_HEADERS = {
    "User-Agent": "AIField-Bot/1.0 (AI news aggregator; contact: bot@aifield.local)"
}
_REDDIT_BASE = "https://www.reddit.com/r/{sub}/hot.json"
_MAX_AGE_HOURS = 24
_TIMEOUT = aiohttp.ClientTimeout(total=10)

# (서브레딧, 최소 추천수)
_SUBREDDITS: list[tuple[str, int]] = [
    ("LocalLLaMA", 30),       # 오픈소스 LLM 커뮤니티 — 핵심 소스
    ("MachineLearning", 100), # ML 연구 커뮤니티 — 논문/연구 위주, 기준 높게
]

# 제외할 플레어 키워드 (대소문자 무관)
_SKIP_FLAIRS = {"meme", "humor", "off-topic", "meta", "rant"}

# 추천수 → 긴급도
_URGENCY_HIGH = 500   # urgency=4
_URGENCY_MID  = 100   # urgency=3
# 그 외             → urgency=2

_HTML_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _HTML_RE.sub("", text).strip()


def _infer_urgency(score: int) -> int:
    if score >= _URGENCY_HIGH:
        return 4
    if score >= _URGENCY_MID:
        return 3
    return 2


async def _fetch_subreddit(
    session: aiohttp.ClientSession,
    sub: str,
    min_score: int,
    cutoff: datetime,
) -> list[NewsItem]:
    url = _REDDIT_BASE.format(sub=sub)
    try:
        async with session.get(
            url,
            params={"limit": 30},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
    except Exception as e:
        print(f"[reddit] r/{sub} 요청 실패: {e}")
        return []

    items: list[NewsItem] = []
    children = data.get("data", {}).get("children", [])

    for child in children:
        post = child.get("data", {})

        # 광고 제외
        if post.get("is_reddit_media_domain") or post.get("stickied"):
            continue

        # 플레어 필터
        flair = (post.get("link_flair_text") or "").lower()
        if any(skip in flair for skip in _SKIP_FLAIRS):
            continue

        score_val = post.get("score") or 0
        if score_val < min_score:
            continue

        # 시간 필터
        created_utc = post.get("created_utc")
        if created_utc:
            post_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)
            if post_time < cutoff:
                continue

        title = (post.get("title") or "").strip()
        if not title:
            continue

        # URL: 외부 링크면 원본, 텍스트 포스트면 Reddit 링크
        link = post.get("url") or ""
        permalink = post.get("permalink") or ""
        is_self = post.get("is_self", False)
        final_url = f"https://www.reddit.com{permalink}" if is_self else link

        # 요약: 셀프 포스트면 본문, 아니면 제목+수치
        selftext = _strip_html(post.get("selftext") or "")[:400]
        num_comments = post.get("num_comments") or 0
        summary = (
            f"r/{sub} | 추천 {score_val} | 댓글 {num_comments}\n{selftext}"
            if selftext
            else f"r/{sub} | 추천 {score_val} | 댓글 {num_comments}"
        ).strip()

        items.append(NewsItem(
            title=title,
            source=f"Reddit r/{sub}",
            url=final_url,
            summary=summary,
            is_official=False,
            is_rumor=True,
            reliability=3,
            urgency=_infer_urgency(score_val),
        ))

    return items


async def fetch() -> list[NewsItem]:
    """등록된 서브레딧에서 최신 핫 포스트를 수집한다."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_MAX_AGE_HOURS)

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[
                _fetch_subreddit(session, sub, min_score, cutoff)
                for sub, min_score in _SUBREDDITS
            ],
            return_exceptions=True,
        )

    items: list[NewsItem] = []
    for (sub, _), result in zip(_SUBREDDITS, results):
        if isinstance(result, Exception):
            print(f"[reddit] r/{sub} 수집 실패: {result}")
            continue
        items.extend(result)
        print(f"[reddit] r/{sub} {len(result)}개 수집")

    return items
