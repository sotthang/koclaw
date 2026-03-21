# Telegram 설정 가이드

koclaw를 Telegram에 연동하는 방법을 안내합니다.

## 사전 요구사항

- Telegram 계정
- koclaw 실행 환경 준비 완료 ([README.md](../../README.md) 참고)
- `python-telegram-bot` 설치: `pip install "koclaw[telegram]"`

---

## 1. BotFather로 봇 생성

1. Telegram에서 [@BotFather](https://t.me/BotFather) 검색 후 시작
2. `/newbot` 명령 입력
3. 봇 이름 입력 (예: `koclaw`)
4. 봇 사용자명 입력 — 반드시 `bot`으로 끝나야 함 (예: `koclaw_bot`)
5. 발급된 **API 토큰**을 복사

---

## 2. .env 설정

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCDefGhIJKlmNoPQRsTUVwxyZ
```

---

## 3. 그룹에서 모든 메시지 수신 설정 (선택)

기본적으로 그룹에서는 `@봇이름 멘션` 또는 봇 메시지에 답장할 때만 응답합니다.

그룹의 **모든 메시지**에 응답하게 하려면 Privacy Mode를 비활성화하세요.

1. BotFather에서 `/setprivacy` 입력
2. 봇 선택
3. `Disable` 선택

> **보안 주의**: Privacy Mode를 비활성화하면 봇이 그룹의 모든 메시지를 읽을 수 있습니다. 신뢰할 수 있는 그룹에서만 사용하세요. 기본(Privacy Mode 활성화) 상태에서도 @멘션과 답장으로 충분히 사용 가능합니다.

---

## 4. 실행 및 테스트

`.env`에 `TELEGRAM_BOT_TOKEN`이 설정되어 있으면 `main.py` 실행만으로 Telegram 봇이 자동 활성화됩니다.

```bash
# Docker
docker compose up --build

# 또는 로컬 실행
uv run python main.py
```

Telegram에서 봇에게 DM을 보내거나 그룹에 추가한 뒤 `@봇이름 안녕`으로 정상 작동을 확인합니다.

---

## 세션 ID 구조

| 컨텍스트 | 세션 ID 형식 |
| --- | --- |
| DM | `telegram:dm:{chat_id}` |
| 그룹 / 슈퍼그룹 | `telegram:{chat_id}` |
| 포럼 토픽 | `telegram:topic:{chat_id}:{thread_id}` |

스케줄러 알림, 웹훅 알림 등은 이 세션 ID 기반으로 전달됩니다.

---

## 사용 예시

### DM 대화

```text
사용자: 오늘 AI 뉴스 요약해줘
koclaw: (웹 검색 후 요약 응답)
```

### 그룹 멘션

```text
사용자: @koclaw 이 PDF 분석해줘  (파일 첨부)
koclaw: (파일 내용 분석 후 응답)
```

### 봇 메시지에 답장 (그룹)

```text
koclaw: (이전 응답)
사용자: [봇 메시지에 답장] 더 자세히 설명해줘
koclaw: (이어서 답변)
```

### 스케줄 등록

```text
사용자: 매일 오전 9시에 AI 뉴스 요약해줘
koclaw: ✅ 스케줄이 등록되었습니다: 'AI 뉴스 요약' (daily 반복)
```

---

## 문제 해결

### 봇이 그룹에서 응답하지 않을 때

`@봇이름`으로 멘션했는지 확인하세요. Privacy Mode가 활성화된 경우 멘션 또는 봇 메시지에 답장해야만 응답합니다.

그룹에서 봇이 메시지 권한이 없다면, 봇을 그룹에서 제거 후 다시 추가하세요.

### 포럼 토픽에서 응답하지 않을 때

슈퍼그룹의 포럼 기능이 활성화되어 있어야 합니다. 토픽 안에서 `@봇이름`으로 멘션하세요.

### 파일 첨부가 인식되지 않을 때

Telegram의 파일 크기 제한(기본 20MB)을 확인하세요. 이미지는 사진(`photo`)으로 전송하거나 파일(`document`)로 전송 모두 지원합니다.

---

> Slack, Discord, Telegram을 동시에 사용할 수 있습니다. 각 채널의 환경변수를 모두 설정하면 `main.py` 하나로 동시 운영됩니다.
