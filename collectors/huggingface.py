"""
HuggingFace 수집기.

HuggingFace Hub API (인증 불필요)로 급상승 / 신규 모델을 가져온다.
"""

import asyncio
import aiohttp
from scorer import NewsItem

_HF_API = "https://huggingface.co/api/models"

# 텍스트/코드/멀티모달 관련 파이프라인만 수집
_TARGET_PIPELINES = {
    "text-generation",
    "text2text-generation",
    "question-answering",
    "summarization",
    "translation",
    "image-to-text",
    "text-to-image",
    "visual-question-answering",
    "code-completion",
}


def _build_summary(model: dict) -> str:
    likes = model.get("likes", 0)
    downloads = model.get("downloads", 0)
    pipeline = model.get("pipeline_tag", "unknown")
    tags = ", ".join((model.get("tags") or [])[:5])
    return f"Pipeline: {pipeline} | Likes: {likes} | Downloads: {downloads}\nTags: {tags}"


def _make_item(model: dict, label: str) -> NewsItem:
    model_id = model.get("modelId") or model.get("id", "")
    pipeline = model.get("pipeline_tag", "")
    is_gated = model.get("gated", False)
    likes = model.get("likes", 0)

    return NewsItem(
        title=f"[HuggingFace {label}] {model_id}",
        source="huggingface.co",
        url=f"https://huggingface.co/{model_id}",
        summary=_build_summary(model),
        is_rumor=False,
        is_official=True,
        # 좋아요 수 많으면 영향도/긴급도 높임
        singularity_impact=4 if likes >= 1000 else 3,
        urgency=3 if likes >= 500 else 2,
        practicality=3 if is_gated else 5,  # 게이티드 모델은 접근 제한 있음
    )


_MIN_LIKES = 50  # 이 미만은 개인 업로드 노이즈로 간주해 걸러냄


async def fetch(limit: int = 20) -> list[NewsItem]:
    """HuggingFace 급상승 모델만 수집한다 (신규 전체 업로드는 노이즈가 많아 제거)."""
    params = {"sort": "trendingScore", "direction": -1, "limit": limit}
    async with aiohttp.ClientSession() as session:
        async with session.get(_HF_API, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            models = await resp.json()

    result = []
    seen: set[str] = set()
    for m in models:
        # 파이프라인 필터 + 최소 좋아요 수 필터
        if m.get("pipeline_tag") not in _TARGET_PIPELINES:
            continue
        if (m.get("likes") or 0) < _MIN_LIKES:
            continue
        item = _make_item(m, "급상승")
        if item.url not in seen:
            seen.add(item.url)
            result.append(item)

    return result
