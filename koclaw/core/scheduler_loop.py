import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from koclaw.storage.db import Database

logger = logging.getLogger(__name__)

NotifyFn = Callable[..., Coroutine[Any, Any, None]]
AgentFn = Callable[..., Coroutine[Any, Any, str]]


class SchedulerLoop:
    def __init__(
        self,
        db: Database,
        notify_fn: NotifyFn,
        agent_fn: AgentFn | None = None,
        interval: float = 60.0,
    ):
        self._db = db
        self._notify_fn = notify_fn
        self._agent_fn = agent_fn
        self._interval = interval
        self._running = False

    async def tick(self) -> None:
        due_tasks = await self._db.get_due_tasks()
        for task in due_tasks:
            try:
                if self._agent_fn:
                    message = await self._agent_fn(
                        session_id=task["session_id"],
                        user_message=f"[스케줄 실행] {task['title']}",
                        files=[],
                    )
                else:
                    message = f"⏰ 알림: {task['title']}"
                await self._notify_fn(
                    session_id=task["session_id"],
                    message=message,
                )
                if task.get("recurrence"):
                    await self._db.advance_task_run_at(task["id"], task["recurrence"])
                else:
                    await self._db.mark_task_notified(task["id"])
            except Exception:
                logger.exception(
                    "[scheduler] task 실행 실패: id=%s title=%r", task["id"], task["title"]
                )

    async def start(self) -> None:
        self._running = True
        while self._running:
            await self.tick()
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False
