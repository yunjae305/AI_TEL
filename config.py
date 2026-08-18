import os
from dotenv import load_dotenv

load_dotenv()

AIFIELD_BOT_TOKEN = os.getenv("AIFIELD_BOT_TOKEN")
AIFIELD_LIVE_CHAT_ID = int(os.getenv("AIFIELD_LIVE_CHAT_ID", "0"))
AIFIELD_BRIEFING_CHAT_ID = int(os.getenv("AIFIELD_BRIEFING_CHAT_ID", "0"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # 없으면 하드코딩 포맷으로 폴백
# 하루 Gemini 호출 상한. 초과분은 고정 포맷 폴백으로 나간다 (무료 티어 보호)
GEMINI_DAILY_BUDGET = int(os.getenv("GEMINI_DAILY_BUDGET", "120"))

def _require_str(name: str, val) -> None:
    if not val:
        raise EnvironmentError(f"필수 환경변수 누락: {name} — .env 파일을 확인해줘.")

def _require_int(name: str, val: int) -> None:
    if val == 0:
        raise EnvironmentError(f"필수 환경변수 누락: {name} — .env 파일을 확인해줘.")

_require_str("AIFIELD_BOT_TOKEN", AIFIELD_BOT_TOKEN)
_require_int("AIFIELD_LIVE_CHAT_ID", AIFIELD_LIVE_CHAT_ID)
_require_int("AIFIELD_BRIEFING_CHAT_ID", AIFIELD_BRIEFING_CHAT_ID)
