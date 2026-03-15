# GitHub 전략

## 브랜치 전략

- `main` 브랜치에 직접 push 금지
- feature 브랜치 → PR → main 머지
- 브랜치 네이밍: `feat/기능명`, `fix/버그명`, `chore/작업명`

## PR 규칙

- 작은 단위로 자주 생성 (todo.md 항목 단위)
- structural change와 behavioral change는 별도 PR로 분리 (Tidy First)
- PR 제목: `feat: ...`, `fix: ...`, `chore: ...` 형식
- PR 생성은 Claude가 담당, commit/push는 사용자가 직접

## 보안 주의사항

PR 생성 전 diff에서 반드시 확인:

- `.env` 파일 절대 커밋 금지
- `storage/koclaw.db` 커밋 금지
- `storage/workspace/` 커밋 금지

## .gitignore 필수 항목

```text
.env
*.env
storage/koclaw.db
storage/workspace/
__pycache__/
*.pyc
.venv/
```

## 릴리즈 전략

- v0.1.0: core + Slack + 기본 tools (MVP)
- v0.2.0: 파일 파싱 파이프라인
- v0.3.0: Korean tools (HWP)
- v1.0.0: 안정화
