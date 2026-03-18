import os
import secrets

from koclaw.core.tool import Tool
from koclaw.storage.db import Database


class WebhookTool(Tool):
    name = "webhook"
    description = (
        "웹훅을 등록, 조회, 삭제합니다. "
        "외부 서비스(GitHub, CI/CD, 모니터링 등)가 이벤트 발생 시 koclaw로 알림을 보낼 수 있습니다. "
        ".env에 WEBHOOK_HOST 설정이 필요합니다."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["register", "list", "delete"],
                "description": "register: 웹훅 등록, list: 목록 조회, delete: 삭제",
            },
            "description": {
                "type": "string",
                "description": "웹훅 설명 (register 시 필수, 예: 'GitHub PR 알림')",
            },
            "token": {
                "type": "string",
                "description": "삭제할 웹훅 토큰 (delete 시 필수, list로 확인 가능)",
            },
        },
        "required": ["action"],
    }
    is_sandboxed = False
    needs_session_context = True

    def __init__(self, db: Database):
        self._db = db

    def _host(self) -> str:
        return os.getenv("WEBHOOK_HOST", "").rstrip("/")

    async def execute(
        self,
        action: str,
        description: str = "",
        token: str = "",
        _session_id: str = "",
    ) -> str:
        if not self._host():
            return (
                "오류: WEBHOOK_HOST가 설정되지 않았습니다. "
                ".env에 WEBHOOK_HOST를 설정하세요.\n"
                "예: WEBHOOK_HOST=https://your-host.ts.net"
            )

        if action == "register":
            return await self._register(_session_id, description)
        if action == "list":
            return await self._list(_session_id)
        if action == "delete":
            return await self._delete(_session_id, token)
        return f"알 수 없는 action: {action}"

    async def _register(self, session_id: str, description: str) -> str:
        if not description:
            return "오류: 웹훅 설명(description)을 지정해주세요. 예: 'GitHub PR 알림'"
        new_token = secrets.token_urlsafe(24)
        await self._db.save_webhook(session_id, new_token, description)
        url = f"{self._host()}/webhook/{new_token}"
        return (
            f"✅ 웹훅이 등록되었습니다.\n"
            f"• 설명: {description}\n"
            f"• URL: {url}\n"
            f"• 토큰: {new_token}\n"
            f"이 URL을 외부 서비스의 웹훅 주소로 등록하세요. POST 요청을 지원합니다."
        )

    async def _list(self, session_id: str) -> str:
        webhooks = await self._db.get_webhooks(session_id)
        if not webhooks:
            return "등록된 웹훅이 없습니다."
        lines = ["🔔 등록된 웹훅 목록:"]
        for w in webhooks:
            url = f"{self._host()}/webhook/{w['token']}"
            lines.append(f"• {w['description']}\n  URL: {url}\n  토큰: {w['token']}")
        return "\n".join(lines)

    async def _delete(self, session_id: str, token: str) -> str:
        if not token:
            return "오류: 삭제할 웹훅 토큰(token)을 지정해주세요. `webhook list`로 확인하세요."
        deleted = await self._db.delete_webhook(session_id, token)
        if not deleted:
            return "해당 웹훅을 찾을 수 없습니다."
        return "✅ 웹훅이 삭제되었습니다."
