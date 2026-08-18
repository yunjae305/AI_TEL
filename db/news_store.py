"""
AIField 뉴스 저장소.

SQLite 기반 영구 저장. 표준 라이브러리만 사용하므로 추가 설치 불필요.

핵심 기능:
  - save(item): 신규면 저장 후 True, 중복이면 False (재시작 후에도 중복 방지)
  - get_unbriefed(): 브리핑 미발송 항목 조회
  - mark_briefed(items): 브리핑 발송 완료 표시
"""

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from scorer import NewsItem

_DB_PATH = Path(__file__).parent / "aifield.db"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS news (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key          TEXT    UNIQUE NOT NULL,
    title              TEXT    NOT NULL,
    source             TEXT,
    url                TEXT,
    summary            TEXT,
    is_official        INTEGER NOT NULL DEFAULT 0,
    is_rumor           INTEGER NOT NULL DEFAULT 1,
    alert_level        INTEGER NOT NULL DEFAULT 0,
    should_alert       INTEGER NOT NULL DEFAULT 0,
    singularity_impact INTEGER NOT NULL DEFAULT 0,
    urgency            INTEGER NOT NULL DEFAULT 0,
    reliability        INTEGER NOT NULL DEFAULT 0,
    practicality       INTEGER NOT NULL DEFAULT 0,
    briefed            INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_alert_level  ON news (alert_level);
CREATE INDEX IF NOT EXISTS idx_news_briefed      ON news (briefed);
CREATE INDEX IF NOT EXISTS idx_news_created_at   ON news (created_at);
"""


class NewsStore:
    def __init__(self, db_path: Path = _DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_CREATE_SQL)
        self._conn.commit()

    # ------------------------------------------------------------------
    # 쓰기
    # ------------------------------------------------------------------

    def save(self, item: NewsItem) -> bool:
        """신규 항목이면 DB에 저장하고 True를 반환한다. 중복이면 False."""
        key = _dedup_key(item)
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute(
                """
                INSERT INTO news (
                    dedup_key, title, source, url, summary,
                    is_official, is_rumor,
                    alert_level, should_alert,
                    singularity_impact, urgency, reliability, practicality,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key, item.title, item.source, item.url, item.summary,
                    int(item.is_official), int(item.is_rumor),
                    item.alert_level, int(item.should_alert),
                    item.singularity_impact, item.urgency,
                    item.reliability, item.practicality,
                    now,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # 중복 (dedup_key UNIQUE 제약 위반)

    def mark_briefed(self, items: list[NewsItem]) -> None:
        """브리핑에 포함된 항목들을 briefed=1로 표시한다."""
        keys = [(_dedup_key(it),) for it in items]
        self._conn.executemany(
            "UPDATE news SET briefed = 1 WHERE dedup_key = ?", keys
        )
        self._conn.commit()

    def cleanup_old_unbriefed(self, days: int = 5) -> int:
        """days일보다 오래된 미브리핑 항목을 briefed=1로 처리해 버퍼에서 제거한다."""
        from datetime import timedelta
        cutoff_str = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._conn.execute(
            "UPDATE news SET briefed = 1 WHERE briefed = 0 AND created_at < ?",
            (cutoff_str,),
        )
        self._conn.commit()
        return cur.rowcount

    def delete_old(self, keep_days: int = 30) -> int:
        """keep_days일보다 오래된 항목을 실제로 삭제한다.

        중복 방지를 위해 최소 keep_days(기본 30일)는 보존.
        """
        from datetime import timedelta
        cutoff_str = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
        cur = self._conn.execute(
            "DELETE FROM news WHERE created_at < ?",
            (cutoff_str,),
        )
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # 읽기
    # ------------------------------------------------------------------

    def get_unbriefed(self, min_level: int = 3, limit: int = 50) -> list[dict]:
        """브리핑 미발송 항목 중 alert_level >= min_level을 최신순으로 반환한다."""
        rows = self._conn.execute(
            """
            SELECT * FROM news
            WHERE briefed = 0 AND alert_level >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (min_level, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recent(self, limit: int = 100) -> list[dict]:
        """최근 저장된 항목을 최신순으로 반환한다."""
        rows = self._conn.execute(
            "SELECT * FROM news ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        """간단한 통계를 반환한다."""
        total = self._conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
        unbriefed = self._conn.execute(
            "SELECT COUNT(*) FROM news WHERE briefed = 0"
        ).fetchone()[0]
        by_level = {
            row["alert_level"]: row["cnt"]
            for row in self._conn.execute(
                "SELECT alert_level, COUNT(*) as cnt FROM news GROUP BY alert_level"
            ).fetchall()
        }
        return {"total": total, "unbriefed": unbriefed, "by_level": by_level}

    def close(self) -> None:
        self._conn.close()


# ------------------------------------------------------------------
# 헬퍼
# ------------------------------------------------------------------

def _dedup_key(item: NewsItem) -> str:
    """URL이 있으면 URL, 없으면 정규화된 제목의 MD5 해시를 키로 쓴다."""
    if item.url:
        return item.url.rstrip("/")
    normalized = item.title.lower().strip()
    return "title:" + hashlib.md5(normalized.encode()).hexdigest()
