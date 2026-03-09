from datetime import datetime, timedelta

from koclaw.core.tool import Tool
from koclaw.storage.db import Database


_MAX_TITLE_LENGTH = 200


class SchedulerTool(Tool):
    name = "scheduler"
    description = "스케줄을 등록, 조회, 수정, 삭제합니다. 지원하는 반복 주기: hourly(매시간), daily(매일), weekly(매주), monthly(매월). 지원하지 않는 주기(예: 10분마다)는 사용자에게 안내하고 가장 가까운 지원 주기를 제안하세요."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "update", "delete"],
                "description": "add: 등록, list: 조회, update: 시각 수정, delete: 삭제",
            },
            "title": {
                "type": "string",
                "description": "스케줄 제목 (add/update/delete 시 필수)",
            },
            "run_at": {
                "type": "string",
                "description": "실행 시각 (add/update 시 필수, 예: 2026-03-10 09:00:00)",
            },
            "recurrence": {
                "type": "string",
                "enum": ["hourly", "daily", "weekly", "monthly"],
                "description": "반복 주기 (add 시 선택, 없으면 단발성): hourly=매시간, daily=매일, weekly=매주, monthly=매월",
            },
        },
        "required": ["action"],
    }
    is_sandboxed = False

    def __init__(self, db: Database, session_id: str):
        self._db = db
        self._session_id = session_id

    _RECURRENCE_LABEL = {"hourly": "매시간", "daily": "매일", "weekly": "매주", "monthly": "매월"}

    async def execute(
        self, action: str, title: str = "", run_at: str = "", recurrence: str = ""
    ) -> str:
        if action == "add":
            title = title.replace("\n", " ").replace("\r", " ").strip()
            if len(title) > _MAX_TITLE_LENGTH:
                return f"오류: 스케줄 제목이 너무 깁니다 (최대 {_MAX_TITLE_LENGTH}자)."
            if not run_at and recurrence:
                run_at = self._next_run_at(recurrence)
            await self._db.save_task(
                self._session_id, title, run_at, recurrence=recurrence or None
            )
            suffix = f" ({self._RECURRENCE_LABEL.get(recurrence, '')} 반복)" if recurrence else ""
            return f"✅ 스케줄이 등록되었습니다: '{title}' ({run_at}){suffix}"

        if action == "list":
            tasks = await self._db.get_pending_tasks()
            session_tasks = [t for t in tasks if t["session_id"] == self._session_id]
            if not session_tasks:
                return "등록된 스케줄이 없습니다."
            lines = []
            for t in session_tasks:
                label = self._RECURRENCE_LABEL.get(t.get("recurrence") or "", "")
                repeat = f" [{label} 반복]" if label else ""
                lines.append(f"- {t['title']} ({t['run_at']}){repeat}")
            return "📅 스케줄 목록:\n" + "\n".join(lines)

        if action == "update":
            updated = await self._db.update_task_run_at(self._session_id, title, run_at)
            if not updated:
                return f"'{title}' 스케줄을 찾을 수 없습니다."
            return f"✅ '{title}' 스케줄이 {run_at}으로 변경되었습니다."

        if action == "delete":
            deleted = await self._db.delete_task(self._session_id, title)
            if not deleted:
                return f"'{title}' 스케줄을 찾을 수 없습니다."
            return f"✅ '{title}' 스케줄이 삭제되었습니다."

        return f"알 수 없는 action: {action}"

    @staticmethod
    def _next_run_at(recurrence: str) -> str:
        now = datetime.now()
        if recurrence == "hourly":
            next_run = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        elif recurrence == "daily":
            next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif recurrence == "weekly":
            next_run = (now + timedelta(weeks=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif recurrence == "monthly":
            month = now.month % 12 + 1
            year = now.year + (1 if now.month == 12 else 0)
            next_run = now.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_run = now + timedelta(hours=1)
        return next_run.strftime("%Y-%m-%d %H:%M:%S")
