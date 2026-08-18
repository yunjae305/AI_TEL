"""
AIField 스케줄러.

두 가지 루프를 asyncio로 동시 실행한다:
  - 수집 루프: 주기적으로 collectors.fetch_all() → 즉시 알림 처리
  - 브리핑 루프: 지정 시각(09:00 / 21:00 KST)에 브리핑 발송

알림 라우팅:
  - is_official=True  → 즉시 속보 → 45분 뒤 커뮤니티 반응 후속
  - is_official=False → 검증 서칭 후 즉시 소식 (검증 결과는 본문에 포함)
  - Level 3           → DB 저장 + 브리핑 버퍼 적재
  - Level 1~2         → DB 저장만 (알림 없음)
"""

import asyncio
from datetime import datetime, timezone, timedelta

from collectors import fetch_all
from collectors.community_search import fetch_reactions, search_for_verification
from scorer import NewsItem
from bot import PasuinBot
from db.news_store import NewsStore
from llm import generate, budget_status
from prompts.pasuin_system import PASUIN_SYSTEM_PROMPT, briefing_user_prompt

KST = timezone(timedelta(hours=9))
# 아래 상한들은 Gemini 무료 티어 기준으로 잡혀 있다.
# 사이클당 최대 호출 = 공식×1 + 공식×2(후속) + 루머×2(검증) = 2 + 4 + 2 = 8회
# 하루 최대 = 8 × 24사이클 = 192회 — 여기에 config.GEMINI_DAILY_BUDGET이 최종 상한을 건다.
SCAN_INTERVAL_SEC = 60 * 60      # 60분마다 수집
BRIEFING_HOURS_KST = (9, 21)     # 09:00, 21:00 KST
BRIEFING_MAX_ITEMS = 10
IMMEDIATE_ALERT_MIN_LEVEL = 4      # Level 4 이상 즉시 알림 (공식)
IMMEDIATE_MAX_PER_CYCLE   = 2      # 사이클당 공식 즉시 알림 최대 건수
RUMOR_IMMEDIATE_MIN_LEVEL = 3      # Level 3 이상 즉시 알림 (루머/커뮤니티)
RUMOR_IMMEDIATE_MAX_PER_CYCLE = 1  # 사이클당 루머 즉시 포스팅 최대 건수
COMMUNITY_REACTION_DELAY_MIN = 45  # 공식 속보 후 커뮤 반응 후속 지연 (분)


