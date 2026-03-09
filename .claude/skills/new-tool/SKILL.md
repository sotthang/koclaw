---
name: new-tool
description: koclaw에 새 Tool을 TDD 방식으로 추가합니다. 체크리스트 순서대로 안내.
disable-model-invocation: true
---

새 Tool 이름을 `$ARGUMENTS`로 받습니다. 이름이 없으면 먼저 물어보세요.

## 진행 순서

다음 순서를 **하나씩** 진행하세요. 각 단계 완료 후 다음 단계로 넘어가세요.

### 1단계: 테스트 파일 작성 (TDD — Red)

`tests/test_$ARGUMENTS.py`를 먼저 작성합니다.

- `Tool` 인터페이스(`name`, `description`, `parameters`, `execute`, `is_sandboxed`) 검증 테스트 포함
- 핵심 동작에 대한 실패 케이스 포함
- 외부 의존성은 `AsyncMock`으로 격리
- 테스트 실행 후 실패 확인: `uv run pytest tests/test_$ARGUMENTS.py -v`

### 2단계: Tool 구현 (TDD — Green)

`koclaw/tools/$ARGUMENTS.py`를 작성합니다.

```python
from koclaw.core.tool import Tool

class {ToolName}Tool(Tool):
    name = "$ARGUMENTS"
    description = "..."
    is_sandboxed = False  # 외부 API 호출이면 False, 코드 실행이면 True
    parameters = {
        "type": "object",
        "properties": { ... },
        "required": [...],
    }

    async def execute(self, ...) -> str:
        ...
```

규칙:
- 외부에서 가져온 데이터는 반드시 `wrap_external_content()` 로 래핑
- 예외는 사용자 친화적 문자열로 반환 (raise 금지)
- 동기 블로킹 라이브러리는 `asyncio.to_thread()` 로 감싸기

테스트 통과 확인: `uv run pytest tests/test_$ARGUMENTS.py -v`

### 3단계: main.py 등록

`main.py`에 등록합니다:

```python
from koclaw.tools.$ARGUMENTS import {ToolName}Tool
tools.register({ToolName}Tool())
```

### 4단계: HELP_TEXT 업데이트

두 채널 모두 업데이트합니다:

- `koclaw/channels/slack.py` → `HELP_TEXT` 상수 (Slack mrkdwn 형식)
- `koclaw/channels/discord.py` → `HELP_TEXT` 상수 (Discord markdown 형식)

### 5단계: README.md 업데이트

`README.md`의 "지원 도구" 표에 새 도구를 추가합니다.

### 6단계: 전체 테스트 확인

```bash
uv run pytest tests/ --ignore=tests/test_agent_integration.py -v
uv run ruff check .
```

모두 통과하면 완료입니다.
