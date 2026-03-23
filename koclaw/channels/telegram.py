import asyncio
import logging
import re
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HELP_TEXT = """\
<b>koclaw 사용 가이드</b>

<b>기본 대화</b>
• DM 또는 그룹에서 채팅할 수 있습니다
• 그룹에서는 @멘션하거나 봇의 메시지에 답장하면 됩니다

<b>주요 기능</b>
• <b>웹 검색</b> — 최신 정보, 뉴스, 기술 트렌드 등 검색
• <b>웹페이지 읽기</b> — URL을 주면 페이지 전체 내용을 분석
• <b>RSS 피드</b> — 뉴스·블로그·GitHub 릴리즈 등 RSS 피드 구독
  - <code>해커뉴스 최신 글 5개 요약해줘</code>
  - <code>https://example.com/feed.xml 읽어줘</code>
• <b>날씨 조회</b> — 전 세계 도시의 현재 날씨와 최저·최고 기온
  - <code>서울 날씨 알려줘</code>
• <b>YouTube 요약</b> — 동영상 링크를 보내면 내용을 요약
• <b>파일 분석</b> — PDF, DOCX, HWPX, 이미지 첨부 시 자동 분석
• <b>Windows PowerShell 실행</b> — Windows PC에서 PowerShell 명령 실행 (Windows Agent 필요)
  - <code>C 드라이브 용량 얼마나 남았어?</code>
  - <code>실행 중인 프로세스 상위 10개 보여줘</code>
• <b>브라우저 자동화</b> — Playwright DOM 기반 웹 제어 (Windows Agent 필요)
• <b>가상 데스크탑 제어</b> — 브라우저 열기, 클릭, 입력, 스크린샷 등 GUI 자동화 (Docker 필요)
• <b>웹훅</b> — 외부 서비스(GitHub, CI/CD 등) 이벤트를 DM/채널로 수신
• <b>캘린더</b> — iCloud 캘린더 일정 조회·추가·수정·삭제
• <b>이메일 전송</b> — Gmail로 이메일 전송
• <b>Docker 로그 조회</b> — 실행 중인 컨테이너 로그 확인
• <b>MCP 서버 연동</b> — 외부 tool 자동 연결 (Notion, GitHub 등)
• <b>멀티 에이전트</b> — 복잡한 태스크를 전문 서브 에이전트에게 위임하거나 병렬 처리

<b>스케줄러</b>
• 자연어로 알림을 예약할 수 있습니다
  - <code>매일 오전 9시에 AI 뉴스 요약해줘</code>
  - <code>매주 월요일에 주간 회의 알림</code>
• <code>내 스케줄 보여줘</code> — 등록된 스케줄 조회
• <code>[스케줄 이름] 삭제해줘</code> — 스케줄 삭제

<b>장기 기억</b>
• koclaw는 중요한 정보를 기억할 수 있습니다
  - <code>내 이름은 홍길동이야, 기억해줘</code> — DM에서 개인 기억 저장
  - <code>이 채팅은 백엔드 개발팀이야</code> — 그룹 기억 저장
  - <code>내 정보 지워줘</code> — 기억 삭제
• 범위: <b>개인(DM 전용)</b> / <b>그룹</b>

<b>도움말</b>
• <code>help</code> 로 이 안내를 다시 볼 수 있습니다\
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
    return f"{icon} {tool_name} 실행 중..."


_TELEGRAM_MAX_TEXT_LEN = 4096


def _split_text(text: str) -> list[str]:
    """4096자 초과 시 여러 청크로 분할"""
    if len(text) <= _TELEGRAM_MAX_TEXT_LEN:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:_TELEGRAM_MAX_TEXT_LEN])
        text = text[_TELEGRAM_MAX_TEXT_LEN:]
    return chunks


SESSION_ID_PREFIX = "telegram:"


def parse_telegram_update(update, bot_username: str) -> dict | None:
    """Telegram Update 객체에서 session_id, user_id, text, files를 추출한다."""
    message = update.effective_message
    if message is None:
        return None

    text = message.text or message.caption or ""
    # @봇이름 멘션 제거
    if bot_username:
        text = re.sub(rf"@{re.escape(bot_username)}\b", "", text).strip()

    # 파일 목록 구성 (tg-file:// 스킴으로 file_id 전달)
    files: list[dict] = []
    if message.document:
        files.append(
            {
                "name": message.document.file_name or "file",
                "url": f"tg-file://{message.document.file_id}",
            }
        )
    if message.photo:
        largest = max(message.photo, key=lambda p: p.file_size or 0)
        files.append({"name": "photo.jpg", "url": f"tg-file://{largest.file_id}"})

    # 세션 ID 결정
    chat = message.chat
    if chat.type == "private":
        session_id = f"telegram:dm:{chat.id}"
    elif message.message_thread_id:
        session_id = f"telegram:topic:{chat.id}:{message.message_thread_id}"
    else:
        session_id = f"telegram:{chat.id}"

    user = message.from_user
    return {
        "session_id": session_id,
        "user_id": user.id if user else None,
        "text": text,
        "files": files,
        "chat_id": chat.id,
        "chat_type": chat.type,
        "message_thread_id": message.message_thread_id,
    }


class TelegramChannel:
    def __init__(self, agent_fn: AgentFn, db=None, computer_use_manager=None):
        self._agent_fn = agent_fn
        self._db = db
        self._cu_manager = computer_use_manager

    @staticmethod
    def _is_help_request(text: str) -> bool:
        return text.strip().lower() in {"help", "/help", "도움말", "/도움말"}

    def should_handle(self, update, bot_user_id: int, bot_username: str) -> bool:
        """메시지를 처리할지 결정한다.

        - 봇 자신의 메시지는 무시
        - Private 채팅: 항상 처리
        - 그룹/슈퍼그룹: @멘션 또는 봇 메시지에 대한 답장만 처리
        """
        message = update.effective_message
        if message is None:
            return False

        user = message.from_user
        if user and user.id == bot_user_id:
            return False

        chat = message.chat
        if chat.type == "private":
            return True

        # 그룹: @멘션 확인
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    text = message.text or ""
                    mention = text[entity.offset : entity.offset + entity.length]
                    if mention.lstrip("@").lower() == bot_username.lower():
                        return True

        # 그룹: 봇 메시지에 대한 답장 확인
        if message.reply_to_message and message.reply_to_message.from_user:
            if message.reply_to_message.from_user.id == bot_user_id:
                return True

        return False

    async def handle_message(self, update, context) -> None:
        bot = context.bot
        if not self.should_handle(update, bot.id, bot.username):
            return

        parsed = parse_telegram_update(update, bot.username)
        if parsed is None:
            return

        logger.info("[telegram] user=%s text=%r", parsed["user_id"], parsed["text"])

        chat_id = parsed["chat_id"]
        thread_id = parsed["message_thread_id"]

        thinking = await bot.send_message(
            chat_id=chat_id,
            text="⏳ 생각 중...",
            message_thread_id=thread_id,
        )

        if self._is_help_request(parsed["text"]):
            await thinking.edit_text(HELP_TEXT, parse_mode="HTML")
            return

        async def progress_callback(tool_name: str, args: dict | None = None) -> None:
            status = _tool_status_text(tool_name, args)
            if tool_name == "computer_use" and hasattr(self._cu_manager, "view_url"):
                status += f"\n🖥️ 화면 보기: {self._cu_manager.view_url()}"
            try:
                await thinking.edit_text(status)
            except Exception:
                pass

        try:
            answer = await self._agent_fn(
                session_id=parsed["session_id"],
                user_message=parsed["text"],
                files=parsed["files"],
                user_id=str(parsed["user_id"]) if parsed["user_id"] else None,
                progress_callback=progress_callback,
            )
            logger.info("[telegram] answer=%r", answer[:80])
        except Exception as e:
            logger.error("[telegram] error: %s", e)
            answer = f"❌ 처리 중 오류가 발생했습니다: {e}"

        chunks = _split_text(answer)
        await self._send_or_edit(thinking, bot, chat_id, thread_id, chunks[0])
        for chunk in chunks[1:]:
            await self._safe_send(bot, chat_id, thread_id, chunk)
        await self._upload_screenshots(bot, chat_id, thread_id, parsed["session_id"])
        await self._upload_files(bot, chat_id, thread_id, parsed["session_id"])

    async def _send_or_edit(self, thinking, bot, chat_id, thread_id, text: str) -> None:
        """thinking 메시지를 HTML로 수정하고, 실패하면 평문으로 재시도한다."""
        try:
            await thinking.edit_text(text, parse_mode="HTML")
        except Exception:
            try:
                await thinking.edit_text(text)
            except Exception as e:
                logger.error("[telegram] edit_text 실패: %s", e)

    async def _safe_send(self, bot, chat_id, thread_id, text: str) -> None:
        """HTML parse_mode로 전송하고, 실패하면 평문으로 재시도한다."""
        try:
            await bot.send_message(
                chat_id=chat_id, text=text, parse_mode="HTML", message_thread_id=thread_id
            )
        except Exception:
            try:
                await bot.send_message(chat_id=chat_id, text=text, message_thread_id=thread_id)
            except Exception as e:
                logger.error("[telegram] send_message 실패: %s", e)

    async def _upload_screenshots(
        self, bot, chat_id: int, thread_id: int | None, session_id: str
    ) -> None:
        if self._cu_manager is None:
            return
        stored = self._cu_manager.pop_screenshots(session_id)
        if not stored:
            return
        try:
            await self._cu_manager.screenshot(session_id)
        except Exception:
            pass
        screenshots = self._cu_manager.pop_screenshots(session_id)
        if not screenshots:
            screenshots = stored
        try:
            img_bytes = screenshots[-1]
            await bot.send_photo(
                chat_id=chat_id,
                photo=img_bytes,
                message_thread_id=thread_id,
            )
        except Exception as e:
            logger.error("[screenshot] Telegram 업로드 실패: %s", e)

    async def _upload_files(
        self, bot, chat_id: int, thread_id: int | None, session_id: str
    ) -> None:
        if self._cu_manager is None:
            return
        import io

        files = self._cu_manager.pop_files(session_id)
        for filename, data in files:
            try:
                await bot.send_document(
                    chat_id=chat_id,
                    document=io.BytesIO(data),
                    filename=filename,
                    message_thread_id=thread_id,
                )
            except Exception as e:
                logger.error("[file_upload] Telegram 업로드 실패: %s", e)


async def _telegram_file_fetcher(url: str, bot) -> bytes:
    """Telegram 파일 또는 일반 HTTP URL에서 바이트를 다운로드한다."""
    if url.startswith("tg-file://"):
        file_id = url[len("tg-file://") :]
        tg_file = await bot.get_file(file_id)
        return bytes(await tg_file.download_as_bytearray())

    import httpx

    from koclaw.tools.browse import _is_safe_url

    if not _is_safe_url(url):
        raise ValueError("이 URL에서 파일을 다운로드할 수 없습니다 (허용되지 않는 URL)")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


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
        from telegram.ext import Application, MessageHandler, filters
        from telegram.request import HTTPXRequest
    except ImportError:
        raise ImportError(
            "Telegram 채널을 사용하려면 python-telegram-bot을 설치하세요: "
            "pip install 'koclaw[telegram]'"
        )

    from koclaw.app import _TELEGRAM_FORMAT_INSTRUCTIONS, create_agent_fn
    from koclaw.channels import parse_parent_session_id
    from koclaw.core.memory_context import parse_memory_context
    from koclaw.tools.file import FileTool
    from koclaw.tools.memory import MemoryTool
    from koclaw.tools.scheduler import SchedulerTool

    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0, write_timeout=30.0)
    app = Application.builder().token(env["TELEGRAM_BOT_TOKEN"]).request(request).build()

    async def file_fetcher(url: str) -> bytes:
        return await _telegram_file_fetcher(url, app.bot)

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
        file_fetcher=file_fetcher,
        session_tool_factories=session_tool_factories,
        workspace=workspace,
        response_formatter=lambda x: x,
        format_instructions=_TELEGRAM_FORMAT_INSTRUCTIONS,
    )

    async def notify_fn(session_id: str, message: str) -> None:
        parts = session_id.split(":")
        # "telegram:dm:CHAT_ID", "telegram:CHAT_ID", "telegram:topic:CHAT_ID:THREAD_ID"
        try:
            if len(parts) >= 3 and parts[1] == "dm":
                await app.bot.send_message(chat_id=int(parts[2]), text=message)
            elif len(parts) >= 4 and parts[1] == "topic":
                await app.bot.send_message(
                    chat_id=int(parts[2]),
                    text=message,
                    message_thread_id=int(parts[3]),
                )
            elif len(parts) >= 2:
                await app.bot.send_message(chat_id=int(parts[1]), text=message)
        except Exception as e:
            logger.error("[telegram] notify 실패: %s", e)

    if notify_registry is not None:
        notify_registry[SESSION_ID_PREFIX] = notify_fn
    if agent_registry is not None:
        agent_registry[SESSION_ID_PREFIX] = agent_fn

    channel_handler = TelegramChannel(
        agent_fn=agent_fn, db=db, computer_use_manager=computer_use_manager
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.Document.ALL | filters.PHOTO | filters.CAPTION,
            channel_handler.handle_message,
        )
    )

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram 채널 시작: @%s", app.bot.username)
        try:
            await asyncio.Event().wait()
        finally:
            await app.updater.stop()
            await app.stop()
