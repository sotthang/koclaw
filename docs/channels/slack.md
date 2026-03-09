# Slack 설정 가이드

koclaw를 Slack 워크스페이스에 연동하는 방법을 안내합니다.

## 사전 요구사항

- Slack 워크스페이스 관리자 권한
- koclaw 실행 환경 준비 완료 ([README.md](../../README.md) 참고)

---

## 1. Slack 앱 생성

1. [api.slack.com/apps](https://api.slack.com/apps) 접속
2. **Create New App** 클릭
3. **From scratch** 선택
4. App Name 입력 (예: `koclaw`), 워크스페이스 선택 후 **Create App**

---

## 2. Socket Mode 활성화

Slack과 koclaw가 실시간으로 통신하기 위해 Socket Mode를 사용합니다.

1. 좌측 메뉴 **Socket Mode** 클릭
2. **Enable Socket Mode** 토글 ON
3. Token Name 입력 (예: `koclaw-app-token`) 후 **Generate**
4. 발급된 `xapp-...` 토큰을 복사하여 `.env`의 `SLACK_APP_TOKEN`에 저장

---

## 3. Bot Token 발급

1. 좌측 메뉴 **OAuth & Permissions** 클릭
2. **Bot Token Scopes** 섹션에서 아래 scope를 모두 추가

| Scope | 용도 |
| --- | --- |
| `app_mentions:read` | 멘션(`@koclaw`) 읽기 |
| `chat:write` | 메시지 전송 |
| `chat:write.customize` | 메시지 수정 (생각 중... → 응답으로 교체) |
| `im:history` | DM 메시지 읽기 |
| `im:read` | DM 채널 정보 읽기 |
| `im:write` | DM 전송 |
| `reactions:read` | 이모지 반응 읽기 (`:x:` 메시지 삭제 기능) |
| `chat:delete` | 메시지 삭제 |
| `files:read` | 파일 다운로드 (파일 분석 기능) |

3. **Install to Workspace** 클릭 후 권한 승인
4. 발급된 `xoxb-...` 토큰을 복사하여 `.env`의 `SLACK_BOT_TOKEN`에 저장

---

## 4. 이벤트 구독 설정

1. 좌측 메뉴 **Event Subscriptions** 클릭
2. **Enable Events** 토글 ON
3. **Subscribe to bot events** 섹션에서 아래 이벤트를 추가

| 이벤트 | 용도 |
| --- | --- |
| `app_mention` | 채널에서 `@koclaw` 멘션 수신 |
| `message.im` | DM 메시지 수신 |
| `reaction_added` | 이모지 반응 수신 (`:x:` 삭제 기능) |

4. **Save Changes** 클릭

---

## 5. App Home 설정 (DM 활성화)

DM으로 koclaw와 대화하려면 App Home을 활성화해야 합니다.

1. 좌측 메뉴 **App Home** 클릭
2. **Show Tabs** → **Messages Tab** 활성화
3. **Allow users to send Slash commands and messages from the messages tab** 체크

---

## 6. 앱 재설치

이벤트나 scope를 추가한 경우 앱을 재설치해야 변경사항이 적용됩니다.

1. 좌측 메뉴 **OAuth & Permissions** 클릭
2. **Reinstall to Workspace** 클릭 후 승인

---

## 7. .env 설정 확인

```env
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here
```

---

## 8. 실행 및 테스트

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

이벤트 구독 목록에 해당 이벤트가 없는 경우입니다. **4단계**를 다시 확인하고 앱을 재설치하세요.

### 파일 분석이 안 될 때

`files:read` scope가 없는 경우입니다. **3단계**에서 scope를 추가하고 앱을 재설치하세요.

### DM이 수신되지 않을 때

**5단계** App Home의 Messages Tab이 활성화되어 있는지 확인하세요.
