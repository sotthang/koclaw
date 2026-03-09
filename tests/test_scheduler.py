"""SchedulerTool 단위 테스트."""
from unittest.mock import AsyncMock

import pytest

from koclaw.tools.scheduler import SchedulerTool

MAX_TITLE_LENGTH = 200


def _make_tool() -> tuple[SchedulerTool, AsyncMock]:
    db = AsyncMock()
    db.save_task = AsyncMock()
    db.get_pending_tasks = AsyncMock(return_value=[])
    db.update_task_run_at = AsyncMock(return_value=True)
    db.delete_task = AsyncMock(return_value=True)
    tool = SchedulerTool(db=db, session_id="discord:123")
    return tool, db


class TestSchedulerTitleSanitization:
    async def test_newline_in_title_is_stripped(self):
        """제목에 줄바꿈이 있으면 제거 후 저장된다."""
        tool, db = _make_tool()
        await tool.execute(action="add", title="매일 뉴스\n요약", run_at="2026-03-11 09:00:00")
        saved_title = db.save_task.call_args[0][1]
        assert "\n" not in saved_title
        assert "매일 뉴스" in saved_title

    async def test_carriage_return_in_title_is_stripped(self):
        """제목에 캐리지 리턴이 있으면 제거 후 저장된다."""
        tool, db = _make_tool()
        await tool.execute(action="add", title="뉴스\r요약", run_at="2026-03-11 09:00:00")
        saved_title = db.save_task.call_args[0][1]
        assert "\r" not in saved_title

    async def test_title_exceeding_max_length_is_rejected(self):
        """제목이 최대 길이를 초과하면 오류 메시지를 반환한다."""
        tool, db = _make_tool()
        long_title = "A" * (MAX_TITLE_LENGTH + 1)
        result = await tool.execute(action="add", title=long_title, run_at="2026-03-11 09:00:00")
        assert "오류" in result or "길이" in result or "초과" in result
        db.save_task.assert_not_called()

    async def test_title_at_max_length_is_accepted(self):
        """제목이 최대 길이와 같으면 정상 저장된다."""
        tool, db = _make_tool()
        title = "A" * MAX_TITLE_LENGTH
        result = await tool.execute(action="add", title=title, run_at="2026-03-11 09:00:00")
        assert "✅" in result
        db.save_task.assert_called_once()

    async def test_normal_title_is_saved_as_is(self):
        """일반 제목은 그대로 저장된다."""
        tool, db = _make_tool()
        result = await tool.execute(action="add", title="매일 AI 뉴스 요약", run_at="2026-03-11 09:00:00")
        assert "✅" in result
        saved_title = db.save_task.call_args[0][1]
        assert saved_title == "매일 AI 뉴스 요약"
