import json
from unittest.mock import AsyncMock, MagicMock, patch

from koclaw.core.mcp_loader import MCPServerManager, MCPToolWrapper, load_mcp_servers
from koclaw.core.tool import ToolRegistry

# ── Fakes ──────────────────────────────────────────────────────────────────


def _make_mcp_tool(name: str, description: str = "설명", schema: dict | None = None):
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.inputSchema = schema or {"type": "object", "properties": {}, "required": []}
    return tool


def _make_text_content(text: str):
    content = MagicMock()
    content.text = text
    del content.data  # text only — data 속성 없음
    return content


def _make_session(tools: list, call_result_text: str = "결과", is_error: bool = False):
    session = AsyncMock()
    list_result = MagicMock()
    list_result.tools = tools
    session.list_tools.return_value = list_result
    session.initialize = AsyncMock()

    call_result = MagicMock()
    call_result.isError = is_error
    call_result.content = [_make_text_content(call_result_text)]
    session.call_tool.return_value = call_result
    return session


# ── MCPToolWrapper Tests ────────────────────────────────────────────────────


class TestMCPToolWrapper:
    def test_name_and_description_set_from_mcp_tool(self):
        mcp_tool = _make_mcp_tool("read_file", "파일 읽기")
        session = _make_session([])
        wrapper = MCPToolWrapper(session, mcp_tool, "filesystem")

        assert wrapper.name == "read_file"
        assert wrapper.description == "파일 읽기"

    def test_uses_server_name_as_fallback_description(self):
        mcp_tool = _make_mcp_tool("do_thing", description=None)
        mcp_tool.description = None
        session = _make_session([])
        wrapper = MCPToolWrapper(session, mcp_tool, "my-server")

        assert "my-server" in wrapper.description

    async def test_execute_returns_text_content(self):
        mcp_tool = _make_mcp_tool("echo")
        session = _make_session([mcp_tool], call_result_text="에코 결과")
        wrapper = MCPToolWrapper(session, mcp_tool, "test")

        result = await wrapper.execute(message="hello")

        session.call_tool.assert_awaited_once_with("echo", {"message": "hello"})
        assert result == "에코 결과"

    async def test_execute_returns_error_message_on_mcp_error(self):
        mcp_tool = _make_mcp_tool("fail_tool")
        session = _make_session([mcp_tool], call_result_text="서버 오류", is_error=True)
        wrapper = MCPToolWrapper(session, mcp_tool, "test")

        result = await wrapper.execute()

        assert "MCP 오류" in result
        assert "서버 오류" in result

    async def test_execute_returns_error_message_on_exception(self):
        mcp_tool = _make_mcp_tool("broken")
        session = AsyncMock()
        session.call_tool.side_effect = RuntimeError("연결 끊김")
        wrapper = MCPToolWrapper(session, mcp_tool, "test")

        result = await wrapper.execute()

        assert "호출 실패" in result

    async def test_execute_multiple_content_blocks_joined(self):
        mcp_tool = _make_mcp_tool("multi")
        session = AsyncMock()
        session.initialize = AsyncMock()

        call_result = MagicMock()
        call_result.isError = False
        call_result.content = [
            _make_text_content("첫 번째"),
            _make_text_content("두 번째"),
        ]
        session.call_tool.return_value = call_result
        wrapper = MCPToolWrapper(session, mcp_tool, "test")

        result = await wrapper.execute()

        assert "첫 번째" in result
        assert "두 번째" in result


# ── MCPServerManager Tests ──────────────────────────────────────────────────


class TestMCPServerManagerRegisterAll:
    def test_registers_tools_into_registry(self):
        manager = MCPServerManager()
        mcp_tool = _make_mcp_tool("list_files")
        session = _make_session([mcp_tool])
        manager._tools.append(MCPToolWrapper(session, mcp_tool, "fs"))

        registry = ToolRegistry()
        manager.register_all(registry)

        assert registry.get("list_files") is not None

    def test_tool_count_reflects_connected_tools(self):
        manager = MCPServerManager()
        for i in range(3):
            t = _make_mcp_tool(f"tool_{i}")
            manager._tools.append(MCPToolWrapper(_make_session([]), t, "srv"))

        assert manager.tool_count == 3


# ── load_mcp_servers Tests ──────────────────────────────────────────────────


class TestLoadMcpServers:
    async def test_returns_none_when_config_file_missing(self, tmp_path):
        registry = ToolRegistry()
        result = await load_mcp_servers(tmp_path / "nonexistent.json", registry)

        assert result is None

    async def test_returns_none_on_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ invalid json }")

        registry = ToolRegistry()
        result = await load_mcp_servers(bad_file, registry)

        assert result is None

    async def test_returns_none_for_empty_config(self, tmp_path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text("[]")

        registry = ToolRegistry()
        result = await load_mcp_servers(config_file, registry)

        assert result is None

    async def test_registers_tools_from_sse_server(self, tmp_path):
        config = [{"name": "test-srv", "transport": "sse", "url": "http://localhost:9999/sse"}]
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps(config))

        mcp_tool = _make_mcp_tool("search")
        session = _make_session([mcp_tool])

        with (
            patch("mcp.client.sse.sse_client") as mock_sse,
            patch("mcp.ClientSession") as mock_session_cls,
        ):
            mock_sse.return_value.__aenter__ = AsyncMock(return_value=("read", "write"))
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            registry = ToolRegistry()
            manager = await load_mcp_servers(config_file, registry)

        assert manager is not None
        assert registry.get("search") is not None

    async def test_connect_failure_does_not_crash_other_servers(self, tmp_path):
        config = [
            {"name": "bad-srv", "transport": "sse", "url": "http://bad-host/sse"},
            {"name": "good-srv", "transport": "sse", "url": "http://good-host/sse"},
        ]
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps(config))

        good_tool = _make_mcp_tool("good_tool")
        good_session = _make_session([good_tool])

        call_count = 0

        class FakeSseClient:
            def __init__(self, url, headers=None):
                self._url = url

            async def __aenter__(self):
                nonlocal call_count
                call_count += 1
                if "bad" in self._url:
                    raise ConnectionError("연결 실패")
                return ("read", "write")

            async def __aexit__(self, *args):
                return False

        class FakeSessionCtx:
            async def __aenter__(self):
                return good_session

            async def __aexit__(self, *args):
                return False

        with (
            patch("mcp.client.sse.sse_client", side_effect=FakeSseClient),
            patch("mcp.ClientSession", return_value=FakeSessionCtx()),
        ):
            registry = ToolRegistry()
            await load_mcp_servers(config_file, registry)

        # good_tool은 등록됨
        assert registry.get("good_tool") is not None
