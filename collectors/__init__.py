"""
AIField 수집기 패키지.

각 수집기는 async fetch() -> list[NewsItem] 인터페이스를 따른다.
점수(신뢰도 등)는 수집기 단계에서 0으로 두고, score()가 자동 추론한다.
수집기가 더 정확한 점수를 알면 직접 설정해도 된다 — score()는 0인 항목만 덮어쓸.
"""

import asyncio
from scorer import NewsItem, score

from collectors import huggingface, dcinside, rss, anthropic


async def fetch_all() -> list[NewsItem]:
    """모든 수집기를 동시에 실행하고 scored NewsItem 목록을 반환한다."""
    results = await asyncio.gather(
        rss.fetch(),
        huggingface.fetch(),
        dcinside.fetch(),
        anthropic.fetch(),
        return_exceptions=True,
    )

    items: list[NewsItem] = []
    names = ["RSS(공식)", "HuggingFace", "DCInside", "Anthropic"]
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            print(f"[collectors] {name} 수집 실패: {result}")
            continue
        for item in result:
            items.append(score(item))

    return items
