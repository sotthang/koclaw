# koclaw 개발 가이드 (for Claude)

한국형 오픈소스 AI 에이전트. Python, asyncio, SQLite, Slack Socket Mode 기반.

## 핵심 파일 위치

| 역할 | 파일 |
| --- | --- |
| 에이전트 루프 | `koclaw/core/agent.py` |
| LLM 추상화 / 폴백 | `koclaw/core/llm.py` |
| 도구 기반 클래스 | `koclaw/core/tool.py` |
| 스케줄 실행 루프 | `koclaw/core/scheduler_loop.py` |
| 파일 파싱 (PDF/DOCX/HWP) | `koclaw/core/file_parser.py` |
| 메모리 스코프 파싱 | `koclaw/core/memory_context.py` |
| 프롬프트 인젝션 방어 | `koclaw/core/prompt_guard.py` |
| Docker 샌드박스 매니저 | `koclaw/core/sandbox.py` |
| 샌드박스 내부 실행기 | `koclaw/sandbox_runner.py` |
| 채널 라우팅 | `koclaw/channels/__init__.py` |
| 에이전트 팩토리 | `koclaw/app.py` |
| Slack 채널 핸들러 | `koclaw/channels/slack.py` |
| Discord 채널 핸들러 | `koclaw/channels/discord.py` |
| **도움말 텍스트 (Slack)** | `koclaw/channels/slack.py` → `HELP_TEXT` 상수 |
| **도움말 텍스트 (Discord)** | `koclaw/channels/discord.py` → `HELP_TEXT` 상수 |
| DB (SQLite) | `koclaw/storage/db.py` |
| 엔트리포인트 | `main.py` |
| 의존성 / 플러그인 등록 | `pyproject.toml` |
| 환경변수 템플릿 | `.env.example` |

## 기능 추가 체크리스트

### 새 Tool 추가 시

- [ ] `koclaw/tools/{name}.py` — `Tool` 상속, `name` / `description` / `parameters` / `execute` / `is_sandboxed` 구현
- [ ] `tests/test_{name}.py` — TDD: 테스트 먼저 작성
- [ ] `koclaw/channels/slack.py` → `HELP_TEXT` 업데이트 (새 기능 설명 추가)
- [ ] `koclaw/channels/discord.py` → `HELP_TEXT` 업데이트 (새 기능 설명 추가)
- [ ] `main.py` — `tools.register(NewTool())` 추가 (또는 `pyproject.toml` entry-points 등록)
- [ ] `README.md` 지원 도구 표 업데이트

### 새 LLM Provider 추가 시

- [ ] `koclaw/providers/{name}.py` — `LLMProvider` 상속
- [ ] `tests/test_providers.py` — 해당 provider 테스트 추가
- [ ] `koclaw/app.py` → `create_provider()` 분기 추가
- [ ] `.env.example` — 필요한 환경변수 추가

### 새 채널(Discord 등) 추가 시

- [ ] `koclaw/channels/{name}.py` — 채널 핸들러 구현
- [ ] `tests/test_{name}.py` — 테스트 작성
- [ ] `docs/channels/{name}.md` — 설정 매뉴얼 작성 (Slack 매뉴얼 참고)
- [ ] `README.md` 채널 설정 표 업데이트
- [ ] `_TOOL_ICONS` / `_tool_status_text()` 패턴 적용 (tool 실행 중 상태 표시)
- [ ] `handle_message` 내에서 `progress_callback` 생성 후 `agent_fn`에 전달

### DB 스키마 변경 시

- [ ] `koclaw/storage/db.py` → `initialize()` 내 마이그레이션 추가 (기존 DB 호환 유지)
- [ ] 관련 메서드 추가 / 수정
- [ ] `tests/test_db.py` — 마이그레이션 및 새 메서드 테스트

## HELP_TEXT 업데이트 규칙

각 채널의 `HELP_TEXT`는 사용자가 `help`를 입력했을 때 표시되는 안내문입니다.

**새 기능을 추가할 때마다 반드시 두 채널 모두 업데이트해야 합니다.**

| 채널 | 파일 | 형식 |
| --- | --- | --- |
| Slack | `koclaw/channels/slack.py` | Slack mrkdwn (`*굵게*`, `` `코드` ``) |
| Discord | `koclaw/channels/discord.py` | Discord markdown (`**굵게**`, `` `코드` ``) |

- 간결하게: 기능명 + 한 줄 설명 + 예시
- 섹션 구조 유지: 주요 기능 / 스케줄러 / 장기 기억 / 메시지 삭제 / 도움말

## 코딩 컨벤션

- **비동기**: 모든 I/O 작업은 `async/await`
- **동기 블로킹 라이브러리**: `asyncio.to_thread()` 로 감싸서 이벤트 루프 블로킹 방지 (예: DDGS, YouTubeTranscriptApi)
- **Tool**: `is_sandboxed = True` 이면 Docker 컨테이너 내 실행, `False`이면 직접 실행
- **외부 데이터**: 웹 검색·파일·YouTube 등 외부에서 가져온 내용은 반드시 `wrap_external_content()` 로 래핑 (프롬프트 인젝션 방어)
- **에러 처리**: 도구 내 예외는 사용자에게 읽기 좋은 문자열로 반환 (raise 금지)
- **tool 진행 상태**: 채널 핸들러는 `progress_callback` 클로저를 만들어 `agent_fn`에 전달 → `Agent`의 `on_tool_start`로 흘러가 tool 실행 전 메시지 업데이트. 새 채널 추가 시 동일 패턴 적용
- **한국어**: 사용자 노출 문자열은 한국어로 작성
- **타입 힌트**: 함수 시그니처에 타입 힌트 필수

