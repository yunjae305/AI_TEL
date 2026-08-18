"""
공식 속보 커뮤니티 반응 수집 + 루머 검증 검색.

Gemini Flash의 내장 Google Search 툴을 사용한다.
별도 API 키 불필요 — 기존 Gemini 키 그대로 사용.
"""

import asyncio
import config

from scorer import NewsItem


async def fetch_reactions(item: NewsItem) -> str:
    """
    공식 속보에 대한 커뮤니티 반응을 Google Search로 수집한다.
    후속 메시지용 텍스트를 반환한다.
    결과 없거나 오류 시 빈 문자열 반환.
    """
    return await _search(
        query=f"{item.title} AI community reaction developer response",
        task="이 AI 뉴스에 대한 개발자/AI 커뮤니티(Reddit, HN, Twitter 등)의 반응을 "
             "한국어로 2~3줄로 요약해줘. 반응이 없으면 빈 문자열만 반환해.",
    )


async def search_for_verification(item: NewsItem) -> str:
    """
    루머/커뮤니티 글 검증용 — Google Search로 관련 정보를 찾는다.
    검증 컨텍스트 텍스트를 반환한다. 결과 없으면 빈 문자열 반환.
    """
    return await _search(
        query=f"{item.title} {item.source}",
        task="이 내용이 사실인지 확인할 수 있는 공식 출처나 관련 뉴스를 찾아서 "
             "한국어로 2~3줄로 정리해줘. 관련 정보가 없으면 빈 문자열만 반환해.",
    )


async def _search(query: str, task: str) -> str:
    """Gemini Google Search 툴로 검색하고 결과를 반환한다.

    llm.try_spend()로 하루 호출 예산을 메시지 생성과 공유한다.
    예산이 없으면 검색을 건너넘는다 (검증 없이 발송되고, 그건 허용된 동작).
    """
    if not config.GEMINI_API_KEY:
        return ""
    from llm import try_spend
    if not try_spend():
        print("[community_search] 하루 호출 예산 소진 — 서칭 생략")
        return ""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = await client.aio.models.generate_content(
            model="gemini-3.5-flash",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=400,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
            contents=f"다음 주제로 검색해줘: {query}\n\n{task}",
        )
        text = (response.text or "").strip()
        if text and len(text) > 10:
            print(f"[community_search] 검색 완료 — {query[:40]!r}")
            return text
        return ""
    except Exception as e:
        print(f"[community_search] 검색 실패: {e}")
        return ""
