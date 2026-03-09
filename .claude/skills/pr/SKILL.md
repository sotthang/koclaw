---
name: pr
description: koclaw 프로젝트 규칙에 맞게 PR을 생성합니다. 한국어/영어 모두 지원.
disable-model-invocation: true
---

다음 순서로 PR을 생성하세요.

## 1. 사전 확인

```bash
# 현재 브랜치와 변경 내용 확인
git status
git diff main...HEAD
git log main..HEAD --oneline
```

단위 테스트가 통과하는지 확인하세요:

```bash
uv run pytest tests/ --ignore=tests/test_agent_integration.py -q
```

테스트가 실패하면 PR 생성 전에 먼저 수정하도록 안내하세요.

## 2. PR 제목 규칙

커밋 접두어와 동일한 규칙을 사용합니다:

| 유형 | 접두어 예시 |
| --- | --- |
| 새 기능 | `feat: 웹 검색 도구 추가` / `feat: add web search tool` |
| 버그 수정 | `fix: 스케줄러 시간대 오류 수정` / `fix: fix scheduler timezone bug` |
| 구조 개선 | `refactor: LLM 폴백 로직 분리` / `refactor: extract LLM fallback logic` |
| 테스트 | `test: 메모리 도구 테스트 추가` / `test: add memory tool tests` |
| 문서 | `docs: RSS 도구 사용법 추가` / `docs: add RSS tool usage` |

제목은 **50자 이내**로 작성하세요.

## 3. PR 본문 형식

사용자가 한국어를 사용하면 한국어로, 영어를 사용하면 영어로 작성하세요.

**한국어 형식:**
```
## 변경 내용
- 변경 사항을 bullet point로 요약

## 테스트
- [ ] 단위 테스트 통과
- [ ] (해당 시) HELP_TEXT 업데이트 (Slack/Discord 양쪽)
- [ ] (해당 시) README.md 업데이트

## 관련 이슈
closes #이슈번호 (있는 경우)
```

**English format:**
```
## Changes
- Summarize changes in bullet points

## Test plan
- [ ] Unit tests pass
- [ ] (if applicable) HELP_TEXT updated (both Slack/Discord)
- [ ] (if applicable) README.md updated

## Related issue
closes #issue-number (if applicable)
```

## 4. PR 생성

```bash
gh pr create --title "제목" --body "본문" --base main
```

PR 생성 후 URL을 사용자에게 알려주세요.
