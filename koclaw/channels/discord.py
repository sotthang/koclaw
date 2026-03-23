import logging
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HELP_TEXT = """\
**koclaw 사용 가이드**

**기본 대화**
• DM, 서버 채널, 또는 @멘션으로 채팅할 수 있습니다

**주요 기능**
• **웹 검색** — 최신 정보, 뉴스, 기술 트렌드 등 검색
• **웹페이지 읽기** — URL을 주면 페이지 전체 내용을 분석
• **RSS 피드** — 뉴스·블로그·GitHub 릴리즈 등 RSS 피드 구독
  - `해커뉴스 최신 글 5개 요약해줘`
  - `https://example.com/feed.xml 읽어줘`
• **날씨 조회** — 전 세계 도시의 현재 날씨와 최저·최고 기온
  - `서울 날씨 알려줘`
  - `도쿄 오늘 날씨 어때?`
• **YouTube 요약** — 동영상 링크를 보내면 내용을 요약
• **파일 분석** — PDF, DOCX, HWPX, 이미지 첨부 시 자동 분석
• **Windows PowerShell 실행** — Windows PC에서 PowerShell 명령 실행 (Windows Agent 필요)
  - `C 드라이브 용량 얼마나 남았어?`
  - `실행 중인 프로세스 상위 10개 보여줘`
  - `Windows 서비스 목록 확인해줘`
• **브라우저 자동화** — Playwright DOM 기반 웹 제어 (좌표 없이 selector로 클릭·입력) (Windows Agent 필요)
  - `네이버 열고 로그인 버튼 눌러줘` — text selector 자동 탐지
  - `이 페이지에서 검색창에 "AI" 입력하고 검색해줘`
• **가상 데스크탑 제어** — 브라우저 열기, 클릭, 입력, 스크린샷 등 GUI 자동화 (Docker 필요)
  - `네이버에서 AI 뉴스 검색해서 스크린샷 찍어줘`
  - `https://example.com 열고 로그인 버튼 눌러줘`
  - `이 CSV 파일로 matplotlib 차트 그려서 파일로 줘` — 컨테이너 파일 채팅 전송
  - `첨부한 DOCX를 PDF로 변환해줘` — LibreOffice 문서 변환
• **웹훅** — 외부 서비스(GitHub, CI/CD 등) 이벤트를 DM/채널로 수신 (`.env`에 `WEBHOOK_HOST` 필요)
  - `GitHub PR 알림 웹훅 등록해줘`
  - `웹훅 목록 보여줘`
  - `웹훅 삭제해줘`
• **캘린더** — iCloud 캘린더 일정 조회·추가·수정·삭제 (`.env`에 `CALDAV_URL` / `CALDAV_USERNAME` / `CALDAV_PASSWORD` 필요)
  - `이번 주 일정 보여줘`
  - `내일 오후 3시에 팀 미팅 추가해줘`
  - `팀 미팅 삭제해줘`
• **이메일 전송** — Gmail로 이메일 전송 (`.env`에 `GMAIL_USER` / `GMAIL_APP_PASSWORD` 필요)
  - `summary@example.com으로 오늘 AI 뉴스 요약 메일 보내줘`
• **Docker 로그 조회** — 실행 중인 컨테이너 로그 확인
  - `내 docker 로그 확인해줘`
  - `docker 컨테이너 목록 보여줘`
• **MCP 서버 연동** — `mcp_servers.json` 에 서버를 등록하면 외부 tool 자동 연결 (Notion, GitHub 등)
• **멀티 에이전트** — 복잡한 태스크를 전문 서브 에이전트에게 위임하거나 병렬 처리
  - `ChatGPT, Claude, Gemini 세 개를 각각 동시에 조사해서 비교해줘`
  - `뉴스 수집과 요약을 별도 에이전트로 나눠서 처리해줘`

**스케줄러**
• 자연어로 알림을 예약할 수 있습니다
  - `매일 오전 9시에 AI 뉴스 요약해줘`
  - `매주 월요일에 주간 회의 알림`
• 반복 주기: 매시간 / 매일 / 매주 / 매월
• **실행 지시** — 스케줄 등록 시 구체적인 절차를 함께 지정하면 에이전트가 실행 시 그대로 따릅니다
  - `매일 오전 9시에 출석체크 해줘. 지시: 출석 페이지 새로고침 후 5초 기다리고 오늘 날짜 버튼 클릭`
• `내 스케줄 보여줘` — 등록된 스케줄 조회 (지시 내용 포함)
• `[스케줄 이름] 삭제해줘` — 스케줄 삭제

**장기 기억**
• koclaw는 중요한 정보를 기억할 수 있습니다
  - `내 이름은 홍길동이야, 기억해줘` — DM에서 개인 기억 저장
  - `이 채널은 백엔드 개발팀 채널이야` — 채널 기억 저장
  - `이 스레드는 API 리뷰 논의야` — 스레드 기억 저장
  - `내 정보 지워줘` — 기억 삭제
• 범위: **개인(DM 전용)** / **채널** / **스레드**

**메시지 삭제**
• koclaw 메시지에 `❌` 이모지를 달면 해당 메시지가 삭제됩니다

**도움말**
• `help` 로 이 안내를 다시 볼 수 있습니다\
"""

