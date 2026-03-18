import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from aiohttp import web

from koclaw.core.prompt_guard import wrap_external_content
from koclaw.storage.db import Database

logger = logging.getLogger(__name__)

NotifyFn = Callable[..., Coroutine[Any, Any, None]]


class WebhookServer:
    def __init__(self, db: Database, notify_fn: NotifyFn, port: int = 8080):
        self._db = db
        self._notify_fn = notify_fn
        self._port = port
        self._runner: web.AppRunner | None = None

    async def _handle(self, request: web.Request) -> web.Response:
        token = request.match_info["token"]
        webhook = await self._db.get_webhook_by_token(token)
        if not webhook:
            return web.Response(status=404, text="Not found")

        try:
            payload = await request.json()
        except Exception:
            payload = await request.text()

        headers = dict(request.headers)
        message = _format_message(webhook["description"], payload, headers)

        try:
            await self._notify_fn(session_id=webhook["session_id"], message=message)
        except Exception:
            logger.exception("웹훅 알림 전송 실패: token=%s", token)
            return web.Response(status=500, text="Internal error")

        return web.Response(text="OK")

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/webhook/{token}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("🌐 웹훅 서버 시작: 포트 %d", self._port)
        while True:
            await asyncio.sleep(3600)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()


# ── 헬퍼 함수 ──────────────────────────────────────────────────────────────


def _format_message(description: str, payload: Any, headers: dict) -> str:
    """수신된 웹훅 페이로드를 알림 메시지로 변환"""
    lines = [f"🔔 웹훅 수신: *{description}*"]

    # GitHub 이벤트 헤더 감지
    gh_event = headers.get("X-GitHub-Event", "")
    if gh_event:
        lines.append(f"GitHub 이벤트: `{gh_event}`")

    if isinstance(payload, dict):
        content = _dict_to_readable(payload)
    elif isinstance(payload, str):
        content = payload[:2000]
    else:
        content = str(payload)[:2000]

    if content:
        lines.append(wrap_external_content("webhook", content))

    return "\n".join(lines)


def _dict_to_readable(d: dict, depth: int = 0) -> str:
    """딕셔너리를 읽기 좋은 텍스트로 변환 (최대 깊이 2, 2000자 제한)"""
    lines = []
    for key, value in list(d.items())[:20]:
        indent = "  " * depth
        if isinstance(value, dict) and depth < 1:
            lines.append(f"{indent}{key}:")
            lines.append(_dict_to_readable(value, depth + 1))
        elif isinstance(value, list):
            lines.append(f"{indent}{key}: [{len(value)}개 항목]")
        elif value is None:
            pass
        else:
            lines.append(f"{indent}{key}: {str(value)[:200]}")
    return "\n".join(lines)[:2000]