## 개발 환경 셋업

```bash
# 의존성 설치 (dev 포함 전체)
uv sync --all-extras

# 단위 테스트 (빠름, 추천)
uv run pytest tests/ --ignore=tests/test_agent_integration.py

# 전체 테스트 (LLM API 호출 포함, 느림)
uv run pytest tests/
```

- 테스트 파일 위치: `tests/test_{모듈명}.py`
- 비동기 테스트: `async def test_*` (pytest-asyncio 자동 감지)
- 외부 의존성(DB, LLM 등)은 `tmp_path` fixture 또는 `AsyncMock`으로 격리
- LLM API 없이 테스트 가능 — 단위 테스트는 모두 `AsyncMock`으로 격리됨

## 기여 워크플로우

이 프로젝트는 **Fork → PR** 방식을 사용합니다.

```text
1. GitHub에서 레포 fork
2. fork한 레포를 로컬에 clone
3. feature 브랜치 생성: feature/{기능명} 또는 fix/{버그명}
4. 변경 후 fork한 레포에 push
5. 원본 레포 main 브랜치로 PR 제출
```

- 브랜치는 반드시 `main`에서 분기
- PR 하나에 기능 하나 — 여러 기능을 한 PR에 섞지 않음
- PR 제출 전 단위 테스트 전체 통과 확인

## 커밋 규칙

TDD 원칙에 따라 **구조적 변경**과 **행동적 변경**을 분리합니다.

| 유형 | 접두어 | 설명 |
| --- | --- | --- |
| 새 기능 | `feat:` | 동작이 추가되는 변경 |
| 버그 수정 | `fix:` | 잘못된 동작 수정 |
| 구조 개선 | `refactor:` | 동작 변경 없이 코드 정리 |
| 테스트 | `test:` | 테스트 추가/수정 |
| 문서 | `docs:` | 문서만 변경 |

- 구조 개선(`refactor`)과 기능 추가(`feat`)는 반드시 **별도 커밋**으로 분리
- 커밋 메시지는 한국어 또는 영어 모두 허용

## 보안 위협 모델

### 전제 조건

이 프로젝트는 **폐쇄적인 신뢰 환경**을 가정합니다.

- Slack/Discord 봇은 특정 워크스페이스/서버 멤버만 사용 가능
- 사용자는 기본적으로 신뢰할 수 있는 내부 구성원으로 간주

### 구현된 보안 대책

| 위협 | 대책 | 파일 |
| --- | --- | --- |
| 프롬프트 인젝션 | `wrap_external_content()` 로 외부 데이터 경계 표시 | `core/prompt_guard.py` |
| SSRF (웹 검색/파일) | `_is_safe_url()` 로 사설 IP·localhost 차단 | `tools/browse.py` |
| 코드 실행 탈출 | Docker 샌드박스 (`--network none`, 메모리·CPU 제한) | `core/sandbox.py` |
| 무한 루프 | 동일 tool+args 반복 감지 후 강제 중단 | `core/agent.py` |
| 대용량 파일 | 다운로드 전 50MB 제한 | `app.py` |
| SQL 인젝션 | 모든 쿼리 파라미터화 | `storage/db.py` |
| 개인 기억 노출 | `user` scope는 DM 세션에서만 활성화 — 채널에서는 비활성화하여 개인 정보가 채널 멤버에게 노출되지 않도록 함 | `core/memory_context.py` |

> **중요**: `parse_memory_context`에서 `user_scope`를 채널 컨텍스트에도 활성화하면 개인 기억이 공개 채널에 노출될 수 있습니다. `user` scope는 반드시 DM(`D...`, `G...`, `discord:dm:...`) 전용으로 유지하세요.

### 의도적으로 구현하지 않은 것

다음 항목은 **신뢰 환경 가정** 하에 의도적으로 생략되었습니다.
보다 개방적인 환경에 배포할 경우 추가 구현이 필요합니다.

- **SSRF 리다이렉트 추적**: `browse`, `rss`, Discord 파일 다운로더에서 리다이렉트 대상 URL 재검증 없음
- **Slack 파일 URL 출처 검증**: 파일 다운로드 시 Slack 도메인 외 URL 차단 없음
- **채널/사용자 허용 목록(allowlist)**: 특정 채널 또는 사용자만 봇을 사용하도록 제한하는 기능 없음
- **검색 요청 횟수 제한(rate limiting)**: 사용자별 검색 요청 빈도 제한 없음

## 주의사항

- `.env`, `storage/`, `.vscode/` 는 `.gitignore`에 포함 — 절대 커밋하지 않음
- `.claude/settings.local.json`, `.claude/*.md` 는 개인 설정 — 커밋하지 않음
- `.claude/skills/` 는 공유 스킬 — 커밋 대상 (`/test`, `/lint`, `/pr`, `/new-tool` 커맨드)
- `storage/koclaw.db` — 운영 DB, 직접 수정 금지
- DB 마이그레이션은 항상 하위 호환성 유지 (`ALTER TABLE ... ADD COLUMN ... DEFAULT ...`)