AgentFn = Callable[..., Coroutine[Any, Any, str]]

_TOOL_ICONS: dict[str, str] = {
    "web_search": "🔍",
    "browse": "🌐",
    "youtube": "🎬",
    "computer_use": "🖥️",
    "browser": "🧭",
    "windows_shell": "💻",
    "memory": "🧠",
    "send_email": "📧",
    "scheduler": "📅",
    "file": "📄",
    "delegate": "🤖",
    "weather": "⛅",
    "calendar": "🗓️",
    "webhook": "🔔",
}


def _tool_status_text(tool_name: str, args: dict | None = None) -> str:
    icon = _TOOL_ICONS.get(tool_name, "🔧")
    if tool_name == "computer_use" and args:
        action = args.get("action", "")
        detail = {
            "screenshot": "스크린샷 찍는 중",
            "click": f"클릭 중 ({args.get('x')}, {args.get('y')})",
            "double_click": f"더블클릭 중 ({args.get('x')}, {args.get('y')})",
            "type": f"입력 중: {str(args.get('text', ''))[:20]}",
            "key": f"키 입력: {args.get('key_name', '')}",
            "scroll": f"{'아래로' if args.get('direction') == 'down' else '위로'} 스크롤 중",
            "open_url": f"URL 열기: {str(args.get('url', ''))[:40]}",
            "run_command": f"명령 실행: {str(args.get('command', ''))[:30]}",
            "list_windows": "창 목록 조회 중",
            "get_screen_size": "화면 크기 조회 중",
        }.get(action, f"{action} 실행 중")
        return f"{icon} {detail}..."
    if tool_name == "browser" and args:
        action = args.get("action", "")
        detail = {
            "navigate": f"URL 이동 중: {str(args.get('url', ''))[:40]}",
            "screenshot": "브라우저 스크린샷 찍는 중",
            "click": f"클릭 중: {str(args.get('selector', ''))[:30]}",
            "type": f"입력 중: {str(args.get('text', ''))[:20]}",
            "scroll": f"{'아래로' if args.get('direction') == 'down' else '위로'} 스크롤 중",
            "evaluate": "JavaScript 실행 중",
            "content": "페이지 내용 추출 중",
            "wait_for": f"요소 대기 중: {str(args.get('selector', ''))[:30]}",
            "select": f"선택 중: {str(args.get('selector', ''))[:30]}",
            "close": "브라우저 닫는 중",
        }.get(action, f"{action} 실행 중")
        return f"{icon} {detail}..."
    return f"{icon} `{tool_name}` 실행 중..."


_DISCORD_MAX_TEXT_LEN = 2000


def _split_text(text: str) -> list[str]:
    """2000자 초과 시 여러 청크로 분할"""
    if len(text) <= _DISCORD_MAX_TEXT_LEN:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:_DISCORD_MAX_TEXT_LEN])
        text = text[_DISCORD_MAX_TEXT_LEN:]
    return chunks


