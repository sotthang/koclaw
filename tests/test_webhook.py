"""WebhookTool / webhook_server 단위 테스트 — DB, HTTP 서버 없이 mock으로 격리"""

from unittest.mock import AsyncMock, patch

import pytest

from koclaw.core.webhook_server import _dict_to_readable, _format_message
from koclaw.tools.webhook import WebhookTool

# ── _dict_to_readable ──────────────────────────────────────────────────────


def test_dict_to_readable_simple():
    result = _dict_to_readable({"action": "opened", "number": 42})
    assert "action" in result
    assert "opened" in result
    assert "42" in result


def test_dict_to_readable_nested():
    result = _dict_to_readable({"repo": {"name": "koclaw", "private": False}})
    assert "repo" in result
    assert "koclaw" in result


def test_dict_to_readable_list_value():
    result = _dict_to_readable({"labels": ["bug", "feature"]})
    assert "labels" in result
    assert "2개 항목" in result


def test_dict_to_readable_none_value_skipped():
    result = _dict_to_readable({"key": None, "val": "hello"})
    assert "key" not in result
    assert "hello" in result


# ── _format_message ─────────────────────────────────────────────────────────


def test_format_message_basic():
    result = _format_message("테스트 웹훅", {"event": "push"}, {})
    assert "테스트 웹훅" in result
    assert "🔔" in result


def test_format_message_github_event_header():
    result = _format_message("GitHub", {"action": "opened"}, {"X-GitHub-Event": "pull_request"})
    assert "pull_request" in result
    assert "GitHub 이벤트" in result


def test_format_message_plain_text_payload():
    result = _format_message("서버 알림", "CPU 90% 초과", {})
    assert "CPU 90% 초과" in result


def test_format_message_wraps_external_content():
    result = _format_message("웹훅", {"key": "value"}, {})
    assert "외부 데이터 시작" in result


# ── WebhookTool — WEBHOOK_HOST 없음 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_missing_host():
    tool = WebhookTool(db=AsyncMock())
    with patch.dict("os.environ", {}, clear=True):
        result = await tool.execute(action="register", description="테스트", _session_id="s1")
    assert "WEBHOOK_HOST" in result


# ── WebhookTool._register ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_missing_description():
    tool = WebhookTool(db=AsyncMock())
    with patch.dict("os.environ", {"WEBHOOK_HOST": "https://example.com"}):
        result = await tool.execute(action="register", _session_id="s1")
    assert "description" in result or "설명" in result


@pytest.mark.asyncio
async def test_register_success():
    mock_db = AsyncMock()
    tool = WebhookTool(db=mock_db)
    with patch.dict("os.environ", {"WEBHOOK_HOST": "https://example.com"}):
        result = await tool.execute(
            action="register", description="GitHub PR 알림", _session_id="slack:dm:U123"
        )
    assert "✅" in result
    assert "https://example.com/webhook/" in result
    assert "GitHub PR 알림" in result
    mock_db.save_webhook.assert_called_once()


# ── WebhookTool._list ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_empty():
    mock_db = AsyncMock()
    mock_db.get_webhooks.return_value = []
    tool = WebhookTool(db=mock_db)
    with patch.dict("os.environ", {"WEBHOOK_HOST": "https://example.com"}):
        result = await tool.execute(action="list", _session_id="s1")
    assert "없습니다" in result


@pytest.mark.asyncio
async def test_list_with_webhooks():
    mock_db = AsyncMock()
    mock_db.get_webhooks.return_value = [
        {"description": "GitHub PR", "token": "abc123", "created_at": "2026-03-19"},
        {"description": "CI 알림", "token": "def456", "created_at": "2026-03-19"},
    ]
    tool = WebhookTool(db=mock_db)
    with patch.dict("os.environ", {"WEBHOOK_HOST": "https://example.com"}):
        result = await tool.execute(action="list", _session_id="s1")
    assert "GitHub PR" in result
    assert "CI 알림" in result
    assert "abc123" in result


# ── WebhookTool._delete ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_missing_token():
    tool = WebhookTool(db=AsyncMock())
    with patch.dict("os.environ", {"WEBHOOK_HOST": "https://example.com"}):
        result = await tool.execute(action="delete", _session_id="s1")
    assert "token" in result or "토큰" in result


@pytest.mark.asyncio
async def test_delete_not_found():
    mock_db = AsyncMock()
    mock_db.delete_webhook.return_value = False
    tool = WebhookTool(db=mock_db)
    with patch.dict("os.environ", {"WEBHOOK_HOST": "https://example.com"}):
        result = await tool.execute(action="delete", token="nonexistent", _session_id="s1")
    assert "찾을 수 없습니다" in result


@pytest.mark.asyncio
async def test_delete_success():
    mock_db = AsyncMock()
    mock_db.delete_webhook.return_value = True
    tool = WebhookTool(db=mock_db)
    with patch.dict("os.environ", {"WEBHOOK_HOST": "https://example.com"}):
        result = await tool.execute(action="delete", token="abc123", _session_id="s1")
    assert "✅" in result
    mock_db.delete_webhook.assert_called_once_with("s1", "abc123")
