---
name: lint
description: ruff로 코드 스타일 검사 및 자동 수정. PR 제출 전 필수 확인.
disable-model-invocation: true
---

## 1. 검사 실행

```bash
uv run ruff check .
```

오류가 없으면 완료 메시지를 출력하세요.

## 2. 자동 수정 가능한 오류가 있는 경우

사용자에게 자동 수정 여부를 물어본 뒤 동의하면 실행하세요:

```bash
uv run ruff check . --fix
```

## 3. 수동 수정이 필요한 오류가 있는 경우

각 오류의 위치와 원인을 설명하고 수정 방법을 제안하세요.

오류 코드 의미:
- `E` — 코드 스타일 (공백, 들여쓰기 등)
- `F` — 미사용 import, 미정의 변수 등
- `I` — import 정렬 순서