SESSION_ID_PREFIX = "discord:"


async def _discord_file_fetcher(url: str) -> bytes:
    """Discord 첨부파일 URL에서 바이트를 다운로드한다. 내부 네트워크 URL은 차단한다."""
    import httpx

    from koclaw.tools.browse import _is_safe_url

    if not _is_safe_url(url):
        raise ValueError("이 URL에서 파일을 다운로드할 수 없습니다 (허용되지 않는 URL)")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def parse_discord_message(message, bot_user_id: int) -> dict:
    text = message.content
    for user in message.mentions:
        text = text.replace(f"<@{user.id}>", "").replace(f"<@!{user.id}>", "")
    text = text.strip()

    files = [{"name": a.filename, "url": str(a.url)} for a in message.attachments]

    if message.guild is None:
        session_id = f"discord:dm:{message.author.id}"
    elif message.channel.__class__.__name__ == "Thread":
        session_id = f"discord:thread:{message.channel.parent_id}:{message.channel.id}"
    else:
        session_id = f"discord:{message.channel.id}"

    return {
        "session_id": session_id,
        "user_id": message.author.id,
        "text": text,
        "files": files,
    }


class DiscordChannel:
    def __init__(self, agent_fn: AgentFn, db=None, computer_use_manager=None):
        self._agent_fn = agent_fn
        self._db = db
        self._cu_manager = computer_use_manager

    @staticmethod
    def _is_help_request(text: str) -> bool:
        return text.strip().lower() in {"help", "/help", "도움말", "/도움말"}

    def should_handle(self, message, bot_user_id: int) -> bool:
        if message.author.id == bot_user_id:
            return False
        return True

    async def handle_reaction_added(self, payload, client, bot_user_id: int) -> None:
        logger.info(
            "[discord] reaction: emoji=%r channel=%s msg=%s",
            payload.emoji.name,
            payload.channel_id,
            payload.message_id,
        )
        if payload.emoji.name != "❌":
            return
        channel = client.get_channel(payload.channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(payload.channel_id)
            except Exception as e:
                logger.error("[discord] fetch_channel 실패: %s", e)
                return
        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception as e:
            logger.error("[discord] fetch_message 실패: %s", e)
            return
        logger.info("[discord] reaction target author=%s bot=%s", message.author.id, bot_user_id)
        if message.author.id != bot_user_id:
            return
        try:
            await message.delete()
            logger.info("[discord] 메시지 삭제 완료: %s", payload.message_id)
        except Exception as e:
            logger.error("[discord] message.delete 실패: %s", e)

    async def handle_message(self, message, bot_user_id: int) -> None:
        if not self.should_handle(message, bot_user_id):
            return

        parsed = parse_discord_message(message, bot_user_id)
        logger.info("[discord] user=%s text=%r", parsed["user_id"], parsed["text"])

        thinking = await message.channel.send("⏳ 생각 중...")

        if self._is_help_request(parsed["text"]):
            await thinking.edit(content=HELP_TEXT)
            return

        async def progress_callback(tool_name: str, args: dict | None = None) -> None:
            text = _tool_status_text(tool_name, args)
            if tool_name == "computer_use" and hasattr(self._cu_manager, "view_url"):
                text += f"\n🖥️ 화면 보기: {self._cu_manager.view_url()}"
            await thinking.edit(content=text)

        try:
            answer = await self._agent_fn(
                session_id=parsed["session_id"],
                user_message=parsed["text"],
                files=parsed["files"],
                user_id=parsed["user_id"],
                progress_callback=progress_callback,
            )
            logger.info("[discord] answer=%r", answer[:80])
        except Exception as e:
            logger.error("[discord] error: %s", e)
            answer = f"❌ 처리 중 오류가 발생했습니다: {e}"

        chunks = _split_text(answer)
        await thinking.edit(content=chunks[0])
        for chunk in chunks[1:]:
            await message.channel.send(chunk)
        await self._upload_screenshots(message.channel, parsed["session_id"])
        await self._upload_files(message.channel, parsed["session_id"])

    async def _upload_screenshots(self, channel, session_id: str) -> None:
        if self._cu_manager is None:
            return
        import io

        import discord

        stored = self._cu_manager.pop_screenshots(session_id)
        if not stored:
            return
        # 에이전트 완료 후 최종 상태를 새로 캡처 (마지막 액션 이후 화면 반영)
        try:
            await self._cu_manager.screenshot(session_id)
        except Exception:
            pass
        screenshots = self._cu_manager.pop_screenshots(session_id)
        if not screenshots:
            screenshots = stored
        try:
            img_bytes = screenshots[-1]
            is_jpeg = img_bytes[:3] == b"\xff\xd8\xff"
            filename = "screenshot.jpg" if is_jpeg else "screenshot.png"
            await channel.send(file=discord.File(io.BytesIO(img_bytes), filename=filename))
        except Exception as e:
            logger.error("[screenshot] Discord 업로드 실패: %s", e)

    async def _upload_files(self, channel, session_id: str) -> None:
        if self._cu_manager is None:
            return
        import io

        import discord

        files = self._cu_manager.pop_files(session_id)
        for filename, data in files:
            try:
                await channel.send(file=discord.File(io.BytesIO(data), filename=filename))
            except Exception as e:
                logger.error("[file_upload] Discord 업로드 실패: %s", e)


async def start(
    env: dict,
    provider,
    tools,
    db,
    *,
    workspace: Path | None = None,
    notify_registry: dict | None = None,
    agent_registry: dict | None = None,
    computer_use_manager=None,
) -> None:
    try:
        import discord
    except ImportError:
        raise ImportError(
            "Discord 채널을 사용하려면 discord.py를 설치하세요: pip install 'koclaw[discord]'"
        )

    from koclaw.app import _DISCORD_FORMAT_INSTRUCTIONS, create_agent_fn
    from koclaw.channels import parse_parent_session_id
    from koclaw.core.memory_context import parse_memory_context
    from koclaw.tools.file import FileTool
    from koclaw.tools.memory import MemoryTool
    from koclaw.tools.scheduler import SchedulerTool

    session_tool_factories = [
        lambda sid, uid: SchedulerTool(db=db, session_id=sid),
        lambda sid, uid: MemoryTool(
            db=db,
            memory_context=parse_memory_context(sid, str(uid) if uid is not None else None),
        ),
    ]
    if workspace is not None:
        session_tool_factories.append(
            lambda sid, uid: FileTool(
                workspace=workspace,
                session_id=sid,
                parent_session_id=parse_parent_session_id(sid),
            )
        )

    agent_fn = create_agent_fn(
        provider=provider,
        tools=tools,
        db=db,
        file_fetcher=_discord_file_fetcher,
        session_tool_factories=session_tool_factories,
        workspace=workspace,
        response_formatter=lambda x: x,
        format_instructions=_DISCORD_FORMAT_INSTRUCTIONS,
    )

    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    client = discord.Client(intents=intents)

    async def notify_fn(session_id: str, message: str) -> None:
        parts = session_id.split(":")
        # "discord:dm:USER_ID" 또는 "discord:CHANNEL_ID"
        if len(parts) >= 3 and parts[1] == "dm":
            user = await client.fetch_user(int(parts[2]))
            dm = await user.create_dm()
            await dm.send(message)
        elif len(parts) >= 2:
            channel = client.get_channel(int(parts[-1]))
            if channel:
                await channel.send(message)

    if notify_registry is not None:
        notify_registry[SESSION_ID_PREFIX] = notify_fn
    if agent_registry is not None:
        agent_registry[SESSION_ID_PREFIX] = agent_fn

    channel_handler = DiscordChannel(
        agent_fn=agent_fn, db=db, computer_use_manager=computer_use_manager
    )

    @client.event
    async def on_ready():
        logger.info("Discord 채널 시작: %s", client.user)

    @client.event
    async def on_message(message):
        await channel_handler.handle_message(message, bot_user_id=client.user.id)

    @client.event
    async def on_raw_reaction_add(payload):
        await channel_handler.handle_reaction_added(
            payload, client=client, bot_user_id=client.user.id
        )

    await client.start(env["DISCORD_BOT_TOKEN"])
