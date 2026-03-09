import logging
import re
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HELP_TEXT = """\
*koclaw 사용 가이드*

*기본 대화*
• DM 또는 채널에서 바로 메시지를 보내거나 @멘션으로 채팅할 수 있습니다

*주요 기능*
• *웹 검색* — 최신 정보, 뉴스, 기술 트렌드 등 검색
• *웹페이지 읽기* — URL을 주면 페이지 전체 내용을 분석
• *RSS 피드* — 뉴스·블로그·GitHub 릴리즈 등 RSS 피드 구독
  - `해커뉴스 최신 글 5개 요약해줘`
  - `https://example.com/feed.xml 읽어줘`
• *YouTube 요약* — 동영상 링크를 보내면 내용을 요약
• *파일 분석* — PDF, DOCX, HWPX, 이미지 첨부 시 자동 분석
• *코드 실행* — Python 코드를 안전한 샌드박스에서 실행하고 결과 반환
  - `파이썬으로 피보나치 수열 출력해줘`

*스케줄러*
• 자연어로 알림을 예약할 수 있습니다
  - `매일 오전 9시에 AI 뉴스 요약해줘`
  - `매주 월요일에 주간 회의 알림`
• 반복 주기: 매시간 / 매일 / 매주 / 매월
• `내 스케줄 보여줘` — 등록된 스케줄 조회
• `[스케줄 이름] 삭제해줘` — 스케줄 삭제

*장기 기억*
• koclaw는 중요한 정보를 기억할 수 있습니다
  - `내 이름은 홍길동이야, 기억해줘` — DM에서 개인 기억 저장
  - `이 채널은 백엔드 개발팀 채널이야` — 채널 기억 저장
  - `이 스레드는 API 리뷰 논의야` — 스레드 기억 저장
  - `내 정보 지워줘` — 기억 삭제
• 범위: *개인(DM 전용)* / *채널* / *스레드*

*메시지 삭제*
• koclaw 메시지에 `:x:` 이모지를 달면 해당 메시지가 삭제됩니다

*도움말*
• `help` 로 이 안내를 다시 볼 수 있습니다\
"""


def parse_slack_event(event: dict, bot_user_id: str) -> dict:
    text = re.sub(rf"<@{bot_user_id}>", "", event.get("text", "")).strip()
    files = [
        {"id": f["id"], "name": f["name"], "url": f["url_private"]}
        for f in event.get("files", [])
    ]
    thread_ts = event.get("thread_ts")
    channel = event["channel"]
    user = event["user"]
    if channel.startswith("D") or channel.startswith("G"):
        session_id = f"slack:dm:{user}"
    elif thread_ts:
        session_id = f"slack:{channel}:{thread_ts}"
    else:
        session_id = f"slack:{channel}"
    return {
        "session_id": session_id,
        "user_id": event["user"],
        "text": text,
        "files": files,
        "thread_ts": thread_ts,
    }


AgentFn = Callable[..., Coroutine[Any, Any, str]]

_TOOL_ICONS: dict[str, str] = {
    "web_search": "🔍",
    "browse": "🌐",
    "youtube": "🎬",
    "code": "💻",
    "memory": "🧠",
    "scheduler": "📅",
    "file": "📄",
}


def _tool_status_text(tool_name: str) -> str:
    icon = _TOOL_ICONS.get(tool_name, "🔧")
    return f"{icon} `{tool_name}` 실행 중..."


