# AIField 🛰️

AI 관련 공식 발표, 논문, 오픈소스 모델, 커뮤니티 떡밥을 자동 수집·분류해서 텔레그램으로 알려주는 AI 뉴스 속보봇 시스템.

---

## 봇 구성

### AIField-파수인
AI 씬을 지켜보고 걸러서 전하는 단일 봇. 떡밥을 먼저 잡아내는 일과 그게 진짜인지 확인하는 일을 한 메시지 안에서 같이 끝낸다.

감정 표현이 서툴러 말이 담백하지만, 그 안에 깊은 헌신이 있다. 지금의 소란에 휩쓸리지 않고 몇 년 뒤에도 남을 것이 무엇인지를 먼저 본다.

> '파수인'은 비밀이나 기지를 지킨다는 뜻이 아니라, 떠도는 이를 묵묵히 지켜준다는 뜻이다.

말투는 조용한 **해요체 존댓말**. 자신은 '저', 상대는 언제나 **'당신'**이라고 부른다. 말줄임표는 쓰지 않는다.

> "당신, 하나 걸렸어요."
> "아직 공식 발표는 확인되지 않았어요."
> "당신, 무리하지 마세요. 핵심만 먼저 보셔도 돼요."

---

## 동작 방식

```
루머/떡밥 발견 시
  검증 서칭 (Google Search) → 파수인이 검증 결과까지 담아 한 메시지로 포스팅

공식 속보 발견 시
  파수인 → 라이브 채팅 즉시 포스팅
    └─ 45분 뒤 커뮤니티 반응이 모이면 후속 메시지

정기 브리핑
  파수인 → 브리핑 채팅 (09:00 / 21:00 KST)
```

---

## 수집 소스

| 소스 | 종류 | 신뢰도 |
|------|------|--------|
| OpenAI Blog | 공식 RSS | 5 |
| Google DeepMind Blog | 공식 RSS | 5 |
| Anthropic News | 공식 스크래핑 | 5 |
| HuggingFace Blog | 공식 RSS | 4 |
| NVIDIA AI Blog | 공식 RSS | 4 |
| Meta Engineering Blog | 공식 RSS | 4 |
| Hacker News | 커뮤니티 | 3 |
| Reddit (LocalLLaMA, MachineLearning) | 커뮤니티 | 3 |
| HuggingFace Models | 급상승 모델 | 3 |
| DCInside 싱귤래리티 갤 | 커뮤니티 | 3 |

수집 주기: **60분**

---

## 알림 레벨

| 레벨 | 조건 | 처리 |
|------|------|------|
| Level 5 | 공식 대형 발표, 신뢰도 5, 긴급도 5 | 즉시 알림 |
| Level 4 | 중요 논문, 큰 오픈소스 모델 | 즉시 알림 |
| Level 3 | 브리핑에 넣을 만한 소식 | 하루 브리핑 포함 |
| Level 2 | 커뮤니티 떡밥, 약한 루머 | DB 저장만 |
| Level 1 | 중복, 출처 없는 과장글 | 무시 |

---

## 기술 스택

- **Python 3.11+** / python-telegram-bot
- **Gemini 3.5 Flash** — 봇 메시지 생성 + 검증 서칭 (Google Search 툴)
- **SQLite** — 수집 데이터 저장 및 중복 필터링
- **aiohttp + feedparser + BeautifulSoup4** — RSS/웹 수집

---

## 파일 구조

```
AIField/
├── main.py                 # 진입점 (--live / --test / --briefing-now)
├── config.py               # 환경변수 로드
├── scorer.py               # 점수 채점 로직
├── scheduler.py            # 수집·브리핑 스케줄러
├── llm.py                  # Gemini API 래퍼 + 호출 예산 가드
├── bot.py                  # 파수인 텔레그램 봇
├── telegram_format.py      # 마크다운→HTML 변환, 메시지 분할
├── deploy/
│   ├── setup.sh            # 서버 초기 세팅 스크립트
│   └── aifield.service     # systemd 유닛
├── prompts/
│   └── pasuin_system.py    # 파수인 시스템 프롬프트 + 메시지 프롬프트
├── collectors/
│   ├── rss.py              # 공식 RSS 수집기
│   ├── hacker_news.py      # Hacker News 수집기
│   ├── reddit.py           # Reddit 수집기
│   ├── huggingface.py      # HuggingFace 모델 수집기
│   ├── dcinside.py         # DCInside 갤러리 스크래퍼
│   ├── anthropic.py        # Anthropic 공식 뉴스 스크래퍼
│   └── community_search.py # 검증 서칭 / 커뮤 반응 수집
└── db/
    └── news_store.py       # SQLite 저장·중복 필터
```

