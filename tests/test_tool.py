import pytest

from koclaw.core.tool import Tool, ToolRegistry


class EchoTool(Tool):
    name = "echo"
    description = "입력값을 그대로 반환합니다"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "반환할 메시지"},
        },
        "required": ["message"],
    }
    is_sandboxed = False

    async def execute(self, message: str) -> str:
        return message


class SandboxedTool(Tool):
    name = "sandboxed"
    description = "격리 실행이 필요한 tool"
    parameters = {"type": "object", "properties": {}, "required": []}
    is_sandboxed = True

    async def execute(self) -> str:
        return "sandboxed"


class TestTool:
    def test_tool_has_required_attributes(self):
        tool = EchoTool()
        assert tool.name == "echo"
        assert tool.description == "입력값을 그대로 반환합니다"
        assert tool.parameters is not None
        assert tool.is_sandboxed is False

    async def test_tool_execute(self):
        tool = EchoTool()
        result = await tool.execute(message="안녕")
        assert result == "안녕"

    def test_tool_schema(self):
        tool = EchoTool()
        schema = tool.schema()
        assert schema["name"] == "echo"
        assert schema["description"] == "입력값을 그대로 반환합니다"
        assert "parameters" in schema


class TestToolRegistry:
    def test_register_and_get_tool(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        assert registry.get("echo") is not None

    def test_get_schemas(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        schemas = registry.schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "echo"

    async def test_execute_tool(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        result = await registry.execute("echo", {"message": "테스트"})
        assert result == "테스트"

    async def test_execute_unknown_tool_raises(self):
        registry = ToolRegistry()
        with pytest.raises(KeyError):
            await registry.execute("unknown", {})

    def test_safe_tools(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(SandboxedTool())
        safe = registry.safe_tools()
        sandboxed = registry.sandboxed_tools()
        assert len(safe) == 1
        assert len(sandboxed) == 1

    def test_clone_contains_same_tools(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        cloned = registry.clone()
        assert cloned.get("echo") is not None

    def test_clone_is_independent(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        cloned = registry.clone()
        cloned.register(SandboxedTool())
        assert registry.get("sandboxed") is None
        assert cloned.get("sandboxed") is not None