class AIFieldScheduler:
    def __init__(self, bot: PasuinBot):
        self.bot = bot
        self._store = NewsStore()         # SQLite 영구 저장 — 재시작 후에도 중복 방지
        self._briefing_buffer: list[NewsItem] = []

    async def run(self):
        """봇이 ready 상태인 상황에서 호출한다. 종료될 때까지 반환하지 않는다."""
        print(f"[scheduler] 시작 — 수집 주기: {SCAN_INTERVAL_SEC // 60}분, "
              f"브리핑: {BRIEFING_HOURS_KST[0]:02d}:00 / {BRIEFING_HOURS_KST[1]:02d}:00 KST")
        try:
            await asyncio.gather(
                self._scan_loop(),
                self._briefing_loop(),
            )
        finally:
            self._store.close()

    # ------------------------------------------------------------------
    # 수집 루프
    # ------------------------------------------------------------------

    async def _scan_loop(self):
        while True:
            await self._scan_once()
            await asyncio.sleep(SCAN_INTERVAL_SEC)

    async def _scan_once(self):
        now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
        print(f"[scheduler] 수집 시작 — {now_str}")
        try:
            items = await fetch_all()
        except Exception as e:
            print(f"[scheduler] fetch_all 오류: {e}")
            return

        new_items = self._save_new(items)
        stats = self._store.stats()
        print(f"[scheduler] {len(items)}개 수집 → 신규 {len(new_items)}개 "
              f"(DB 누계: {stats['total']}건, 미브리핑: {stats['unbriefed']}건)")

        # Level 4+ 공식 → 영향도+긴급도 순으로 사이클당 최대 3건만 즉시 알림
        immediate_candidates = [it for it in new_items if it.alert_level >= IMMEDIATE_ALERT_MIN_LEVEL]
        immediate_candidates.sort(
            key=lambda x: (x.urgency + x.singularity_impact), reverse=True
        )
        immediate = immediate_candidates[:IMMEDIATE_MAX_PER_CYCLE]
        # 알림 안 된 나머지는 브리핑 버퍼로
        immediate_urls = {it.url for it in immediate}
        overflow = [
            it for it in immediate_candidates if it.url not in immediate_urls
        ]
        self._briefing_buffer.extend(overflow)

        # Level 3 루머/커뮤니티 → 즉시 알림 (사이클당 최대 2건, 긴급도+영향도 순)
        rumor_candidates = [
            it for it in new_items
            if not it.is_official and it.alert_level == RUMOR_IMMEDIATE_MIN_LEVEL
        ]
        rumor_candidates.sort(
            key=lambda x: (x.urgency + x.singularity_impact), reverse=True
        )
        rumor_immediate = rumor_candidates[:RUMOR_IMMEDIATE_MAX_PER_CYCLE]

        # Level 3 공식 항목 + 즉시 포스팅되지 않는 루머는 브리핑 버퍼
        rumor_immediate_urls = {it.url for it in rumor_immediate}
        buffered = [
            it for it in new_items
            if it.alert_level == 3 and it.url not in rumor_immediate_urls
        ]

        self._briefing_buffer.extend(buffered)

        for item in immediate:
            await self._post_immediate(item)
            await asyncio.sleep(1.5)

        for item in rumor_immediate:
            await self._post_immediate(item)
            await asyncio.sleep(1.5)

    def _save_new(self, items: list[NewsItem]) -> list[NewsItem]:
        """DB에 저장 성공한 항목(신규)만 반환한다."""
        return [it for it in items if self._store.save(it)]

    # ------------------------------------------------------------------
    # 즉시 알림 (Level 4 / 5)
    # ------------------------------------------------------------------

    async def _post_immediate(self, item: NewsItem):
        label = f"L{item.alert_level} {'공식' if item.is_official else '루머'}"
        print(f"[scheduler] 즉시 알림 [{label}] {item.title[:50]}")
        try:
            # 루머는 발송 전에 검증 서칭 — 결과를 본문에 함께 담아야 하므로 먼저 돈다
            if not item.is_official:
                try:
                    item.verification_context = await asyncio.wait_for(
                        search_for_verification(item), timeout=12.0
                    )
                except asyncio.TimeoutError:
                    print("[scheduler] 검증 서칭 타임아웃")
                    item.verification_context = ""

            message_id = await self.bot.post_news(item)

            if item.is_official:
                # 커뮤 반응은 45분 후 백그라운드로 처리 (갤 반응 쌓일 시간)
                asyncio.create_task(
                    self._delayed_community_reaction(message_id, item)
                )
                print(f"[scheduler] 커뮤 반응 {COMMUNITY_REACTION_DELAY_MIN}분 후 예약됨")
        except Exception as e:
            print(f"[scheduler] 즉시 알림 실패: {e}")

    async def _delayed_community_reaction(self, message_id: int, item: NewsItem):
        """공식 속보 후 일정 시간 대기 → 갤 반응 수집 → 후속 메시지."""
        delay_sec = COMMUNITY_REACTION_DELAY_MIN * 60
        await asyncio.sleep(delay_sec)
        print(f"[scheduler] 커뮤 반응 수집 시작 — {item.title[:40]}")
        try:
            try:
                item.community_summary = await asyncio.wait_for(
                    fetch_reactions(item), timeout=20.0
                )
            except asyncio.TimeoutError:
                print("[scheduler] 커뮤 반응 서칭 타임아웃")
                item.community_summary = ""
            if item.community_summary:
                await self.bot.post_community_reaction(message_id, item)
            else:
                print("[scheduler] 커뮤니티 반응 없음 — 후속 생략")
        except Exception as e:
            print(f"[scheduler] 커뮤 반응 후속 실패: {e}")

    # ------------------------------------------------------------------
    # 브리핑 루프
    # ------------------------------------------------------------------

    async def _briefing_loop(self):
        while True:
            now = datetime.now(KST)
            next_at = _next_briefing_time(now)
            wait_sec = (next_at - now).total_seconds()
            print(f"[scheduler] 다음 브리핑: {next_at.strftime('%m/%d %H:%M KST')} "
                  f"({wait_sec / 3600:.1f}h 후)")
            await asyncio.sleep(wait_sec)
            await self._post_briefing()

    async def _post_briefing(self):
        # 오래된 미브리핑 항목 자동 정리 (5일 초과분 → briefed=1)
        cleaned = self._store.cleanup_old_unbriefed(days=5)
        if cleaned:
            print(f"[scheduler] 오래된 미브리핑 {cleaned}건 자동 정리")

        # 30일 초과 항목 실제 삭제 (중복 방지용 30일치만 보존)
        deleted = self._store.delete_old(keep_days=30)
        if deleted:
            print(f"[scheduler] 30일 초과 항목 {deleted}건 삭제")

        # 버퍼가 비어 있으면 DB 미브리핑 항목으로 보완
        if not self._briefing_buffer:
            rows = self._store.get_unbriefed(min_level=3)
            if rows:
                self._briefing_buffer = [_row_to_news_item(r) for r in rows]

        if not self._briefing_buffer:
            print("[scheduler] 브리핑 항목 없음 — 생략")
            return

        # HuggingFace 모델만 있거나 DCInside만 있고 수가 적으면 브리핑할 가치 없음
        hf_only = all("HuggingFace" in it.source for it in self._briefing_buffer)
        notable = [it for it in self._briefing_buffer if "HuggingFace" not in it.source]
        if hf_only or len(notable) < 2:
            print(f"[scheduler] 브리핑 의미 없음 (주목할 항목 {len(notable)}개) — 생략")
            return

        now = datetime.now(KST)
        date_str = now.strftime("%Y-%m-%d")
        fallback = _format_briefing(self._briefing_buffer, now)
        content = await generate(
            PASUIN_SYSTEM_PROMPT,
            briefing_user_prompt(self._briefing_buffer, date_str),
            fallback=fallback,
        )
        try:
            await self.bot.post_briefing(content)
            self._store.mark_briefed(self._briefing_buffer)
            print(f"[scheduler] 브리핑 발송 완료 ({len(self._briefing_buffer)}개 항목)")
            self._briefing_buffer.clear()
        except Exception as e:
            print(f"[scheduler] 브리핑 발송 실패: {e}")

    # ------------------------------------------------------------------
    # 봇 명령어용 공개 메서드
    # ------------------------------------------------------------------

    async def force_briefing(self, items: list[NewsItem] | None = None):
        """items 지정 시 버퍼를 교체하고 즉시 브리핑을 발송한다."""
        if items is not None:
            self._briefing_buffer = list(items)
        await self._post_briefing()

    async def scan_once(self):
        """봇 명령어에서 즉시 수집 한 사이클 실행용."""
        await self._scan_once()

    def get_status(self) -> dict:
        """/status 명령어용 상태 정보를 반환한다."""
        stats = self._store.stats()
        now = datetime.now(KST)
        next_at = _next_briefing_time(now)
        wait_h = (next_at - now).total_seconds() / 3600
        return {
            "db": stats,
            "next_briefing": next_at.strftime("%m/%d %H:%M KST"),
            "next_briefing_in": f"{wait_h:.1f}h",
            "buffer_count": len(self._briefing_buffer),
            "budget": budget_status(),
        }