class SlackChannel:
    def __init__(self, app, agent_fn: AgentFn, db=None):
        self._app = app
        self._agent_fn = agent_fn
        self._db = db

    @staticmethod
    def _is_help_request(text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in {"help", "/help", "도움말", "/도움말"}

    async def handle_mention(
        self, event: dict, say, client, bot_user_id: str
    ) -> None:
        parsed = parse_slack_event(event, bot_user_id)
        logger.info("[mention] user=%s text=%r", parsed["user_id"], parsed["text"])

        say_kwargs = {"thread_ts": parsed["thread_ts"]} if parsed["thread_ts"] else {}
        response = await say("⏳ 생각 중...", **say_kwargs)
        ts = response["ts"]
        channel = event["channel"]

        if self._is_help_request(parsed["text"]):
            await client.chat_update(channel=channel, ts=ts, text=HELP_TEXT)
            return

        async def progress_callback(tool_name: str) -> None:
            await client.chat_update(channel=channel, ts=ts, text=_tool_status_text(tool_name))

        try:
            answer = await self._agent_fn(
                session_id=parsed["session_id"],
                user_message=parsed["text"],
                files=parsed["files"],
                user_id=parsed["user_id"],
                progress_callback=progress_callback,
            )
            logger.info("[mention] answer=%r", answer[:80])
        except Exception as e:
            logger.error("[mention] error: %s", e)
            answer = f"❌ 처리 중 오류가 발생했습니다: {e}"

        await client.chat_update(channel=channel, ts=ts, text=answer)

    _IGNORED_SUBTYPES = {"message_changed", "message_deleted", "bot_message"}

    def should_handle_message(self, event: dict, bot_user_id: str) -> bool:
        if event.get("subtype") in self._IGNORED_SUBTYPES:
            return False
        if "bot_id" in event:
            return False
        if f"<@{bot_user_id}>" in event.get("text", ""):
            return False
        return True

    async def handle_dm(self, event: dict, say, client) -> None:
        text = event.get("text", "").strip()
        files = [
            {"id": f["id"], "name": f["name"], "url": f["url_private"]}
            for f in event.get("files", [])
        ]
        channel_id = event["channel"]
        thread_ts = event.get("thread_ts")
        session_id = f"slack:{channel_id}:{thread_ts}" if thread_ts else f"slack:{channel_id}"
        logger.info("[dm] user=%s text=%r", event.get("user"), text)

        say_kwargs = {"thread_ts": thread_ts} if thread_ts else {}
        response = await say("⏳ 생각 중...", **say_kwargs)
        ts = response["ts"]

        if self._is_help_request(text):
            await client.chat_update(channel=channel_id, ts=ts, text=HELP_TEXT)
            return

        user_id = event.get("user")

        async def progress_callback(tool_name: str) -> None:
            await client.chat_update(channel=channel_id, ts=ts, text=_tool_status_text(tool_name))

        try:
            answer = await self._agent_fn(
                session_id=session_id,
                user_message=text,
                files=files,
                user_id=user_id,
                progress_callback=progress_callback,
            )
            logger.info("[dm] answer=%r", answer[:80])
        except Exception as e:
            logger.error("[dm] error: %s", e)
            answer = f"❌ 처리 중 오류가 발생했습니다: {e}"

        await client.chat_update(channel=channel_id, ts=ts, text=answer)

        if self._db:
            msg_id = await self._db.get_last_message_id(session_id)
            if msg_id:
                await self._db.update_message_slack_ts(msg_id, ts)

    async def handle_reaction_added(
        self, event: dict, client, bot_user_id: str
    ) -> None:
        if event.get("reaction") != "x":
            return
        item = event.get("item", {})
        if item.get("type") != "message":
            return
        if event.get("item_user") != bot_user_id:
            return

        channel = item["channel"]
        ts = item["ts"]

        try:
            await client.chat_delete(channel=channel, ts=ts)
        except Exception as e:
            logger.error("[reaction] chat_delete 실패: %s", e)

        if self._db:
            await self._db.delete_message_pair_by_slack_ts(ts)


SESSION_ID_PREFIX = "slack:"


async def start(
    env: dict,
    provider,
    tools,
    db,
    *,
    sandbox=None,
    workspace: Path | None = None,
    notify_registry: dict | None = None,
    agent_registry: dict | None = None,
) -> None:
    import httpx
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
    from slack_bolt.async_app import AsyncApp

    from koclaw.app import create_agent_fn
    from koclaw.channels import parse_parent_session_id
    from koclaw.core.memory_context import parse_memory_context
    from koclaw.tools.file import FileTool
    from koclaw.tools.memory import MemoryTool
    from koclaw.tools.scheduler import SchedulerTool

    slack_bot_token = env["SLACK_BOT_TOKEN"]
    app = AsyncApp(token=slack_bot_token)

    async def file_fetcher(url: str) -> bytes:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {slack_bot_token}"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.content
            if content[:9].lower().startswith(b"<!doctype") or content[:5] == b"<html":
                raise PermissionError(
                    "파일 다운로드 권한이 없습니다. "
                    "Slack 앱 설정(OAuth & Permissions)에서 "
                    "Bot Token Scopes에 `files:read`를 추가하고 재설치하세요."
                )
            return content

    session_tool_factories = [
        lambda sid, uid: SchedulerTool(db=db, session_id=sid),
        lambda sid, uid: MemoryTool(db=db, memory_context=parse_memory_context(sid, uid)),
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
        file_fetcher=file_fetcher,
        session_tool_factories=session_tool_factories,
        sandbox=sandbox,
        workspace=workspace,
    )

    async def notify_fn(session_id: str, message: str) -> None:
        # "slack:C001" or "slack:C001:9999.0000" → channel_id = "C001"
        channel_id = session_id.removeprefix("slack:").split(":")[0]
        await app.client.chat_postMessage(channel=channel_id, text=message)

    if notify_registry is not None:
        notify_registry[SESSION_ID_PREFIX] = notify_fn
    if agent_registry is not None:
        agent_registry[SESSION_ID_PREFIX] = agent_fn

    channel = SlackChannel(app=app, agent_fn=agent_fn, db=db)
    bot_user_id = (await app.client.auth_test())["user_id"]

    @app.event("app_mention")
    async def handle_mention(event, say, client):
        await channel.handle_mention(event=event, say=say, client=client, bot_user_id=bot_user_id)

    @app.event("message")
    async def handle_message(event, say, client):
        if channel.should_handle_message(event, bot_user_id=bot_user_id):
            await channel.handle_dm(event=event, say=say, client=client)

    @app.event("reaction_added")
    async def handle_reaction_added(event, client):
        await channel.handle_reaction_added(event=event, client=client, bot_user_id=bot_user_id)

    @app.event("app_home_opened")
    async def handle_app_home_opened():
        pass

    logger.info("Slack 채널 시작")
    handler = AsyncSocketModeHandler(app, env["SLACK_APP_TOKEN"])
    await handler.start_async()
