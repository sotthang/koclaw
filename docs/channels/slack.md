# Slack 설정 가이드

koclaw를 Slack 워크스페이스에 연동하는 방법을 안내합니다.

## 사전 요구사항

- Slack 워크스페이스 관리자 권한
- koclaw 실행 환경 준비 완료 ([README.md](../../README.md) 참고)

---

## 1. Slack 앱 생성 (매니페스트 사용)

1. [api.slack.com/apps](https://api.slack.com/apps) 접속
2. **Create New App** 클릭
3. **From a manifest** 선택
4. 워크스페이스 선택 후 **Next**
5. 아래 JSON을 붙여넣고 **Next** → **Create**

```json
{
  "display_information": {
    "name": "koclaw",
    "description": "AI 에이전트 봇"
  },
  "features": {
    "app_home": {
      "home_tab_enabled": false,
      "messages_tab_enabled": true,
      "messages_tab_read_only_enabled": false
    },
    "bot_user": {
      "display_name": "koclaw",
      "always_online": true
    }
  },
  "oauth_config": {
    "scopes": {
      "bot": [
        "app_mentions:read",
        "chat:write",
        "chat:write.customize",
        "chat:delete",
        "files:read",
        "im:history",
        "im:read",
        "im:write",
        "reactions:read"
      ]
    }
  },
  "settings": {
    "event_subscriptions": {
      "bot_events": [
        "app_mention",
        "message.im",
        "reaction_added"
      ]
    },
    "interactivity": {
      "is_enabled": false
    },
    "socket_mode_enabled": true,
    "token_rotation_enabled": false
  }
}
```

---

## 2. 토큰 발급

### App-Level Token (SLACK_APP_TOKEN)

1. 좌측 메뉴 **Basic Information** 클릭
2. **App-Level Tokens** 섹션 → **Generate Token and Scopes**
3. Token Name 입력 (예: `koclaw-app-token`), `connections:write` 스코프 추가 후 **Generate**
4. 발급된 `xapp-...` 토큰을 `.env`의 `SLACK_APP_TOKEN`에 저장

### Bot Token (SLACK_BOT_TOKEN)

1. 좌측 메뉴 **OAuth & Permissions** 클릭
2. **Install to Workspace** 클릭 후 권한 승인
3. 발급된 `xoxb-...` 토큰을 `.env`의 `SLACK_BOT_TOKEN`에 저장

---

## 3. .env 설정 확인

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
```

---

## 4. 실행 및 테스트

```bash
# Docker
docker compose up --build

# 또는 로컬 실행
uv run python main.py
```

Slack 워크스페이스에서 koclaw 앱을 DM하거나 채널에서 `@koclaw 안녕`을 입력해 정상 작동을 확인합니다.

---

## 사용 예시

### DM 대화

```text
사용자: 오늘 AI 뉴스 요약해줘
koclaw: (웹 검색 후 요약 응답)
```

### 채널 멘션

```text
사용자: @koclaw 이 PDF 분석해줘  (파일 첨부)
koclaw: (파일 내용 분석 후 응답)
```

### 스케줄 등록

```text
사용자: 매일 오전 9시에 백엔드 트렌드 알려줘
koclaw: ✅ 스케줄이 등록되었습니다: '백엔드 트렌드 알림' (daily 반복)
```

### 메시지 삭제

koclaw가 보낸 메시지에 `:x:` 이모지 반응을 달면 해당 메시지가 Slack과 DB에서 모두 삭제됩니다.

---

## 문제 해결

### `unhandled request` 경고가 나타날 때

이벤트 구독 목록에 해당 이벤트가 없는 경우입니다. 매니페스트의 `bot_events`를 확인하고 앱을 재설치하세요.

### 파일 분석이 안 될 때

`files:read` scope가 없는 경우입니다. **OAuth & Permissions**에서 scope를 추가하고 앱을 재설치하세요.

### DM이 수신되지 않을 때

**App Home** → Messages Tab이 활성화되어 있는지 확인하세요. 매니페스트에서는 `messages_tab_enabled: true`로 자동 설정됩니다.
