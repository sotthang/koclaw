# Discord 설정 가이드

koclaw를 Discord 서버에 연동하는 방법을 안내합니다.

## 사전 요구사항

- Discord 계정
- koclaw 실행 환경 준비 완료 ([README.md](../../README.md) 참고)
- `discord.py` 설치: `pip install "koclaw[discord]"` 또는 `pip install discord.py`

---

## 1. Discord 애플리케이션 생성

1. [discord.com/developers/applications](https://discord.com/developers/applications) 접속
2. **New Application** 클릭
3. 이름 입력 (예: `koclaw`) 후 **Create**

---

## 2. Bot 생성 및 토큰 발급

1. 좌측 메뉴 **Bot** 클릭
2. **Add Bot** 클릭 → 확인
3. **Token** 섹션에서 **Reset Token** 클릭 후 토큰 복사
4. 복사한 토큰을 `.env`의 `DISCORD_BOT_TOKEN`에 저장

---

## 3. Privileged Intents 활성화

Bot이 메시지 내용을 읽으려면 반드시 아래 권한을 활성화해야 합니다.

1. 좌측 메뉴 **Bot** → **Privileged Gateway Intents** 섹션
2. **MESSAGE CONTENT INTENT** 토글 ON
3. **Save Changes** 클릭

> ⚠️ 이 설정이 없으면 봇이 메시지 내용을 읽지 못해 응답하지 않습니다.

---

## 4. 서버 초대 URL 생성

1. 좌측 메뉴 **OAuth2 → URL Generator** 클릭
2. **Scopes**에서 `bot` 체크
3. **Bot Permissions**에서 아래 권한 체크

   | 권한 | 용도 |
   | --- | --- |
   | `messages.read / dm_channels.messages.read` | 채널 메시지 읽기 |
   | `Send Messages` | 메시지 전송 |
   | `Read Message History` | 대화 히스토리 접근 |
   | `Attach Files` | 파일 첨부 (코드 실행 결과 등) |

4. 생성된 URL을 브라우저에서 열어 봇을 서버에 초대

---

## 5. .env 설정

```env
DISCORD_BOT_TOKEN=your-bot-token-here
```

---

## 6. 실행 및 테스트

`.env`에 `DISCORD_BOT_TOKEN`이 설정되어 있으면 `main.py` 실행만으로 Discord 봇이 자동 활성화됩니다.

```bash
# Docker
docker compose up --build

# 또는 로컬 실행
uv run python main.py
```

Discord 서버에서 `@koclaw 안녕` 또는 봇에게 DM을 보내 정상 작동을 확인합니다.

> Slack과 Discord를 동시에 사용할 수 있습니다. 두 채널의 환경변수를 모두 설정하면 `main.py` 하나로 동시 운영됩니다.

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

---

## 문제 해결

### 봇이 메시지에 응답하지 않을 때

**3단계** MESSAGE CONTENT INTENT가 활성화되어 있는지 확인하세요.
서버 채널에서는 반드시 `@koclaw`로 멘션해야 응답합니다 (DM은 멘션 불필요).

### 봇이 서버에 보이지 않을 때

**4단계**에서 생성한 초대 URL을 다시 사용해 서버에 초대하세요.

### 파일 분석이 안 될 때

Discord 파일 첨부 URL은 일정 시간 후 만료됩니다. 파일 업로드 직후 분석을 요청하세요.
