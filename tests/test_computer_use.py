"""computer_use tool 단위 테스트"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from koclaw.tools.computer_use import ComputerUseTool


@pytest.fixture
def manager():
    m = MagicMock()
    m.screenshot = AsyncMock(return_value="base64encodedpng==")
    m.click = AsyncMock(return_value="✅ (100, 200) 클릭 완료")
    m.type_text = AsyncMock(return_value="✅ 텍스트 입력 완료: hello")
    m.key = AsyncMock(return_value="✅ 키 입력 완료: Return")
    m.open_url = AsyncMock(return_value="✅ URL 열기 요청: https://example.com")
    m.scroll = AsyncMock(return_value="✅ down 스크롤 완료")
    m.run_command = AsyncMock(return_value="Python 3.11.0")
    return m


@pytest.fixture
def tool(manager):
    return ComputerUseTool(manager=manager)


# ── 스키마 ──────────────────────────────────────────────────────────────────


def test_tool_name(tool):
    assert tool.name == "computer_use"


def test_tool_is_not_sandboxed(tool):
    assert tool.is_sandboxed is False


def test_tool_needs_session_context(tool):
    assert tool.needs_session_context is True


def test_tool_has_action_parameter(tool):
    schema = tool.schema()
    assert "action" in schema["parameters"]["properties"]


def test_tool_action_is_required(tool):
    schema = tool.schema()
    assert "action" in schema["parameters"]["required"]


def test_tool_action_enum(tool):
    schema = tool.schema()
    actions = schema["parameters"]["properties"]["action"]["enum"]
    assert set(actions) == {
        "screenshot",
        "click",
        "type",
        "key",
        "open_url",
        "scroll",
        "run_command",
        "copy_from",
        "reset",
    }


# ── 액션 라우팅 ──────────────────────────────────────────────────────────────


async def test_screenshot(tool, manager):
    result = await tool.execute(action="screenshot", _session_id="test-session")
    manager.screenshot.assert_awaited_once_with("test-session")
    assert result == "base64encodedpng=="


async def test_click(tool, manager):
    result = await tool.execute(action="click", x=100, y=200, _session_id="s1")
    manager.click.assert_awaited_once_with("s1", 100, 200)
    assert "클릭" in result


async def test_click_missing_coords(tool):
    result = await tool.execute(action="click", _session_id="s1")
    assert "오류" in result


async def test_type(tool, manager):
    result = await tool.execute(action="type", text="hello", _session_id="s1")
    manager.type_text.assert_awaited_once_with("s1", "hello")
    assert "입력" in result


async def test_type_missing_text(tool):
    result = await tool.execute(action="type", _session_id="s1")
    assert "오류" in result


async def test_key(tool, manager):
    result = await tool.execute(action="key", key_name="Return", _session_id="s1")
    manager.key.assert_awaited_once_with("s1", "Return")
    assert "키" in result


async def test_key_missing_name(tool):
    result = await tool.execute(action="key", _session_id="s1")
    assert "오류" in result


async def test_open_url(tool, manager):
    result = await tool.execute(action="open_url", url="https://example.com", _session_id="s1")
    manager.open_url.assert_awaited_once_with("s1", "https://example.com")
    assert "URL" in result


async def test_open_url_missing_url(tool):
    result = await tool.execute(action="open_url", _session_id="s1")
    assert "오류" in result


async def test_scroll(tool, manager):
    result = await tool.execute(action="scroll", x=640, y=360, direction="down", _session_id="s1")
    manager.scroll.assert_awaited_once_with("s1", 640, 360, "down", 3)
    assert "스크롤" in result


async def test_run_command(tool, manager):
    result = await tool.execute(action="run_command", command="python3 --version", _session_id="s1")
    manager.run_command.assert_awaited_once_with("s1", "python3 --version")
    assert result == "Python 3.11.0"


async def test_run_command_missing_command(tool):
    result = await tool.execute(action="run_command", _session_id="s1")
    assert "오류" in result


async def test_unknown_action(tool):
    result = await tool.execute(action="fly", _session_id="s1")
    assert "오류" in result


async def test_default_session_id(tool, manager):
    """_session_id 없이 호출하면 'default' 사용"""
    await tool.execute(action="screenshot")
    manager.screenshot.assert_awaited_once_with("default")


# ── copy_from / copy_to ───────────────────────────────────────────────────────


async def test_copy_from(tool, manager):
    manager.copy_from = AsyncMock(
        return_value="✅ chart.png (12345 bytes) — 채팅에 파일로 업로드됩니다"
    )
    result = await tool.execute(
        action="copy_from", container_path="/tmp/chart.png", _session_id="s1"
    )
    manager.copy_from.assert_awaited_once_with("s1", "/tmp/chart.png")
    assert "chart.png" in result


async def test_copy_from_missing_path(tool):
    result = await tool.execute(action="copy_from", _session_id="s1")
    assert "오류" in result


async def test_reset(tool, manager):
    manager.reset = AsyncMock(
        return_value="✅ 가상 데스크탑이 초기화됐습니다. 다음 작업 시 새 환경이 시작됩니다."
    )
    result = await tool.execute(action="reset", _session_id="s1")
    manager.reset.assert_awaited_once_with("s1")
    assert "초기화" in result
