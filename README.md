# koclaw

한국형 오픈소스 AI 에이전트

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![CI](https://github.com/sotthang/koclaw/actions/workflows/ci.yml/badge.svg)](https://github.com/sotthang/koclaw/actions/workflows/ci.yml)

## 특징

- **한국어 우선** — 모든 응답이 기본적으로 한국어로 작성되며, HWP 등 한국 문서 포맷을 지원합니다
- **멀티 LLM 지원** — Claude, GPT, Gemini, Ollama 중 선택 사용, 자동 폴백 지원
- **도구 확장** — 웹 검색, YouTube 요약, PDF/문서 분석, GUI 자동화, 스케줄러, 메모리
- **플러그인 아키텍처** — 커스텀 도구를 플러그인으로 추가 가능
- **채널 연동** — Slack, Discord 지원
- **가상 데스크탑** — Docker 기반 가상 환경에서 브라우저 조작, 클릭, 스크린샷 등 Computer Use
- **계층형 메모리** — 유저/채널/스레드 단위 장기 기억 저장, 대화 자동 요약

## 빠른 시작 (Docker)

```bash
# 1. 저장소 클론
git clone https://github.com/sotthang/koclaw.git
cd koclaw

# 2. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 설정 진행

# 3. 실행
./start.sh
```

## 로컬 개발 환경

Python 3.12 이상이 필요합니다. 패키지 관리는 [uv](https://docs.astral.sh/uv/)를 권장합니다.

```bash
# uv 설치 (없는 경우)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 의존성 설치
uv sync --all-extras

# 실행
uv run python main.py
```

### 테스트

```bash
# 단위 테스트 (빠름, 추천)
uv run pytest tests/ --ignore=tests/test_agent_integration.py

# 전체 테스트 (LLM API 호출 포함)
uv run pytest tests/
```

## 환경변수 설정

`.env.example`을 복사하여 `.env`를 만들고 아래 항목을 채웁니다.

| 변수 | 설명 | 필수 |
| --- | --- | --- |
| `DEFAULT_LLM_PROVIDER` | 기본 LLM (`claude` / `openai` / `gemini` / `ollama`) | ✅ |
| `FALLBACK_LLM_PROVIDERS` | 폴백 순서 (예: `claude,gemini`) — 기본 provider 실패 시 순서대로 시도 | 선택 |
| `CLAUDE_MODEL` | Claude 모델명 (예: `claude-sonnet-4-6`) | 선택 |
| `OPENAI_MODEL` | OpenAI 모델명 (예: `gpt-5.3`) | 선택 |
| `GEMINI_MODEL` | Gemini 모델명 (예: `gemini-3-flash-preview`) | 선택 |
| `OLLAMA_MODEL` | Ollama 모델명 (예: `llama3`, `qwen3:8b`) | 선택 |
| `ANTHROPIC_API_KEY` | Claude 사용 시 필요 | 조건부 |
| `OPENAI_API_KEY` | GPT 사용 시 필요 | 조건부 |
| `GEMINI_API_KEY` | Gemini 사용 시 필요 | 조건부 |
| `OLLAMA_BASE_URL` | Ollama 사용 시 (기본: `http://localhost:11434/v1`) | 조건부 |
| `SLACK_BOT_TOKEN` | Slack 봇 토큰 (`xoxb-...`) | Slack 사용 시 |
| `SLACK_APP_TOKEN` | Slack 앱 토큰 (`xapp-...`) | Slack 사용 시 |
| `DISCORD_BOT_TOKEN` | Discord 봇 토큰 | Discord 사용 시 |

## 기본 사용법

### 대화 시작

| 채널 | 방법 |
| --- | --- |
| Slack DM | 봇에게 직접 메시지 전송 |
| Slack 채널 | 채널에서 바로 메시지 또는 `@봇이름 질문` |
| Slack 스레드 | 스레드 내에서 바로 메시지 또는 `@봇이름 질문` |
| Discord DM | 봇에게 직접 메시지 전송 |
| Discord 서버 채널 | 채널에서 바로 메시지 또는 `@봇이름 질문` |

도움말을 보려면 `help` 또는 `/help`를 입력하세요.

### 주요 기능

#### 웹 검색 · 웹페이지 읽기

```text
최근 AI 뉴스 알려줘
https://example.com 이 페이지 요약해줘
```

#### RSS 피드

별도 설정 없이 자연어로 요청하면 됩니다. LLM이 RSS URL을 알아서 찾아서 사용합니다.

```text
해커뉴스 최신 글 5개 요약해줘
연합뉴스 IT 뉴스 가져와줘
https://example.com/feed.xml 읽어줘
```

#### YouTube 요약

```text
https://youtu.be/... 이 영상 요약해줘
```

> **참고**: 자막(자동 생성 포함)이 없는 영상은 요약이 불가능합니다.

#### 파일 분석

PDF, DOCX, HWPX, 이미지를 첨부하면 자동으로 분석합니다.

#### 가상 데스크탑 제어 (Computer Use)

Docker 컨테이너 안의 가상 데스크탑을 AI가 직접 조작합니다. `koclaw-computer-use` 이미지가 빌드되어 있어야 합니다.

```text
네이버 열고 AI 뉴스 검색해서 스크린샷 찍어줘
https://example.com 열고 로그인 버튼 눌러줘
구글에서 파이썬 튜토리얼 검색하고 첫 번째 결과 열어줘
```

지원 액션: `screenshot` (화면 캡처) · `click` (좌표 클릭) · `type` (텍스트 입력) · `key` (키 입력) · `open_url` (URL 열기) · `scroll` (스크롤)

> **참고**: Docker가 설치되어 있어야 합니다. `./start.sh` 실행 시 자동으로 이미지가 빌드됩니다.

#### 스케줄러

```text
매일 오전 9시에 AI 뉴스 요약해줘
매주 월요일 오전 10시에 주간 회의 알림
내 스케줄 보여줘
AI 뉴스 알림 삭제해줘
```

#### 메모리 (장기 기억)

koclaw는 대화를 넘어 정보를 기억할 수 있습니다. LLM이 자동으로 중요한 정보를 저장하거나, 직접 요청할 수도 있습니다.

```text
내 이름은 홍길동이야, 기억해줘       → DM에서 개인 기억으로 저장
이 채널은 백엔드 개발팀 채널이야      → 채널 기억으로 저장 (스레드에도 적용)
이 스레드는 API 리뷰 논의야           → 스레드 기억으로 저장
내 정보 지워줘                        → 메모리 삭제
```

메모리 범위별 적용 규칙:

| 범위 | 저장 조건 | 적용 컨텍스트 |
| --- | --- | --- |
| `user` | DM에서만 저장 가능 | DM 대화에만 적용 (프라이버시 보호) |
| `channel` | 채널/스레드에서 저장 가능 | 해당 채널 + 채널의 모든 스레드 |
| `thread` | 스레드에서만 저장 가능 | 해당 스레드에만 적용 |

> **프라이버시**: 개인 정보(`user` 범위)는 DM에서만 사용됩니다. 공개 채널에서는 채널 단위 기억만 적용되므로 개인 정보가 다른 멤버에게 노출되지 않습니다.

#### 대화 자동 요약

대화가 20턴을 넘으면 이전 대화를 자동으로 요약하여 컨텍스트를 유지합니다. 별도 조작이 필요 없습니다.

#### 메시지 삭제

koclaw가 보낸 메시지에 `:x:` (Slack) 또는 `❌` (Discord) 이모지를 달면 해당 메시지가 삭제됩니다.

## 지원 도구

| 도구 | 설명 |
| --- | --- |
| `web_search` | DuckDuckGo 웹 검색 (한국어 최적화) |
| `browse` | URL 웹페이지 내용 읽기 및 분석 |
| `rss_feed` | RSS/Atom 피드 구독 (뉴스·블로그·GitHub 릴리즈 등) |
| `youtube` | YouTube 동영상 자막 기반 내용 요약 |
| `scheduler` | 알림 스케줄 등록/조회/수정/삭제 (단발/반복) |
| `memory` | 유저/채널/스레드 범위 장기 기억 저장·조회·삭제 |
| `send_email` | Gmail SMTP로 이메일 전송 (`GMAIL_USER` / `GMAIL_APP_PASSWORD` 필요) |
| `computer_use` | 가상 데스크탑 제어 — 브라우저 열기, 클릭, 입력, 스크린샷 (Docker 필요) |
| 파일 분석 | PDF, DOCX, HWP, 이미지 자동 파싱 (첨부파일 전송 시 자동) |

## Ollama (로컬 LLM)

API 비용 없이 로컬에서 LLM을 실행할 수 있습니다.

```bash
# Ollama 컨테이너 실행
docker compose -f docker-compose.ollama.yml up -d

# 모델 다운로드 (예: llama3, gemma3, qwen2.5 등)
docker exec -it koclaw-ollama-1 ollama pull llama3

# .env 설정
DEFAULT_LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
DEFAULT_MODEL=llama3
```

사용 가능한 모델 목록은 [ollama.com/library](https://ollama.com/library)에서 확인하세요.

> GPU가 없으면 응답이 느릴 수 있습니다. GPU 사용 시 `docker-compose.ollama.yml`의 주석을 해제하세요.

## 채널 설정

| 채널 | 설정 문서 |
| --- | --- |
| Slack | [docs/channels/slack.md](docs/channels/slack.md) |
| Discord | [docs/channels/discord.md](docs/channels/discord.md) |

## 아키텍처

```text
koclaw/
├── core/
│   ├── agent.py                # ReAct 에이전트 루프
│   ├── llm.py                  # LLM 추상화 / 폴백
│   ├── tool.py                 # 도구 기반 클래스 / 레지스트리
│   ├── scheduler_loop.py       # 스케줄 실행 루프
│   ├── file_parser.py          # 파일 파싱 (PDF/DOCX/HWP)
│   ├── memory_context.py       # 메모리 스코프 파싱
│   ├── prompt_guard.py         # 프롬프트 인젝션 방어
│   └── computer_use_manager.py # 가상 데스크탑 Docker 컨테이너 관리
├── providers/
│   ├── claude.py          # Anthropic Claude
│   ├── openai.py          # OpenAI GPT
│   ├── gemini.py          # Google Gemini
│   └── ollama.py          # Ollama (로컬)
├── tools/
│   ├── search.py          # 웹 검색
│   ├── browse.py          # 웹페이지 읽기
│   ├── rss.py             # RSS/Atom 피드
│   ├── youtube.py         # YouTube 요약
│   ├── scheduler.py       # 스케줄 관리
│   ├── memory.py          # 장기 기억 (DB 기반)
│   ├── file.py            # 파일 읽기/목록
│   └── computer_use.py    # 가상 데스크탑 제어
├── channels/
│   ├── slack.py           # Slack 채널 핸들러
│   └── discord.py         # Discord 채널 핸들러
├── storage/
│   └── db.py              # SQLite 비동기 DB
└── app.py                 # 에이전트 팩토리 / 설정
```

### DB 스키마

| 테이블 | 용도 |
| --- | --- |
| `messages` | 세션별 대화 히스토리 |
| `session_summaries` | 대화 요약 (20턴 초과 시 자동 생성) |
| `memories` | 유저/채널/스레드 범위 장기 기억 |
| `scheduled_tasks` | 스케줄 작업 목록 |

## 커스텀 도구 추가

`koclaw.core.tool.Tool`을 상속하면 됩니다.

```python
from koclaw.core.tool import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "설명"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "입력값"},
        },
        "required": ["input"],
    }

    async def execute(self, input: str) -> str:
        return f"결과: {input}"
```

`pyproject.toml`의 `[project.entry-points."koclaw.tools"]`에 등록하면 자동으로 로드됩니다.

## 기여하기 (Contributing)

기여를 환영합니다! Fork → PR 방식을 사용합니다.

### Claude Code 기반 개발 권장

이 프로젝트는 **[Claude Code](https://claude.ai/claude-code)** 를 개발 도구로 적극 활용합니다.

`.claude/` 디렉토리에 프로젝트 전략 문서가 포함되어 있습니다:

| 파일 | 내용 |
| --- | --- |
| `CLAUDE.md` | 아키텍처, 코딩 컨벤션, 기능 추가 체크리스트 |
| `.claude/github-strategy.md` | 브랜치 전략, PR 규칙, 릴리즈 전략 |

Claude Code를 사용하면 이 문서들이 자동으로 컨텍스트에 로드되어, 프로젝트 컨벤션에 맞는 코드 생성과 PR 작성을 도와줍니다. Claude Code 없이도 기여 가능하지만, 사용을 권장합니다.

### 로컬 개발 환경 셋업

```bash
# 1. 레포 fork 후 clone
git clone https://github.com/{your-username}/koclaw.git
cd koclaw

# 2. 의존성 설치
uv sync --all-extras

# 3. 테스트 실행 (LLM API 없이 동작)
uv run pytest tests/ --ignore=tests/test_agent_integration.py
```

### PR 제출 방법

```bash
# feature 브랜치 생성
git checkout -b feature/{기능명}

# 작업 후 push
git push origin feature/{기능명}
```

이후 GitHub에서 `sotthang/koclaw` 의 `main` 브랜치로 PR을 제출하세요.

### 기여 규칙

- PR 하나에 기능/수정 하나
- 새 기능은 반드시 테스트 포함 (TDD 권장)
- 모든 단위 테스트 통과 후 PR 제출
- 코딩 컨벤션 및 기여 워크플로우 상세 내용은 [CLAUDE.md](CLAUDE.md) 참고

## 보안

이 프로젝트는 **폐쇄적인 신뢰 환경(사내 Slack/Discord 등)**을 가정합니다.

구현된 보안 대책: 프롬프트 인젝션 방어, SSRF 차단, 무한 루프 감지, 파일 크기 제한, SQL 파라미터화.

외부 공개 환경에 배포할 경우 추가 보안 조치가 필요합니다. 자세한 위협 모델 및 의도적 생략 항목은 [CLAUDE.md](CLAUDE.md)의 "보안 위협 모델" 섹션을 참고하세요.

## 라이선스

MIT License — 자유롭게 사용, 수정, 배포 가능합니다.
