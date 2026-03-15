import asyncio

from koclaw.core.llm import LLMProvider, LLMResponse, ToolCall
from koclaw.core.tool import Tool, ToolRegistry
from koclaw.tools.delegate import DelegateTool

# ── Fakes ──────────────────────────────────────────────────────────────────


class EchoTool(Tool):
    name = "echo"
    description = "입력을 그대로 반환"
    parameters = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    async def execute(self, message: str) -> str:
        return message


class FixedProvider(LLMProvider):
    """항상 같은 응답을 반환하는 fake provider"""

    def __init__(self, responses: list[LLMResponse]):
        self._iter = iter(responses)

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        return next(self._iter)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestDelegateToolBasic:
    async def test_returns_sub_agent_result(self):
        """서브 에이전트 결과를 그대로 반환한다."""
        provider = FixedProvider([LLMResponse(content="서브 에이전트 결과", tool_calls=[])])
        registry = ToolRegistry()
        tool = DelegateTool(provider=provider, registry=registry)

        result = await tool.execute(task="테스트 태스크")

        assert result == "서브 에이전트 결과"

    async def test_sub_agent_can_use_registered_tools(self):
        """서브 에이전트가 allowed_tools에 포함된 tool을 실행할 수 있다."""
        tool_call = ToolCall(id="1", name="echo", arguments={"message": "도구 실행됨"})
        provider = FixedProvider(
            [
                LLMResponse(content=None, tool_calls=[tool_call]),
                LLMResponse(content="완료", tool_calls=[]),
            ]
        )
        registry = ToolRegistry()
        registry.register(EchoTool())
        tool = DelegateTool(provider=provider, registry=registry)

        result = await tool.execute(task="echo 실행해줘", allowed_tools=["echo"])

        assert result == "완료"

    async def test_allowed_tools_filters_registry(self):
        """allowed_tools에 없는 tool은 서브 에이전트가 사용할 수 없다."""
        captured_tools: list[list[dict] | None] = []

        class CapturingProvider(LLMProvider):
            async def complete(self, messages, tools=None):
                captured_tools.append(tools)
                return LLMResponse(content="완료", tool_calls=[])

        registry = ToolRegistry()
        registry.register(EchoTool())

        class AnotherTool(Tool):
            name = "another"
            description = "다른 tool"
            parameters = {"type": "object", "properties": {}, "required": []}

            async def execute(self) -> str:
                return "another"

        registry.register(AnotherTool())
        tool = DelegateTool(provider=CapturingProvider(), registry=registry)

        await tool.execute(task="echo만 써줘", allowed_tools=["echo"])

        tool_names = [t["name"] for t in (captured_tools[0] or [])]
        assert "echo" in tool_names
        assert "another" not in tool_names

    async def test_no_allowed_tools_excludes_delegate(self):
        """allowed_tools 미지정 시 delegate 자신은 서브 에이전트에게 전달되지 않는다 (무한 재귀 방지)."""
        captured_tools: list[list[dict] | None] = []

        class CapturingProvider(LLMProvider):
            async def complete(self, messages, tools=None):
                captured_tools.append(tools)
                return LLMResponse(content="완료", tool_calls=[])

        registry = ToolRegistry()
        registry.register(EchoTool())

        delegate_tool = DelegateTool(provider=CapturingProvider(), registry=registry)
        registry.register(delegate_tool)

        await delegate_tool.execute(task="뭔가 해줘")

        tool_names = [t["name"] for t in (captured_tools[0] or [])]
        assert "delegate" not in tool_names
        assert "echo" in tool_names


class TestDelegateToolErrorHandling:
    async def test_timeout_returns_error_message(self):
        """서브 에이전트가 타임아웃되면 에러 메시지를 반환한다."""
        import koclaw.tools.delegate as delegate_module

        original_timeout = delegate_module._SUB_AGENT_TIMEOUT

        class SlowProvider(LLMProvider):
            async def complete(self, messages, tools=None):
                await asyncio.sleep(10)
                return LLMResponse(content="늦은 응답", tool_calls=[])

        delegate_module._SUB_AGENT_TIMEOUT = 0.01
        try:
            registry = ToolRegistry()
            tool = DelegateTool(provider=SlowProvider(), registry=registry)
            result = await tool.execute(task="느린 태스크")
        finally:
            delegate_module._SUB_AGENT_TIMEOUT = original_timeout

        assert "시간 초과" in result

    async def test_missing_tool_in_allowed_tools_is_ignored(self):
        """allowed_tools에 존재하지 않는 tool 이름이 포함되어도 오류 없이 실행된다."""
        provider = FixedProvider([LLMResponse(content="완료", tool_calls=[])])
        registry = ToolRegistry()
        registry.register(EchoTool())
        tool = DelegateTool(provider=provider, registry=registry)

        result = await tool.execute(task="테스트", allowed_tools=["echo", "nonexistent_tool"])

        assert result == "완료"

    async def test_provider_exception_returns_error_message(self):
        """provider에서 예외가 발생하면 에러 메시지를 반환한다."""

        class FailingProvider(LLMProvider):
            async def complete(self, messages, tools=None):
                raise RuntimeError("LLM 연결 오류")

        registry = ToolRegistry()
        tool = DelegateTool(provider=FailingProvider(), registry=registry)

        result = await tool.execute(task="실패 태스크")

        assert "오류" in result


class TestDelegateToolParallel:
    async def test_multiple_delegates_run_concurrently(self):
        """여러 delegate 태스크가 병렬로 실행될 수 있다."""
        execution_log: list[str] = []

        class TrackingProvider(LLMProvider):
            def __init__(self, label: str, delay: float):
                self._label = label
                self._delay = delay

            async def complete(self, messages, tools=None):
                await asyncio.sleep(self._delay)
                execution_log.append(self._label)
                return LLMResponse(content=f"{self._label} 완료", tool_calls=[])

        registry = ToolRegistry()
        tool_a = DelegateTool(provider=TrackingProvider("A", 0.05), registry=registry)
        tool_b = DelegateTool(provider=TrackingProvider("B", 0.01), registry=registry)

        results = await asyncio.gather(
            tool_a.execute(task="태스크 A"),
            tool_b.execute(task="태스크 B"),
        )

        # B가 더 빠르므로 먼저 완료
        assert execution_log == ["B", "A"]
        assert "A 완료" in results[0]
        assert "B 완료" in results[1]
