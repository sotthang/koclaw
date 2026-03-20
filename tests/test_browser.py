"""BrowserTool 단위 테스트"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from koclaw.tools.browser import BrowserTool


@pytest.fixture
def manager():
    m = MagicMock()
    m.browser_navigate = AsyncMock(return_value="✅ 페이지 이동 완료: 네이버 (https://naver.com)")
    m.browser_screenshot = AsyncMock(return_value="/9j/base64jpeg==")
    m.browser_click = AsyncMock(return_value="✅ 클릭 완료: text=로그인")
    m.browser_type = AsyncMock(return_value="✅ 입력 완료: #id ← test")
    m.browser_scroll = AsyncMock(return_value="✅ down 스크롤 완료")
    m.browser_evaluate = AsyncMock(return_value="document.title")
    m.browser_content = AsyncMock(return_value="[네이버] https://naver.com\n\n페이지 내용...")
    m.browser_wait_for = AsyncMock(return_value="✅ 요소 나타남: .btn")
    m.browser_select = AsyncMock(return_value="✅ 선택 완료: #select = value1")
    m.browser_close = AsyncMock(return_value="✅ 브라우저 닫힘")
    return m


@pytest.fixture
def tool(manager):
    return BrowserTool(manager=manager)


# ── 스키마 ──────────────────────────────────────────────────────────────────


def test_tool_name(tool):
    assert tool.name == "browser"


def test_tool_is_not_sandboxed(tool):
    assert tool.is_sandboxed is False


def test_tool_needs_session_context(tool):
    assert tool.needs_session_context is True


def test_tool_action_is_required(tool):
    schema = tool.schema()
    assert "action" in schema["parameters"]["required"]


def test_tool_action_enum(tool):
    schema = tool.schema()
    actions = schema["parameters"]["properties"]["action"]["enum"]
    assert set(actions) == {
        "navigate",
        "screenshot",
        "click",
        "type",
        "scroll",
        "evaluate",
        "content",
        "wait_for",
        "select",
        "close",
    }


# ── 액션 라우팅 ──────────────────────────────────────────────────────────────


async def test_navigate(tool, manager):
    result = await tool.execute(action="navigate", url="https://naver.com", _session_id="s1")
    manager.browser_navigate.assert_awaited_once_with("s1", "https://naver.com", "domcontentloaded")
    assert "이동" in result


async def test_navigate_missing_url(tool):
    result = await tool.execute(action="navigate", _session_id="s1")
    assert "오류" in result


async def test_screenshot(tool, manager):
    result = await tool.execute(action="screenshot", _session_id="s1")
    manager.browser_screenshot.assert_awaited_once_with("s1")
    assert result == "/9j/base64jpeg=="


async def test_click(tool, manager):
    result = await tool.execute(action="click", selector="text=로그인", _session_id="s1")
    manager.browser_click.assert_awaited_once_with("s1", "text=로그인")
    assert "클릭" in result


async def test_click_missing_selector(tool):
    result = await tool.execute(action="click", _session_id="s1")
    assert "오류" in result


async def test_type(tool, manager):
    result = await tool.execute(action="type", selector="#id", text="test", _session_id="s1")
    manager.browser_type.assert_awaited_once_with("s1", "#id", "test", True)
    assert "입력" in result


async def test_type_missing_fields(tool):
    result = await tool.execute(action="type", selector="#id", _session_id="s1")
    assert "오류" in result


async def test_scroll(tool, manager):
    result = await tool.execute(action="scroll", direction="down", amount=3, _session_id="s1")
    manager.browser_scroll.assert_awaited_once_with("s1", "down", 3)
    assert "스크롤" in result


async def test_evaluate(tool, manager):
    await tool.execute(action="evaluate", script="document.title", _session_id="s1")
    manager.browser_evaluate.assert_awaited_once_with("s1", "document.title")


async def test_evaluate_missing_script(tool):
    result = await tool.execute(action="evaluate", _session_id="s1")
    assert "오류" in result


async def test_content(tool, manager):
    result = await tool.execute(action="content", _session_id="s1")
    manager.browser_content.assert_awaited_once_with("s1")
    assert "네이버" in result


async def test_wait_for(tool, manager):
    await tool.execute(action="wait_for", selector=".btn", _session_id="s1")
    manager.browser_wait_for.assert_awaited_once_with("s1", ".btn", 10.0)


async def test_wait_for_missing_selector(tool):
    result = await tool.execute(action="wait_for", _session_id="s1")
    assert "오류" in result


async def test_select(tool, manager):
    await tool.execute(action="select", selector="#sel", value="v1", _session_id="s1")
    manager.browser_select.assert_awaited_once_with("s1", "#sel", "v1")


async def test_select_missing_fields(tool):
    result = await tool.execute(action="select", selector="#sel", _session_id="s1")
    assert "오류" in result


async def test_close(tool, manager):
    result = await tool.execute(action="close", _session_id="s1")
    manager.browser_close.assert_awaited_once_with("s1")
    assert "브라우저" in result


async def test_unknown_action(tool):
    result = await tool.execute(action="fly", _session_id="s1")
    assert "오류" in result


async def test_default_session_id(tool, manager):
    await tool.execute(action="screenshot")
    manager.browser_screenshot.assert_awaited_once_with("default")
