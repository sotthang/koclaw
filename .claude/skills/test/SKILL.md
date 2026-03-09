---
name: test
description: koclaw 단위 테스트 실행 (LLM API 호출 제외). 코드 변경 후 빠른 검증용.
disable-model-invocation: true
---

다음 명령어로 단위 테스트를 실행하세요:

```bash
uv run pytest tests/ --ignore=tests/test_agent_integration.py -v
```

- 테스트가 모두 통과하면 결과를 간단히 요약하세요.
- 실패한 테스트가 있으면 원인을 분석하고 수정 방법을 제안하세요.
- `test_agent_integration.py`는 LLM API 호출이 필요해 제외합니다. 전체 테스트가 필요하면 `uv run pytest tests/`를 사용하세요.
