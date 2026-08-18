"""텔레그램 메시지 포맷 헬퍼.

**굵게** 마크다운을 텔레그램 HTML로 변환하고, 4096자 메시지 길이
제한에 맞춰 줄 단위로 분할한다.
"""

import html
import re

TELEGRAM_MSG_LIMIT = 4096
_CHUNK_LIMIT = TELEGRAM_MSG_LIMIT - 96  # 분할 여유분


def md_to_html(text: str) -> str:
    """`**굵게**`만 <b>로 변환. 나머지는 그대로 두되 HTML 특수문자는 이스케이프."""
    escaped = html.escape(text, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.S)


def split_chunks(content: str, limit: int = _CHUNK_LIMIT) -> list[str]:
    """제한 길이 초과 시 줄 단위로 분할. 줄 하나가 제한보다 길면 그 줄을 강제로 자른다."""
    if len(content) <= limit:
        return [content]
    chunks: list[str] = []
    chunk = ""
    for line in content.splitlines(keepends=True):
        while len(line) > limit:
            # 줄 하나가 제한을 넘으면 앞부분을 잘라 내보낸다 (안 자르면 텔레그램이 거절)
            head_room = limit - len(chunk)
            chunk += line[:head_room]
            chunks.append(chunk)
            chunk = ""
            line = line[head_room:]
        if len(chunk) + len(line) > limit:
            chunks.append(chunk)
            chunk = line
        else:
            chunk += line
    if chunk:
        chunks.append(chunk)
    return chunks


if __name__ == "__main__":
    # HTML 특수문자는 이스케이프되고, **굵게**만 태그로 바뀐다
    assert md_to_html("**제목** <b>주입</b> & 기호") == "<b>제목</b> &lt;b&gt;주입&lt;/b&gt; &amp; 기호"
    # 여러 줄에 걸친 굵게도 처리
    assert md_to_html("**두\n줄**") == "<b>두\n줄</b>"
    # 짝이 안 맞는 별표는 그대로 둔다
    assert md_to_html("**열기만") == "**열기만"

    assert split_chunks("짧은 글") == ["짧은 글"]
    long_text = "".join(f"{i}번째 줄입니다\n" for i in range(1000))
    chunks = split_chunks(long_text)
    assert len(chunks) > 1
    assert "".join(chunks) == long_text                      # 내용 유실 없음
    assert all(len(c) <= _CHUNK_LIMIT for c in chunks)       # 전부 제한 이하
    # 줄바꿈 없는 초장문도 제한 이하로 잘리고, 빈 청크가 섞이지 않는다
    huge = split_chunks("x" * 10_000)
    assert "".join(huge) == "x" * 10_000
    assert all(0 < len(c) <= _CHUNK_LIMIT for c in huge)
    # 짧은 줄 + 초장문 줄이 섞여도 마찬가지
    mixed = split_chunks("머리말\n" + "y" * 9_000 + "\n꼬리말")
    assert "".join(mixed) == "머리말\n" + "y" * 9_000 + "\n꼬리말"
    assert all(0 < len(c) <= _CHUNK_LIMIT for c in mixed)

    print("telegram_format 자체 검사 통과")
