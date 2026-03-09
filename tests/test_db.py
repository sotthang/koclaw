import pytest

from koclaw.storage.db import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(tmp_path / "test.db")
    await database.initialize()
    yield database
    await database.close()


class TestDatabaseInitialization:
    async def test_initialize_creates_tables(self, db):
        tables = await db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        table_names = {row["name"] for row in tables}
        assert "messages" in table_names
        assert "scheduled_tasks" in table_names


class TestMessages:
    async def test_save_and_load_messages(self, db):
        await db.save_message(
            session_id="ch_001",
            role="user",
            content="안녕하세요",
        )
        messages = await db.get_messages(session_id="ch_001")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "안녕하세요"

    async def test_messages_ordered_by_created_at(self, db):
        await db.save_message("ch_001", "user", "첫 번째")
        await db.save_message("ch_001", "assistant", "두 번째")

        messages = await db.get_messages("ch_001")
        assert messages[0]["content"] == "첫 번째"
        assert messages[1]["content"] == "두 번째"

    async def test_messages_isolated_by_session(self, db):
        await db.save_message("ch_001", "user", "채널1 메시지")
        await db.save_message("ch_002", "user", "채널2 메시지")

        ch1 = await db.get_messages("ch_001")
        ch2 = await db.get_messages("ch_002")
        assert len(ch1) == 1
        assert len(ch2) == 1
        assert ch1[0]["content"] == "채널1 메시지"

    async def test_get_recent_messages_with_limit(self, db):
        for i in range(5):
            await db.save_message("ch_001", "user", f"메시지 {i}")

        recent = await db.get_messages("ch_001", limit=3)
        assert len(recent) == 3
        assert recent[-1]["content"] == "메시지 4"


class TestMessageSlackTs:
    async def test_save_message_returns_id(self, db):
        msg_id = await db.save_message("ch_001", "user", "안녕")
        assert isinstance(msg_id, int)
        assert msg_id > 0

    async def test_update_message_slack_ts(self, db):
        msg_id = await db.save_message("ch_001", "assistant", "응답")
        await db.update_message_slack_ts(msg_id, "1234.5678")

        rows = await db.fetch_all("SELECT slack_ts FROM messages WHERE id = ?", (msg_id,))
        assert rows[0]["slack_ts"] == "1234.5678"

    async def test_delete_message_pair_by_slack_ts(self, db):
        """x 이모지로 assistant 메시지 삭제 시 user 메시지도 함께 삭제"""
        await db.save_message("ch_001", "user", "질문")
        asst_id = await db.save_message("ch_001", "assistant", "답변")
        await db.update_message_slack_ts(asst_id, "9999.0001")

        deleted = await db.delete_message_pair_by_slack_ts("9999.0001")

        assert deleted is True
        remaining = await db.get_messages("ch_001")
        assert len(remaining) == 0

    async def test_delete_message_pair_returns_false_when_not_found(self, db):
        deleted = await db.delete_message_pair_by_slack_ts("0000.0000")
        assert deleted is False

    async def test_delete_message_pair_keeps_other_messages(self, db):
        """삭제할 메시지 외 다른 메시지는 보존"""
        await db.save_message("ch_001", "user", "첫 번째 질문")
        await db.save_message("ch_001", "assistant", "첫 번째 답변")
        await db.save_message("ch_001", "user", "두 번째 질문")
        asst_id = await db.save_message("ch_001", "assistant", "두 번째 답변")
        await db.update_message_slack_ts(asst_id, "9999.0002")

        await db.delete_message_pair_by_slack_ts("9999.0002")

        remaining = await db.get_messages("ch_001")
        assert len(remaining) == 2
        assert remaining[0]["content"] == "첫 번째 질문"
        assert remaining[1]["content"] == "첫 번째 답변"


class TestMemories:
    async def test_save_and_get_memory(self, db):
        await db.save_memory("user", "user123", "이름: 홍길동")
        result = await db.get_memory("user", "user123")
        assert result == "이름: 홍길동"

    async def test_save_memory_upserts(self, db):
        await db.save_memory("user", "user123", "버전1")
        await db.save_memory("user", "user123", "버전2")
        result = await db.get_memory("user", "user123")
        assert result == "버전2"

    async def test_get_memory_returns_none_when_not_found(self, db):
        result = await db.get_memory("user", "nobody")
        assert result is None

    async def test_delete_memory(self, db):
        await db.save_memory("channel", "slack:C001", "채널 기억")
        deleted = await db.delete_memory("channel", "slack:C001")
        assert deleted is True
        assert await db.get_memory("channel", "slack:C001") is None

    async def test_delete_memory_returns_false_when_not_found(self, db):
        result = await db.delete_memory("channel", "nonexistent")
        assert result is False

    async def test_memories_isolated_by_scope_type(self, db):
        await db.save_memory("user", "id1", "유저 기억")
        await db.save_memory("channel", "id1", "채널 기억")
        assert await db.get_memory("user", "id1") == "유저 기억"
        assert await db.get_memory("channel", "id1") == "채널 기억"


