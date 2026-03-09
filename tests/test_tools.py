from unittest.mock import MagicMock, patch

# ── SearchTool ────────────────────────────────────────────────────────────────

class TestSearchTool:
    async def test_returns_search_results(self):
        from koclaw.tools.search import SearchTool

        with patch("koclaw.tools.search.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = [
                {"title": "결과1", "body": "내용1", "href": "https://example.com/1"},
                {"title": "결과2", "body": "내용2", "href": "https://example.com/2"},
            ]
            tool = SearchTool()
            result = await tool.execute(query="파이썬 튜토리얼")

        assert "결과1" in result
        assert "내용1" in result

    async def test_returns_no_results_message(self):
        from koclaw.tools.search import SearchTool

        with patch("koclaw.tools.search.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = []
            tool = SearchTool()
            result = await tool.execute(query="존재하지않는검색어xyz")

        assert "결과" in result or "없" in result

    async def test_uses_korean_region(self):
        from koclaw.tools.search import SearchTool

        with patch("koclaw.tools.search.DDGS") as mock_ddgs:
            mock_text = mock_ddgs.return_value.__enter__.return_value.text
            mock_text.return_value = [
                {"title": "결과", "body": "내용", "href": "https://example.com"},
            ]
            tool = SearchTool()
            await tool.execute(query="검색어")

        call_kwargs = mock_text.call_args
        assert call_kwargs.kwargs.get("region") == "kr-ko"

    async def test_search_results_wrapped_with_external_data_delimiters(self):
        from koclaw.tools.search import SearchTool

        with patch("koclaw.tools.search.DDGS") as mock_ddgs:
            mock_ddgs.return_value.__enter__.return_value.text.return_value = [
                {"title": "결과1", "body": "내용1", "href": "https://example.com/1"},
            ]
            tool = SearchTool()
            result = await tool.execute(query="테스트")

        assert "[외부 데이터 시작:" in result
        assert "[외부 데이터 끝:" in result

    def test_is_not_sandboxed(self):
        from koclaw.tools.search import SearchTool
        assert SearchTool.is_sandboxed is False


# ── YouTubeTool ───────────────────────────────────────────────────────────────

class TestYouTubeTool:
    async def test_extracts_transcript(self):
        from koclaw.tools.youtube import YouTubeTool

        with patch("koclaw.tools.youtube.YouTubeTranscriptApi") as mock_api:
            mock_instance = mock_api.return_value
            mock_snippet1 = MagicMock()
            mock_snippet1.text = "안녕하세요"
            mock_snippet2 = MagicMock()
            mock_snippet2.text = "오늘은 파이썬을 배워봅시다"
            mock_instance.fetch.return_value = [mock_snippet1, mock_snippet2]
            tool = YouTubeTool()
            result = await tool.execute(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert "안녕하세요" in result
        assert "파이썬" in result

    async def test_extracts_video_id_from_url(self):
        from koclaw.tools.youtube import extract_video_id

        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    async def test_returns_error_on_invalid_url(self):
        from koclaw.tools.youtube import YouTubeTool

        tool = YouTubeTool()
        result = await tool.execute(url="https://not-youtube.com/video")

        assert "오류" in result or "실패" in result or "URL" in result

    async def test_transcript_wrapped_with_external_data_delimiters(self):
        from koclaw.tools.youtube import YouTubeTool

        with patch("koclaw.tools.youtube.YouTubeTranscriptApi") as mock_api:
            mock_snippet = MagicMock()
            mock_snippet.text = "자막 내용입니다"
            mock_api.return_value.fetch.return_value = [mock_snippet]
            tool = YouTubeTool()
            result = await tool.execute(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert "[외부 데이터 시작:" in result
        assert "[외부 데이터 끝:" in result

    def test_is_not_sandboxed(self):
        from koclaw.tools.youtube import YouTubeTool
        assert YouTubeTool.is_sandboxed is False


# ── SchedulerTool ─────────────────────────────────────────────────────────────

class TestSchedulerTool:
    async def test_adds_schedule(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(
            action="add",
            title="팀 회의",
            run_at="2026-03-10 09:00:00",
        )

        assert "추가" in result or "등록" in result
        tasks = await db.get_pending_tasks()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "팀 회의"

    async def test_lists_schedules(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        await db.save_task("ch_001", "미팅", "2026-03-10 09:00:00")
        await db.save_task("ch_001", "점심", "2026-03-10 12:00:00")

        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(action="list")

        assert "미팅" in result
        assert "점심" in result

    async def test_list_returns_empty_message_when_no_tasks(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(action="list")

        assert "없" in result

    async def test_updates_schedule_run_at(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        await db.save_task("ch_001", "아침 알림", "2026-03-04 09:00:00")

        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(
            action="update",
            title="아침 알림",
            run_at="2026-03-04 08:00:00",
        )

        assert "수정" in result or "변경" in result or "업데이트" in result
        tasks = await db.get_pending_tasks()
        assert tasks[0]["run_at"] == "2026-03-04 08:00:00"

    async def test_update_returns_error_when_not_found(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(
            action="update",
            title="없는 스케줄",
            run_at="2026-03-04 08:00:00",
        )

        assert "없" in result or "찾을 수 없" in result

    async def test_deletes_schedule(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        await db.save_task("ch_001", "삭제할 알림", "2026-03-04 09:00:00")

        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(action="delete", title="삭제할 알림")

        assert "삭제" in result or "취소" in result
        tasks = await db.get_pending_tasks()
        assert len(tasks) == 0

    async def test_delete_returns_error_when_not_found(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(action="delete", title="없는 스케줄")

        assert "없" in result or "찾을 수 없" in result

    async def test_adds_recurring_schedule(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(
            action="add",
            title="매일 브리핑",
            run_at="2026-03-10 09:00:00",
            recurrence="daily",
        )

        assert "등록" in result
        tasks = await db.get_pending_tasks()
        assert tasks[0]["recurrence"] == "daily"

    async def test_list_shows_recurrence(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        await db.save_task("ch_001", "매일 브리핑", "2026-03-10 09:00:00", recurrence="daily")
        await db.save_task("ch_001", "단발 알림", "2026-03-10 10:00:00")

        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(action="list")

        assert "매일" in result or "daily" in result
        assert "단발 알림" in result

    async def test_deletes_notified_schedule(self, make_db):
        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        await db.save_task("ch_001", "이미 발송된 알림", "2025-01-01 09:00:00")
        tasks = await db.get_pending_tasks()
        await db.mark_task_notified(tasks[0]["id"])

        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(action="delete", title="이미 발송된 알림")

        assert "삭제" in result or "취소" in result

    async def test_adds_recurring_schedule_without_run_at(self, make_db):
        """recurrence 스케줄은 run_at 없이 등록 가능하고, 자동으로 다음 실행 시각이 계산됨"""
        from datetime import datetime

        from koclaw.tools.scheduler import SchedulerTool

        db = await make_db()
        tool = SchedulerTool(db=db, session_id="ch_001")
        result = await tool.execute(
            action="add",
            title="매시간 트렌드",
            recurrence="hourly",
        )

        assert "등록" in result
        tasks = await db.get_pending_tasks()
        assert len(tasks) == 1
        assert tasks[0]["recurrence"] == "hourly"
        run_at = datetime.fromisoformat(tasks[0]["run_at"])
        assert run_at > datetime.now()

    def test_is_not_sandboxed(self):

        from koclaw.tools.scheduler import SchedulerTool
        assert SchedulerTool.is_sandboxed is False


# ── MemoryTool ────────────────────────────────────────────────────────────────

class TestMemoryTool:
    async def _make_tool(self, make_db, session_id="slack:D001", user_id="U1"):
        from koclaw.core.memory_context import parse_memory_context
        from koclaw.tools.memory import MemoryTool

        db = await make_db()
        ctx = parse_memory_context(session_id, user_id=user_id)
        return MemoryTool(db=db, memory_context=ctx), db

    async def test_writes_user_memory_in_dm(self, make_db):
        tool, db = await self._make_tool(make_db, session_id="slack:D001", user_id="U1")
        result = await tool.execute(action="write", scope="user", content="이름: 홍길동")
        assert "저장" in result
        assert await db.get_memory("user", "U1") == "이름: 홍길동"

    async def test_reads_user_memory_in_dm(self, make_db):
        tool, db = await self._make_tool(make_db, session_id="slack:D001", user_id="U1")
        await db.save_memory("user", "U1", "좋아하는 음식: 김치찌개")
        result = await tool.execute(action="read")
        assert "김치찌개" in result

    async def test_reads_empty_memory(self, make_db):
        tool, _ = await self._make_tool(make_db, session_id="slack:D001", user_id="U1")
        result = await tool.execute(action="read")
        assert "없" in result or "비어" in result

    async def test_writes_channel_memory(self, make_db):
        tool, db = await self._make_tool(make_db, session_id="slack:C001", user_id="U1")
        await tool.execute(action="write", scope="channel", content="채널 목적: 개발")
        assert await db.get_memory("channel", "slack:C001") == "채널 목적: 개발"

    async def test_writes_thread_memory(self, make_db):
        tool, db = await self._make_tool(make_db, session_id="slack:C001:ts123", user_id="U1")
        await tool.execute(action="write", scope="thread", content="스레드 맥락")
        assert await db.get_memory("thread", "slack:C001:ts123") == "스레드 맥락"

    async def test_delete_memory(self, make_db):
        tool, db = await self._make_tool(make_db, session_id="slack:D001", user_id="U1")
        await db.save_memory("user", "U1", "삭제할 기억")
        result = await tool.execute(action="delete", scope="user")
        assert "삭제" in result
        assert await db.get_memory("user", "U1") is None

    async def test_write_requires_scope(self, make_db):
        tool, _ = await self._make_tool(make_db)
        result = await tool.execute(action="write", content="내용")
        assert "scope" in result or "오류" in result

    async def test_write_invalid_scope_for_context(self, make_db):
        """DM에서 channel scope 쓰기 시도 → 오류"""
        tool, _ = await self._make_tool(make_db, session_id="slack:D001", user_id="U1")
        result = await tool.execute(action="write", scope="channel", content="내용")
        assert "오류" in result or "사용할 수 없" in result

    async def test_read_thread_includes_channel_memory(self, make_db):
        """스레드에서 read 시 채널 기억도 포함"""
        tool, db = await self._make_tool(make_db, session_id="slack:C001:ts", user_id="U1")
        await db.save_memory("channel", "slack:C001", "채널 기억")
        await db.save_memory("thread", "slack:C001:ts", "스레드 기억")
        result = await tool.execute(action="read")
        assert "채널 기억" in result
        assert "스레드 기억" in result

    def test_is_not_sandboxed(self):
        from koclaw.tools.memory import MemoryTool
        assert MemoryTool.is_sandboxed is False
