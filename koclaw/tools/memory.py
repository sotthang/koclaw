from koclaw.core.memory_context import MemoryContext
from koclaw.core.tool import Tool


class MemoryTool(Tool):
    name = "memory"
    description = (
        "기억을 읽거나 저장/삭제합니다. "
        "scope: user(개인, DM 전용) / channel(채널 공유) / thread(스레드 전용). "
        "read는 현재 컨텍스트의 모든 기억을 반환합니다."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "delete"],
                "description": "read: 모든 기억 읽기, write: 기억 저장, delete: 기억 삭제",
            },
            "scope": {
                "type": "string",
                "enum": ["user", "channel", "thread"],
                "description": "write/delete 시 필수. user는 DM에서만, channel은 채널/스레드에서, thread는 스레드에서만 사용 가능",
            },
            "content": {
                "type": "string",
                "description": "저장할 내용 (write 시 필수)",
            },
        },
        "required": ["action"],
    }
    is_sandboxed = False

    def __init__(self, db, memory_context: MemoryContext):
        self._db = db
        self._ctx = memory_context

    async def execute(self, action: str, scope: str | None = None, content: str = "") -> str:
        if action == "read":
            return await self._read_all()

        if action == "write":
            if not scope:
                return "오류: scope를 지정해주세요 (user/channel/thread)"
            scope_id = self._get_scope_id(scope)
            if scope_id is None:
                return f"오류: 현재 컨텍스트에서 '{scope}' 범위를 사용할 수 없습니다"
            await self._db.save_memory(scope, scope_id, content)
            return "✅ 기억이 저장되었습니다."

        if action == "delete":
            if not scope:
                return "오류: scope를 지정해주세요 (user/channel/thread)"
            scope_id = self._get_scope_id(scope)
            if scope_id is None:
                return f"오류: 현재 컨텍스트에서 '{scope}' 범위를 사용할 수 없습니다"
            deleted = await self._db.delete_memory(scope, scope_id)
            return "✅ 기억이 삭제되었습니다." if deleted else "삭제할 기억이 없습니다."

        return f"알 수 없는 action: {action}"

    def _get_scope_id(self, scope: str) -> str | None:
        if scope == "user":
            return self._ctx.user_scope
        if scope == "channel":
            return self._ctx.channel_scope
        if scope == "thread":
            return self._ctx.thread_scope
        return None

    async def _read_all(self) -> str:
        parts = []
        for scope_type, scope_id in self._ctx.applicable_scopes():
            label = {"user": "개인 기억", "channel": "채널 기억", "thread": "스레드 기억"}.get(scope_type, scope_type)
            mem = await self._db.get_memory(scope_type, scope_id)
            if mem:
                parts.append(f"[{label}]\n{mem}")
        if not parts:
            return "저장된 기억이 없습니다."
        return "\n\n".join(parts)