# ------------------------------------------------------------------
# 헬퍼 함수
# ------------------------------------------------------------------

def _next_briefing_time(now: datetime) -> datetime:
    for hour in BRIEFING_HOURS_KST:
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if candidate > now:
            return candidate
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(
        hour=BRIEFING_HOURS_KST[0], minute=0, second=0, microsecond=0
    )


def _row_to_news_item(row: dict) -> NewsItem:
    """DB 행을 NewsItem으로 변환한다."""
    return NewsItem(
        title=row["title"],
        source=row.get("source", ""),
        url=row.get("url", ""),
        summary=row.get("summary", ""),
        is_official=bool(row.get("is_official", 0)),
        is_rumor=bool(row.get("is_rumor", 1)),
        alert_level=row.get("alert_level", 0),
        should_alert=bool(row.get("should_alert", 0)),
        singularity_impact=row.get("singularity_impact", 0),
        urgency=row.get("urgency", 0),
        reliability=row.get("reliability", 0),
        practicality=row.get("practicality", 0),
    )


def _format_briefing(items: list[NewsItem], now: datetime) -> str:
    """Gemini 실패 시 fallback — 굵은 제목 + 한 줄 이유 + 커뮤 서술체."""
    date_str  = now.strftime("%Y-%m-%d")
    hf_items  = [it for it in items if "HuggingFace" in it.source]
    notable   = [it for it in items if "HuggingFace" not in it.source]
    # 영향도 + 긴급도 합산 순 정렬
    notable.sort(key=lambda x: x.singularity_impact + x.urgency, reverse=True)
    top     = notable[:5]
    rest    = notable[5:]

    lines = [f"**[AIField 일일 브리핑] {date_str}**", ""]

    # 주요 항목 — 굵은 제목 + 한 줄 이유
    for it in top:
        summary = (it.summary or "")[:100].strip()
        reason = summary.split(".")[0] if summary else it.source
        lines.append(f"**{it.title[:65]}** — {reason}")
    lines.append("")

    # 나머지 커뮤 흐름 — 1~2문장
    if rest:
        titles = ", ".join(f"'{it.title[:35]}'" for it in rest[:3])
        lines.append(f"오늘 커뮤에선 {titles} 얘기도 있었어요.")
    if hf_items:
        lines.append(f"HuggingFace엔 주목할 모델 {len(hf_items)}건도 올라왔어요.")
    if rest or hf_items:
        lines.append("")

    lines.append("당신, 무리하지 마세요. 핵심만 먼저 보셔도 돼요.")
    lines.append("*AI는 또 한 걸음 앞으로 나아갔네요.*")
    return "\n".join(lines)
