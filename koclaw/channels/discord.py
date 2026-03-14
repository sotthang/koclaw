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
• **YouTube 요약** — 동영상 링크를 보내면 내용을 요약
• **파일 분석** — PDF, DOCX, HWPX, 이미지 첨부 시 자동 분석
• **가상 데스크탑 제어** — 브라우저 열기, 클릭, 입력, 스크린샷 등 GUI 자동화 (Docker 필요)
  - `네이버에서 AI 뉴스 검색해서 스크린샷 찍어줘`
  - `https://example.com 열고 로그인 버튼 눌러줘`
  - `이 CSV 파일로 matplotlib 차트 그려서 파일로 줘` — 컨테이너 파일 채팅 전송
  - `첨부한 DOCX를 PDF로 변환해줘` — LibreOffice 문서 변환
• **이메일 전송** — Gmail로 이메일 전송 (`.env`에 `GMAIL_USER` / `GMAIL_APP_PASSWORD` 필요)
  - `summary@example.com으로 오늘 AI 뉴스 요약 메일 보내줘`

**스케줄러**
• 자연어로 알림을 예약할 수 있습니다
  - `매일 오전 9시에 AI 뉴스 요약해줘`
  - `매주 월요일에 주간 회의 알림`
• `내 스케줄 보여줘` — 등록된 스케줄 조회
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
    "memory": "🧠",
    "send_email": "📧",
    "scheduler": "📅",
    "file": "📄",
}


def _tool_status_text(tool_name: str) -> str:
    icon = _TOOL_ICONS.get(tool_name, "🔧")
    return f"{icon} `{tool_name}` 실행 중..."


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

        async def progress_callback(tool_name: str) -> None:
            await thinking.edit(content=_tool_status_text(tool_name))

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

        await thinking.edit(content=answer)
        await self._upload_screenshots(message.channel, parsed["session_id"])
        await self._upload_files(message.channel, parsed["session_id"])

    async def _upload_screenshots(self, channel, session_id: str) -> None:
        if self._cu_manager is None:
            return
        import io

        import discord

        screenshots = self._cu_manager.pop_screenshots(session_id)
        for i, png_bytes in enumerate(screenshots, start=1):
            try:
                await channel.send(
                    file=discord.File(io.BytesIO(png_bytes), filename=f"screenshot_{i}.png")
                )
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
