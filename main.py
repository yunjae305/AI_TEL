"""
AIField 진입점.

모드:
  python main.py           # --test (기본): 더미 데이터로 텔레그램 흐름 검증
  python main.py --live    # 실제 수집 + 스케줄러 실행 (텔레그램 봇 토큰 필요)
  python main.py --briefing-now  # --live와 동일하되 첫 수집 후 브리핑을 즉시 발송
"""

import argparse
import asyncio

import config  # 임포트 시점에 필수 환경변수 검증 실행
from scorer import NewsItem, score
from bot import PasuinBot
from scheduler import AIFieldScheduler

# ---------------------------------------------------------------------------
# 더미 테스트 데이터
# ---------------------------------------------------------------------------

RUMOR_NEWS = score(NewsItem(
    title="Meta, 새 오픈소스 LLM 출시 임박 — 내부 유출",
    summary=(
        "Reddit r/LocalLLaMA에서 Meta 내부 직원으로 추정되는 계정이 "
        "'Llama 4 Turbo' 출시가 이번 주 내로 예정됐다고 언급. "
        "공식 확인 없음."
    ),
    source="Reddit r/LocalLLaMA",
    is_rumor=True,
    is_official=False,
))

BREAKING_NEWS = score(NewsItem(
    title="Anthropic, Claude 4 공식 발표 — API 즉시 제공",
    summary=(
        "Anthropic이 공식 블로그를 통해 Claude 4 모델을 발표했다. "
        "API는 즉시 사용 가능하며, 코딩 및 멀티스텝 에이전트 성능이 "
        "이전 모델 대비 대폭 향상됐다고 밝혔다."
    ),
    source="anthropic.com",
    is_rumor=False,
    is_official=True,
    community_summary=(
        "Hacker News, Reddit에서 동시에 화제. "
        "개발자들 사이에서 API 한도 관련 질문이 폭발적으로 올라오는 중."
    ),
))

BRIEFING_ITEMS = [
    score(NewsItem(
        title="HuggingFace: DeepSeek-V4-Pro 급상승",
        source="huggingface.co",
        is_official=True,
        is_rumor=False,
    )),
    score(NewsItem(
        title="Reddit r/LocalLLaMA: Llama 4 Turbo 루머 계속 확산",
        source="Reddit r/LocalLLaMA",
        is_rumor=True,
        is_official=False,
    )),
]

# ---------------------------------------------------------------------------
# --test 모드: 더미 데이터로 3가지 텔레그램 흐름 검증
# ---------------------------------------------------------------------------

async def run_test(bot: PasuinBot):
    print("\n[test] 봇 온라인. 더미 시나리오 시작.")
    print(f"  루머 → Level {RUMOR_NEWS.alert_level} | "
          f"속보 → Level {BREAKING_NEWS.alert_level}\n")

    scheduler = AIFieldScheduler(bot)
    bot.set_scheduler(scheduler)

    # 시나리오 A: 루머 → 검증 서칭 결과를 본문에 담아 단일 메시지
    print("[A] 루머 포스팅 (검증 포함)")
    await scheduler._post_immediate(RUMOR_NEWS)
    await asyncio.sleep(2)

    # 시나리오 B: 공식 속보 (커뮤 반응 후속은 45분 뒤라 여기선 안 뜸)
    print("[B] 공식 속보 포스팅")
    await scheduler._post_immediate(BREAKING_NEWS)
    await asyncio.sleep(2)

    # 시나리오 C: 즉시 브리핑 강제 발송
    print("[C] 브리핑 발송")
    await scheduler.force_briefing(BRIEFING_ITEMS)

    print("\n[test] 완료.")

# ---------------------------------------------------------------------------
# --live 모드: 실제 수집 + 스케줄러 실행
# ---------------------------------------------------------------------------

async def run_live(briefing_now: bool = False):
    bot = PasuinBot()
    await bot.wait_ready()
    print("[live] 봇 온라인. 스케줄러 시작.")

    scheduler = AIFieldScheduler(bot)
    bot.set_scheduler(scheduler)

    try:
        if briefing_now:
            # 수집 한 번 실행 후 즉시 브리핑
            await scheduler._scan_once()
            await scheduler.force_briefing()
        else:
            await scheduler.run()  # 무한 루프
    finally:
        await bot.close()

# ---------------------------------------------------------------------------
# --test 모드 진입점 (봇 준비 + 테스트 + 종료)
# ---------------------------------------------------------------------------

async def run_test_mode():
    bot = PasuinBot()
    await bot.wait_ready()
    try:
        await run_test(bot)
    finally:
        await bot.close()

# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AIField 봇 실행")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--live", action="store_true",
        help="실제 수집 + 스케줄러 실행 (무한 루프)"
    )
    group.add_argument(
        "--briefing-now", action="store_true",
        help="수집 한 번 실행 후 브리핑 즉시 발송 (테스트용)"
    )
    args = parser.parse_args()

    if args.live:
        asyncio.run(run_live(briefing_now=False))
    elif args.briefing_now:
        asyncio.run(run_live(briefing_now=True))
    else:
        asyncio.run(run_test_mode())


if __name__ == "__main__":
    main()
