import asyncio
from unittest.mock import AsyncMock

from koclaw.core.scheduler_loop import SchedulerLoop


class TestSchedulerLoop:
    async def test_notifies_due_tasks(self, tmp_path):
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_task("ch_001", "회의 알림", "2020-01-01 00:00:00")  # 과거 = 즉시 실행

        notify_fn = AsyncMock()
        loop = SchedulerLoop(db=db, notify_fn=notify_fn, interval=0.01)

        await loop.tick()

        notify_fn.assert_called_once()
        call_args = notify_fn.call_args.kwargs
        assert call_args["session_id"] == "ch_001"
        assert "회의 알림" in call_args["message"]

    async def test_marks_task_as_notified_after_sending(self, tmp_path):
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_task("ch_001", "알림", "2020-01-01 00:00:00")

        loop = SchedulerLoop(db=db, notify_fn=AsyncMock(), interval=0.01)
        await loop.tick()
        await loop.tick()  # 두 번째 tick에서는 이미 처리됨

        # notify_fn은 딱 1번만 호출
        assert loop._notify_fn.call_count == 1

    async def test_does_not_notify_future_tasks(self, tmp_path):
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_task("ch_001", "미래 알림", "2099-01-01 00:00:00")

        notify_fn = AsyncMock()
        loop = SchedulerLoop(db=db, notify_fn=notify_fn, interval=0.01)
        await loop.tick()

        notify_fn.assert_not_called()

    async def test_recurring_task_advances_instead_of_notifying(self, tmp_path):
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_task("ch_001", "매일 브리핑", "2020-01-01 09:00:00", recurrence="daily")

        loop = SchedulerLoop(db=db, notify_fn=AsyncMock(), interval=0.01)
        await loop.tick()

        tasks = await db.get_pending_tasks()
        assert len(tasks) == 1  # 삭제되지 않고 남아있음
        assert tasks[0]["run_at"] == "2020-01-02 09:00:00"  # 다음 날로 이동

    async def test_recurring_task_notifies_every_tick(self, tmp_path):
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_task("ch_001", "매일 브리핑", "2020-01-01 09:00:00", recurrence="daily")

        notify_fn = AsyncMock()
        loop = SchedulerLoop(db=db, notify_fn=notify_fn, interval=0.01)
        await loop.tick()  # 2020-01-01 발송, run_at → 2020-01-02 (과거)
        await loop.tick()  # 2020-01-02 발송, run_at → 2020-01-03 (과거)

        assert notify_fn.call_count == 2

    async def test_runs_and_stops(self, tmp_path):
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()

        loop = SchedulerLoop(db=db, notify_fn=AsyncMock(), interval=0.01)
        task = asyncio.create_task(loop.start())
        await asyncio.sleep(0.05)
        loop.stop()
        await asyncio.wait_for(task, timeout=1.0)

    async def test_uses_agent_fn_to_generate_notification_content(self, tmp_path):
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_task("ch_001", "AI 트렌드 알림", "2020-01-01 00:00:00")

        agent_fn = AsyncMock(return_value="오늘의 AI 트렌드: GPT-5 출시...")
        notify_fn = AsyncMock()
        loop = SchedulerLoop(db=db, notify_fn=notify_fn, agent_fn=agent_fn, interval=0.01)

        await loop.tick()

        # 스케줄 title은 [스케줄 실행] 접두사와 함께 전달되어야 함
        called_kwargs = agent_fn.call_args.kwargs
        assert called_kwargs["session_id"] == "ch_001"
        assert "AI 트렌드 알림" in called_kwargs["user_message"]
        assert called_kwargs["files"] == []

        call_args = notify_fn.call_args.kwargs
        assert "오늘의 AI 트렌드" in call_args["message"]

    async def test_agent_fn_receives_scheduled_task_context_prefix(self, tmp_path):
        """스케줄러 title이 LLM 인젝션 방지를 위해 컨텍스트 접두사와 함께 전달됨"""
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_task("ch_001", "뉴스 요약", "2020-01-01 00:00:00")

        agent_fn = AsyncMock(return_value="뉴스 요약 결과")
        loop = SchedulerLoop(db=db, notify_fn=AsyncMock(), agent_fn=agent_fn, interval=0.01)

        await loop.tick()

        called_user_message = agent_fn.call_args.kwargs["user_message"]
        assert "[스케줄 실행]" in called_user_message
        assert "뉴스 요약" in called_user_message

    async def test_falls_back_to_title_when_no_agent_fn(self, tmp_path):
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_task("ch_001", "회의 알림", "2020-01-01 00:00:00")

        notify_fn = AsyncMock()
        loop = SchedulerLoop(db=db, notify_fn=notify_fn, interval=0.01)

        await loop.tick()

        call_args = notify_fn.call_args.kwargs
        assert "회의 알림" in call_args["message"]

    async def test_task_failure_does_not_stop_other_tasks(self, tmp_path):
        """하나의 task 실패가 나머지 task 처리를 막지 않는다"""
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_task("ch_001", "첫 번째 알림", "2020-01-01 00:00:00")
        await db.save_task("ch_002", "두 번째 알림", "2020-01-01 00:00:00")

        call_count = 0

        async def failing_notify(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs["session_id"] == "ch_001":
                raise RuntimeError("notify 실패")

        loop = SchedulerLoop(db=db, notify_fn=failing_notify, interval=0.01)
        await loop.tick()

        assert call_count == 2
