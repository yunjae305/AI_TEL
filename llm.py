"""
Gemini Flash 비동기 래퍼.

키가 없으면 즉시 fallback을 반환하므로 키 없이도 봇이 동작한다.
무료 티어를 넘지 않도록 두 겹으로 막는다:
  - Semaphore(1) + sleep(_REQ_INTERVAL): 분당 호출 간격 (RPM)
  - try_spend(): 하루 총 호출 상한 (RPD)

상한을 다 쓰면 예외를 내지 않고 fallback으로 조용히 넘어간다.
봇은 계속 돌고, 메시지만 고정 포맷으로 나간다.
"""

import asyncio
from datetime import datetime, timezone, timedelta

import config

# gemini-2.5-flash는 신규 사용자에게 404 → 3.5-flash 사용
_MODEL = "gemini-3.5-flash"
_REQ_INTERVAL = 12.0   # 호출 간 최소 간격(초). 429가 잦으면 올린다
_THINKING_BUDGET = 128  # thinking 토큰도 쿼터를 먹는다. 낮게 유지

KST = timezone(timedelta(hours=9))

_client = None
_semaphore: asyncio.Semaphore | None = None

if config.GEMINI_API_KEY:
    try:
        from google import genai
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
        _semaphore = asyncio.Semaphore(1)
    except ImportError:
        print("[llm] google-genai 미설치 — pip install google-genai 후 재시작")


# ---------------------------------------------------------------------------
# 하루 호출 예산 (RPD 가드)
# ---------------------------------------------------------------------------
# ponytail: 프로세스 메모리에만 두는 카운터라 재시작하면 0으로 돌아간다.
# 재시작이 잦아 실제 쿼터를 넘기 시작하면 DB(news_store)에 옮긴다.

_used = 0
_used_day = None


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def try_spend() -> bool:
    """하루 예산을 1회 소비한다. 남아 있으면 True, 소진됐으면 False."""
    global _used, _used_day
    today = _today()
    if today != _used_day:
        _used_day, _used = today, 0
    if _used >= config.GEMINI_DAILY_BUDGET:
        return False
    _used += 1
    return True


def budget_status() -> dict:
    """남은 예산 조회 (/status 명령어용)."""
    if _used_day != _today():
        return {"used": 0, "limit": config.GEMINI_DAILY_BUDGET}
    return {"used": _used, "limit": config.GEMINI_DAILY_BUDGET}


# ---------------------------------------------------------------------------
# 생성
# ---------------------------------------------------------------------------

async def generate(system_prompt: str, user_prompt: str, fallback: str = "") -> str:
    """Gemini로 텍스트를 생성한다. 키 없음/예산 소진/오류 시 fallback을 반환한다.

    429 rate limit 시 1회 재시도. 그 외 오류는 즉시 fallback.
    """
    if _client is None:
        return fallback

    if not try_spend():
        print(f"[llm] 하루 호출 예산 {config.GEMINI_DAILY_BUDGET}회 소진 — fallback 사용")
        return fallback

    from google.genai import types

    async with _semaphore:
        for attempt in range(2):
            try:
                response = await _client.aio.models.generate_content(
                    model=_MODEL,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.8,
                        max_output_tokens=2000,
                        thinking_config=types.ThinkingConfig(
                            thinking_budget=_THINKING_BUDGET
                        ),
                    ),
                    contents=user_prompt,
                )
                await asyncio.sleep(_REQ_INTERVAL)
                text = response.text
                return text.strip() if text else fallback

            except Exception as e:
                err_str = str(e)
                is_rate_limit = "429" in err_str or "quota" in err_str.lower()

                if is_rate_limit and attempt == 0:
                    print("[llm] 429 rate limit — 65초 후 1회 재시도")
                    await asyncio.sleep(65.0)
                    continue

                print(f"[llm] 오류: {e}")
                await asyncio.sleep(_REQ_INTERVAL)
                return fallback

    return fallback
