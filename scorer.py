"""
AIField 스코어링 모듈.

NewsItem 데이터클래스와 score() 함수가 핵심.
score()는 규칙 기반으로 빈 점수를 채우고 알림 레벨을 결정한다.
수집기(collector)가 이미 점수를 설정했다면 그 값을 그대로 유지한다.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NewsItem:
    # 기본 정보
    title: str
    source: str
    summary: str = ""
    url: str = ""

    # 수집 단계에서 설정하는 메타데이터
    is_official: bool = False
    is_rumor: bool = True
    community_summary: str = ""
    verification_context: str = ""  # 발송 전 검증 서칭 결과

    # 점수 (0이면 score()에서 규칙 기반으로 자동 추론)
    singularity_impact: int = 0  # 1~5: AI 생태계 방향에 미치는 영향
    urgency: int = 0             # 1~5: 즉시 알림 필요 여부
    reliability: int = 0         # 1~5: 출처 신뢰도
    practicality: int = 0        # 1~5: 개발/연구/서비스 실용성

    # score() 실행 후 채워지는 결과값
    alert_level: int = 0         # 1~5
    should_alert: bool = False


# ---------------------------------------------------------------------------
# 신뢰도 추론 — 출처 도메인/이름 기반
# ---------------------------------------------------------------------------

_OFFICIAL_DOMAINS = {
    "anthropic.com",
    "openai.com",
    "deepmind.google",
    "blog.google",
    "ai.meta.com",
    "nvidia.com",
    "x.ai",
    "huggingface.co",
    "arxiv.org",
}

_RELIABLE_SOURCES = {
    "techcrunch", "wired", "mit technology review", "nature", "science",
    "ieee", "acm", "the verge", "ars technica",
}

_COMMUNITY_SOURCES = {
    "reddit", "hacker news", "hn", "twitter", "x.com",
    "dcinside", "clien", "fm korea", "ruliweb",
}


def _infer_reliability(item: NewsItem) -> int:
    src = item.source.lower()

    if any(d in src for d in _OFFICIAL_DOMAINS) or item.is_official:
        return 5
    if any(s in src for s in _RELIABLE_SOURCES):
        return 4
    if "arxiv" in src:
        return 4
    if any(s in src for s in _COMMUNITY_SOURCES):
        return 3
    if item.is_rumor:
        return 1
    return 3


# ---------------------------------------------------------------------------
# 긴급도 추론 — 공식 여부 + 제목 키워드
# ---------------------------------------------------------------------------

_HIGH_URGENCY_KEYWORDS = [
    "출시", "공개", "발표", "release", "launch", "announce",
    "api", "오픈소스", "open source",
]

_LOW_URGENCY_KEYWORDS = [
    "루머", "rumor", "유출", "leak", "추측", "speculation",
    "예정", "예상", "전망",
]


def _infer_urgency(item: NewsItem) -> int:
    if item.is_official:
        text = (item.title + " " + item.summary).lower()
        if any(k in text for k in _HIGH_URGENCY_KEYWORDS):
            return 5
        return 4

    text = (item.title + " " + item.summary).lower()
    if any(k in text for k in _LOW_URGENCY_KEYWORDS):
        return 2
    if any(k in text for k in _HIGH_URGENCY_KEYWORDS):
        return 3
    return 2


# ---------------------------------------------------------------------------
# 특이점 영향도 추론 — 제목/요약 키워드
# ---------------------------------------------------------------------------

_IMPACT_5_KEYWORDS = [
    "gpt-5", "claude 4", "gemini 3", "llama 4",
    "agi", "범용 ai", "인간 수준",
    "multimodal", "멀티모달", "reasoning",
]

_IMPACT_4_KEYWORDS = [
    "오픈소스 모델", "open source model", "new model", "신규 모델",
    "논문", "paper", "benchmark", "벤치마크",
    "fine-tuning", "파인튜닝", "rlhf",
]

_IMPACT_3_KEYWORDS = [
    "업데이트", "update", "개선", "improvement",
    "api 변경", "api change", "pricing",
]


def _infer_impact(item: NewsItem) -> int:
    text = (item.title + " " + item.summary).lower()
    if any(k in text for k in _IMPACT_5_KEYWORDS):
        return 5
    if any(k in text for k in _IMPACT_4_KEYWORDS):
        return 4
    if any(k in text for k in _IMPACT_3_KEYWORDS):
        return 3
    if item.is_official:
        return 3
    return 2


# ---------------------------------------------------------------------------
# 실용성 추론
# ---------------------------------------------------------------------------

_HIGH_PRACTICALITY_KEYWORDS = [
    "api", "sdk", "오픈소스", "open source", "weights", "모델 공개",
    "github", "huggingface", "무료", "free",
]

_LOW_PRACTICALITY_KEYWORDS = [
    "루머", "rumor", "예정", "전망", "추측",
]


def _infer_practicality(item: NewsItem) -> int:
    text = (item.title + " " + item.summary).lower()
    if any(k in text for k in _HIGH_PRACTICALITY_KEYWORDS):
        return 5 if item.is_official else 4
    if any(k in text for k in _LOW_PRACTICALITY_KEYWORDS):
        return 2
    if item.is_official:
        return 4
    return 3


# ---------------------------------------------------------------------------
# 알림 레벨 결정 (CLAUDE.md 기준)
# ---------------------------------------------------------------------------

def _compute_alert_level(item: NewsItem) -> int:
    """
    Level 5: 공식 대형 발표, 신뢰도 5, 긴급도 5 → 즉시 알림
    Level 4: 중요 논문, 큰 오픈소스 모델 → 즉시 또는 묶음 알림
    Level 3: 오늘 브리핑에 넣을 만한 소식
    Level 2: 커뮤니티 떡밥, 근거 약한 루머 → DB 저장만
    Level 1: 중복, 출처 없는 과장글, 광고 → 무시
    """
    if item.is_official and item.reliability >= 5 and item.urgency >= 4:
        return 5

    if item.singularity_impact >= 4 and item.reliability >= 4:
        return 4

    if item.singularity_impact >= 3 or item.urgency >= 3:
        return 3

    if item.is_rumor and item.reliability <= 2:
        return 2

    return 1


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def score(item: NewsItem) -> NewsItem:
    """
    규칙 기반으로 빈 점수(0)를 채우고 alert_level, should_alert를 결정한다.
    수집기가 이미 설정한 점수(0이 아닌 값)는 덮어쓰지 않는다.
    """
    if item.reliability == 0:
        item.reliability = _infer_reliability(item)
    if item.urgency == 0:
        item.urgency = _infer_urgency(item)
    if item.singularity_impact == 0:
        item.singularity_impact = _infer_impact(item)
    if item.practicality == 0:
        item.practicality = _infer_practicality(item)

    item.alert_level = _compute_alert_level(item)
    item.should_alert = item.alert_level >= 4
    return item
