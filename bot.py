import asyncio
import telegram
from telegram.ext import Application, CommandHandler, ContextTypes
import config
from scorer import NewsItem
from llm import generate
from telegram_format import md_to_html, split_chunks
from prompts.pasuin_system import (
    PASUIN_SYSTEM_PROMPT,
    news_user_prompt,
    community_reaction_user_prompt,
)


class PasuinBot:
    """AIField-파수인 — AI 씬을 지켜보고 걸러서 전하는 텔레그램 봇."""

    def __init__(self):
        self.app = Application.builder().token(config.AIFIELD_BOT_TOKEN).build()
        self.bot = self.app.bot
        self._scheduler = None
        self._setup_commands()

    def set_scheduler(self, scheduler) -> None:
        self._scheduler = scheduler

    def _setup_commands(self):
        self.app.add_handler(CommandHandler("status", self._cmd_status))
        self.app.add_handler(CommandHandler("briefing_now", self._cmd_briefing_now))
        self.app.add_handler(CommandHandler("scan_now", self._cmd_scan_now))

    async def _cmd_status(self, update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
        if self._scheduler is None:
            await update.message.reply_text("스케줄러가 아직 준비 중이에요. 조금만 기다려 주세요.")
            return
        s = self._scheduler.get_status()
        db = s["db"]
        by_level = " | ".join(
            f"L{lvl}:{cnt}" for lvl, cnt in sorted(db["by_level"].items())
        ) or "없음"
        b = s["budget"]
        text = (
            "<b>AIField 상태</b>\n"
            "<pre>\n"
            f"DB 총 수집  : {db['total']}건\n"
            f"미브리핑    : {db['unbriefed']}건\n"
            f"버퍼 대기   : {s['buffer_count']}건\n"
            f"레벨별      : {by_level}\n"
            f"다음 브리핑 : {s['next_briefing']} ({s['next_briefing_in']} 후)\n"
            f"Gemini 예산 : {b['used']}/{b['limit']}회 (오늘)\n"
            "</pre>"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    async def _cmd_briefing_now(self, update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
        if self._scheduler is None:
            await update.message.reply_text("스케줄러가 아직 준비 중이에요. 조금만 기다려 주세요.")
            return
        await update.message.reply_text("정리해서 올릴게요.")
        await self._scheduler.force_briefing()
        await update.message.reply_text("브리핑 보냈어요.")

    async def _cmd_scan_now(self, update: telegram.Update, context: ContextTypes.DEFAULT_TYPE):
        if self._scheduler is None:
            await update.message.reply_text("스케줄러가 아직 준비 중이에요. 조금만 기다려 주세요.")
            return
        await update.message.reply_text("한번 훑어볼게요.")
        await self._scheduler.scan_once()
        await update.message.reply_text("수집 끝났어요.")

    async def wait_ready(self):
        """봇 초기화 + 명령어 폴링 시작. 완료 후 온라인 상태로 표시."""
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        me = await self.bot.get_me()
        print(f"[파수인] 온라인: @{me.username}")

    async def close(self):
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()

    async def _safe_send(self, chat_id: int, content: str, reply_to: int | None = None) -> int:
        """텔레그램 4096자 제한 대응 — 초과 시 줄 단위로 분할 발송. 첫 메시지 id 반환."""
        chunks = split_chunks(content)
        first_id = None
        for i, chunk in enumerate(chunks):
            message = await self.bot.send_message(
                chat_id=chat_id,
                text=md_to_html(chunk),
                parse_mode="HTML",
                reply_to_message_id=reply_to if i == 0 else None,
            )
            if first_id is None:
                first_id = message.message_id
            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)
        return first_id

    async def post_news(self, item: NewsItem) -> int:
        """소식 하나를 라이브 채팅에 올리고 message_id 반환. 검증 결과는 본문에 녹인다."""
        content = await generate(
            PASUIN_SYSTEM_PROMPT,
            news_user_prompt(item),
            fallback=_format_news(item),
        )
        # DCInside 글: 링크를 Gemini에 맡기지 않고 코드에서 직접 붙임
        is_dcinside = "특이점" in item.source or "dcinside" in item.source.lower()
        if is_dcinside and item.url and item.url not in content:
            content = content.rstrip() + f"\n{item.url}"

        return await self._safe_send(config.AIFIELD_LIVE_CHAT_ID, content)

    async def post_community_reaction(self, message_id: int, item: NewsItem):
        """속보를 올린 뒤 시간이 지나 모인 커뮤니티 반응을 후속으로 덧붙인다."""
        content = await generate(
            PASUIN_SYSTEM_PROMPT,
            community_reaction_user_prompt(item),
            fallback=_format_community_reaction(item),
        )
        await self._safe_send(config.AIFIELD_LIVE_CHAT_ID, content, reply_to=message_id)

    async def post_briefing(self, content: str):
        """브리핑 채팅에 브리핑 게시."""
        await self._safe_send(config.AIFIELD_BRIEFING_CHAT_ID, content)


def _format_news(item: NewsItem) -> str:
    """Gemini 실패 시 fallback."""
    summary_short = (item.summary or "")[:220].strip()
    url_line = item.url or item.source
    if item.is_official:
        intro = "당신, 공식 발표 하나 확인했어요."
        verdict = "AI는 또 한 걸음 앞으로 나아갔네요."
    else:
        intro = "당신, 하나 걸렸어요. 아직 공식은 아니에요."
        verdict = "아직 한 걸음이라고 말하기엔 일러요. 조금 더 지켜보죠."

    lines = [intro, "", f"**{item.title}**", f"{item.source} | {url_line}", ""]
    if summary_short:
        lines.append(summary_short)
    if item.verification_context:
        lines.append(item.verification_context)
    lines += [
        "",
        f"영향 {item.singularity_impact} | 긴급 {item.urgency} | "
        f"신뢰 {item.reliability} | 실용 {item.practicality}",
        verdict,
    ]
    return "\n".join(lines)


def _format_community_reaction(item: NewsItem) -> str:
    """Gemini 실패 시 fallback."""
    reaction = item.community_summary or "아직 이렇다 할 반응은 보이지 않아요."
    return (
        f"아까 그 소식, 반응이 좀 모였어요.\n\n"
        f"**{item.title}**\n"
        f"{reaction}\n\n"
        f"지나치기엔 아까운 것 같아요."
    )