class TestSessionSummaries:
    async def test_save_and_get_summary(self, db):
        await db.save_summary("ch_001", "대화 요약입니다")
        result = await db.get_summary("ch_001")
        assert result == "대화 요약입니다"

    async def test_save_summary_upserts(self, db):
        await db.save_summary("ch_001", "요약1")
        await db.save_summary("ch_001", "요약2")
        result = await db.get_summary("ch_001")
        assert result == "요약2"

    async def test_get_summary_returns_none_when_not_found(self, db):
        result = await db.get_summary("ch_001")
        assert result is None

    async def test_count_messages(self, db):
        await db.save_message("ch_001", "user", "a")
        await db.save_message("ch_001", "user", "b")
        assert await db.count_messages("ch_001") == 2

    async def test_count_messages_isolated_by_session(self, db):
        await db.save_message("ch_001", "user", "a")
        await db.save_message("ch_002", "user", "b")
        assert await db.count_messages("ch_001") == 1
        assert await db.count_messages("ch_002") == 1

    async def test_delete_old_messages_keeps_recent(self, db):
        for i in range(6):
            await db.save_message("ch_001", "user", f"메시지 {i}")
        await db.delete_old_messages("ch_001", keep_last=3)
        remaining = await db.get_messages("ch_001")
        assert len(remaining) == 3
        assert remaining[-1]["content"] == "메시지 5"

    async def test_delete_old_messages_does_not_affect_other_sessions(self, db):
        for i in range(5):
            await db.save_message("ch_001", "user", f"ch1 메시지 {i}")
        await db.save_message("ch_002", "user", "ch2 메시지")
        await db.delete_old_messages("ch_001", keep_last=2)
        assert await db.count_messages("ch_002") == 1


class TestScheduledTasks:
    async def test_save_and_load_task(self, db):
        await db.save_task(
            session_id="ch_001",
            title="회의 알림",
            run_at="2026-03-10 09:00:00",
        )
        tasks = await db.get_pending_tasks()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "회의 알림"

    async def test_mark_task_notified(self, db):
        await db.save_task("ch_001", "테스트 알림", "2026-01-01 00:00:00")
        tasks = await db.get_pending_tasks()
        task_id = tasks[0]["id"]

        await db.mark_task_notified(task_id)

        pending = await db.get_pending_tasks()
        assert len(pending) == 0

    async def test_get_due_tasks(self, db):
        await db.save_task("ch_001", "과거 알림", "2020-01-01 00:00:00")
        await db.save_task("ch_001", "미래 알림", "2099-01-01 00:00:00")

        due = await db.get_due_tasks()
        assert len(due) == 1
        assert due[0]["title"] == "과거 알림"

    async def test_get_due_tasks_uses_local_time(self, db):
        from datetime import datetime, timedelta

        # 1초 전 시각으로 저장 → local time 기준 즉시 발동되어야 함
        past = (datetime.now() - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        await db.save_task("ch_001", "즉시 알림", past)

        due = await db.get_due_tasks()
        assert len(due) == 1  # CURRENT_TIMESTAMP(UTC) 사용 시 KST 환경에서 실패

    async def test_save_task_with_recurrence(self, db):
        await db.save_task("ch_001", "매일 알림", "2026-03-10 09:00:00", recurrence="daily")
        tasks = await db.get_pending_tasks()
        assert tasks[0]["recurrence"] == "daily"

    async def test_advance_task_run_at_daily(self, db):
        await db.save_task("ch_001", "매일 알림", "2026-03-10 09:00:00", recurrence="daily")
        task_id = (await db.get_pending_tasks())[0]["id"]

        await db.advance_task_run_at(task_id, "daily")

        tasks = await db.get_pending_tasks()
        assert tasks[0]["run_at"] == "2026-03-11 09:00:00"

    async def test_advance_task_run_at_weekly(self, db):
        await db.save_task("ch_001", "매주 알림", "2026-03-10 09:00:00", recurrence="weekly")
        task_id = (await db.get_pending_tasks())[0]["id"]

        await db.advance_task_run_at(task_id, "weekly")

        tasks = await db.get_pending_tasks()
        assert tasks[0]["run_at"] == "2026-03-17 09:00:00"

    async def test_advance_task_run_at_monthly(self, db):
        await db.save_task("ch_001", "매월 알림", "2026-03-10 09:00:00", recurrence="monthly")
        task_id = (await db.get_pending_tasks())[0]["id"]

        await db.advance_task_run_at(task_id, "monthly")

        tasks = await db.get_pending_tasks()
        assert tasks[0]["run_at"] == "2026-04-10 09:00:00"