---

## 설치 및 실행

### 1. 패키지 설치
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 텔레그램 봇 생성 + 채팅 ID 확인
1. [@BotFather](https://t.me/BotFather)에게 `/newbot`으로 봇 하나를 생성하고 토큰을 받는다.
2. 알림 받을 그룹(또는 채널)에 봇을 초대한다. 개인 DM으로 받으려면 봇과의 1:1 대화만 열면 된다.
3. 봇에게 아무 메시지나 보낸 뒤 `https://api.telegram.org/bot<토큰>/getUpdates`에 접속해 `chat.id` 값을 확인한다 (그룹 ID는 보통 음수).

### 3. 환경변수 설정
```bash
cp .env.example .env
# .env 파일에 값 채우기
```

```env
AIFIELD_BOT_TOKEN=
AIFIELD_LIVE_CHAT_ID=
AIFIELD_BRIEFING_CHAT_ID=
GEMINI_API_KEY=          # 없으면 고정 포맷으로 fallback
GEMINI_DAILY_BUDGET=120  # 선택. 하루 Gemini 호출 상한
```

### 4. 실행
```bash
# 더미 데이터로 텔레그램 흐름 테스트
python main.py

# 실제 수집 + 스케줄러 실행
python main.py --live
```

---

## 봇 명령어

| 명령어 | 설명 |
|--------|------|
| `/status` | 봇 상태, DB 통계, 남은 Gemini 예산 확인 |
| `/scan_now` | 즉시 수집 실행 |
| `/briefing_now` | 즉시 브리핑 발송 |

그룹에서 명령어가 반응 안 하면 `/status@봇username` 형태로 입력한다.

---

## 무료 티어 호출 제한

Gemini 무료 티어를 넘지 않도록 두 겹으로 막는다.

- **빈도**: 수집 60분 주기, 사이클당 공식 2건 / 루머 1건 → 최대 192회/일
- **하드 상한**: `GEMINI_DAILY_BUDGET`(기본 120). 메시지 생성과 검증 서칭이 예산을 공유하고,
  소진되면 API를 호출하지 않고 고정 포맷으로 나간다. 봇은 계속 돌아간다.

예산 카운터는 프로세스 메모리에만 있어 재시작하면 0으로 리셋된다.

---

## 서버 배포 (Ubuntu + systemd)

24시간 운영하려면 항상 켜져 있는 리눅스 서버가 필요하다. 서버리스(Lambda, Vercel 등)는
장시간 실행 프로세스가 아니라서 맞지 않고, 파일시스템이 휘발성인 환경도 곤란하다
(`db/aifield.db`가 날아가면 중복 필터가 초기화돼 같은 뉴스를 다시 알린다).

Oracle Cloud Always Free(춘천/서울 리전)나 AWS Lightsail(서울)이 무난하다.
국내 커뮤니티 수집 때문에 한국 리전이 유리하다.

```bash
git clone https://github.com/yunjae305/AI_TEL.git ~/aifield
cd ~/aifield
bash deploy/setup.sh     # 시간대 KST, venv, 의존성, systemd 등록
nano .env                # 토큰과 chat_id 입력 (스크립트는 .env를 건드리지 않는다)

./venv/bin/python main.py        # 더미 데이터로 발송 확인
sudo systemctl start aifield     # 실운영 시작
journalctl -u aifield -f         # 로그
```

`deploy/aifield.service`에는 크래시 루프 방지 설정(`StartLimitBurst=5`)이 들어 있다.
Gemini 하루 예산 카운터가 프로세스 메모리에 있어서 재시작마다 0으로 리셋되기 때문에,
무한 재시작에 빠지면 무료 티어를 통째로 소진할 수 있다. 이 설정이 그것을 막는다.

인바운드 포트는 열 필요가 없다. 봇은 텔레그램으로 아웃바운드 연결만 한다.
