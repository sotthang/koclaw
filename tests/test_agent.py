from unittest.mock import AsyncMock

import pytest

from koclaw.core.agent import Agent
from koclaw.core.llm import LLMProvider, LLMResponse, ToolCall
from koclaw.core.tool import Tool, ToolRegistry

# ── Fakes ──────────────────────────────────────────────────────────────────

class EchoTool(Tool):
    name = "echo"
    description = "메시지를 그대로 반환"
    parameters = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    is_sandboxed = False

    async def execute(self, message: str) -> str:
        return message


class CountingProvider(LLMProvider):
    """호출 횟수를 추적하고 순서대로 응답을 반환하는 fake provider"""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = iter(responses)
        self.call_count = 0

    async def complete(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        self.call_count += 1
        return next(self._responses)


# ── Tests ──────────────────────────────────────────────────────────────────

class TestAgentDirectResponse:
    async def test_returns_llm_content_when_no_tool_calls(self):
        provider = CountingProvider([
            LLMResponse(content="안녕하세요!", tool_calls=[])
        ])
        agent = Agent(provider=provider, tools=ToolRegistry())

        result = await agent.run("안녕")

        assert result == "안녕하세요!"

    async def test_user_message_included_in_llm_call(self):
        provider = CountingProvider([
            LLMResponse(content="응답", tool_calls=[])
        ])
        agent = Agent(provider=provider, tools=ToolRegistry())

        await agent.run("테스트 메시지")

        # LLM이 정확히 1번 호출됨
        assert provider.call_count == 1


class TestAgentToolExecution:
    async def test_executes_tool_and_returns_final_response(self):
        tool_call = ToolCall(id="1", name="echo", arguments={"message": "tool 결과"})
        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[tool_call]),
            LLMResponse(content="tool 결과를 받았습니다", tool_calls=[]),
        ])
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = Agent(provider=provider, tools=registry)

        result = await agent.run("echo 실행해줘")

        assert result == "tool 결과를 받았습니다"
        assert provider.call_count == 2

    async def test_executes_multiple_tool_calls_in_parallel(self):
        import asyncio

        execution_order = []

        class SlowTool(Tool):
            name = "slow"
            description = "느린 tool"
            parameters = {"type": "object", "properties": {}, "required": []}
            is_sandboxed = False

            async def execute(self) -> str:
                await asyncio.sleep(0.05)
                execution_order.append("slow")
                return "slow done"

        class FastTool(Tool):
            name = "fast"
            description = "빠른 tool"
            parameters = {"type": "object", "properties": {}, "required": []}
            is_sandboxed = False

            async def execute(self) -> str:
                execution_order.append("fast")
                return "fast done"

        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[
                ToolCall(id="1", name="slow", arguments={}),
                ToolCall(id="2", name="fast", arguments={}),
            ]),
            LLMResponse(content="둘 다 완료", tool_calls=[]),
        ])
        registry = ToolRegistry()
        registry.register(SlowTool())
        registry.register(FastTool())
        agent = Agent(provider=provider, tools=registry)

        result = await agent.run("둘 다 실행해줘")

        assert result == "둘 다 완료"
        # 병렬 실행이면 fast가 slow보다 먼저 완료됨
        assert execution_order == ["fast", "slow"]


class TestAgentErrorHandling:
    async def test_tool_error_continues_loop(self):
        class FailingTool(Tool):
            name = "failing"
            description = "항상 실패하는 tool"
            parameters = {"type": "object", "properties": {}, "required": []}
            is_sandboxed = False

            async def execute(self) -> str:
                raise RuntimeError("tool 실패!")

        tool_call = ToolCall(id="1", name="failing", arguments={})
        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[tool_call]),
            LLMResponse(content="에러가 발생했네요", tool_calls=[]),
        ])
        registry = ToolRegistry()
        registry.register(FailingTool())
        agent = Agent(provider=provider, tools=registry)

        result = await agent.run("실패하는 tool 실행해줘")

        # 에러가 나도 LLM에 에러 내용을 전달하고 계속 진행
        assert result == "에러가 발생했네요"

    async def test_max_turns_raises(self):
        # tool call을 무한히 반환하는 provider
        tool_call = ToolCall(id="1", name="echo", arguments={"message": "hi"})
        responses = [LLMResponse(content=None, tool_calls=[tool_call])] * 20
        provider = CountingProvider(responses)
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = Agent(provider=provider, tools=registry, max_turns=3)

        with pytest.raises(RuntimeError, match="최대 실행 횟수"):
            await agent.run("무한루프")


class TestAgentSystemPrompt:
    async def test_system_prompt_prepended_to_messages(self):
        received = []

        class CapturingProvider(LLMProvider):
            async def complete(self, messages, tools=None):
                received.append(messages)
                return LLMResponse(content="응답", tool_calls=[])

        agent = Agent(
            provider=CapturingProvider(),
            tools=ToolRegistry(),
            system_prompt="당신은 한국어 AI입니다.",
        )
        await agent.run("안녕")

        assert received[0][0]["role"] == "system"
        assert received[0][0]["content"] == "당신은 한국어 AI입니다."
        assert received[0][1]["role"] == "user"

    async def test_system_prompt_not_stored_in_history(self):
        provider = CountingProvider([LLMResponse(content="응답", tool_calls=[])])
        agent = Agent(
            provider=provider,
            tools=ToolRegistry(),
            system_prompt="시스템 안내",
        )
        await agent.run("안녕")

        roles = [m["role"] for m in agent.messages]
        assert "system" not in roles


class TestAgentSandboxRouting:
    """is_sandboxed=True 인 tool은 SandboxManager를 통해 실행되어야 한다."""

    def _make_sandboxed_tool(self, result: str = "sandbox 결과") -> Tool:
        class SandboxedTool(Tool):
            name = "secure_op"
            description = "격리 실행이 필요한 tool"
            parameters = {"type": "object", "properties": {}, "required": []}
            is_sandboxed = True

            async def execute(self) -> str:  # 직접 호출되면 안 됨
                return "직접 실행됨 (오류)"

        return SandboxedTool()

    async def test_sandboxed_tool_uses_sandbox_manager(self):
        """is_sandboxed tool 실행 시 sandbox.execute()가 호출된다."""
        tool = self._make_sandboxed_tool()
        registry = ToolRegistry()
        registry.register(tool)

        mock_sandbox = AsyncMock()
        mock_sandbox.execute = AsyncMock(return_value="sandbox 결과")

        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[
                ToolCall(id="1", name="secure_op", arguments={})
            ]),
            LLMResponse(content="완료", tool_calls=[]),
        ])
        agent = Agent(provider=provider, tools=registry, sandbox=mock_sandbox, session_id="sess-x")

        await agent.run("격리 실행해줘")

        mock_sandbox.execute.assert_called_once_with("sess-x", "secure_op", {}, parent_session_id=None)

    async def test_sandboxed_tool_forwards_parent_session_id(self):
        """parent_session_id가 있으면 sandbox.execute에 전달된다."""
        tool = self._make_sandboxed_tool()
        registry = ToolRegistry()
        registry.register(tool)

        mock_sandbox = AsyncMock()
        mock_sandbox.execute = AsyncMock(return_value="sandbox 결과")

        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[
                ToolCall(id="1", name="secure_op", arguments={})
            ]),
            LLMResponse(content="완료", tool_calls=[]),
        ])
        agent = Agent(
            provider=provider, tools=registry, sandbox=mock_sandbox,
            session_id="slack:C001:9999.0", parent_session_id="slack:C001",
        )

        await agent.run("격리 실행해줘")

        mock_sandbox.execute.assert_called_once_with(
            "slack:C001:9999.0", "secure_op", {}, parent_session_id="slack:C001"
        )

    async def test_safe_tool_does_not_use_sandbox(self):
        """is_sandboxed=False tool은 sandbox를 거치지 않고 직접 실행된다."""
        registry = ToolRegistry()
        registry.register(EchoTool())

        mock_sandbox = AsyncMock()
        mock_sandbox.execute = AsyncMock()

        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[
                ToolCall(id="1", name="echo", arguments={"message": "hi"})
            ]),
            LLMResponse(content="완료", tool_calls=[]),
        ])
        agent = Agent(provider=provider, tools=registry, sandbox=mock_sandbox, session_id="sess-y")

        await agent.run("직접 실행해줘")

        mock_sandbox.execute.assert_not_called()


class TestAgentSandboxMissing:
    """sandbox=None 일 때 sandboxed tool은 실행되지 않아야 한다."""

    def _make_sandboxed_tool(self) -> Tool:
        class SandboxedTool(Tool):
            name = "secure_op"
            description = "격리 실행이 필요한 tool"
            parameters = {"type": "object", "properties": {}, "required": []}
            is_sandboxed = True

            async def execute(self) -> str:
                return "직접 실행됨 (오류)"

        return SandboxedTool()

    async def test_sandboxed_tool_without_sandbox_returns_error(self):
        """sandbox가 없을 때 sandboxed tool 호출 시 에러 문자열을 반환한다."""
        tool = self._make_sandboxed_tool()
        registry = ToolRegistry()
        registry.register(tool)

        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[
                ToolCall(id="1", name="secure_op", arguments={})
            ]),
            LLMResponse(content="오류 처리됨", tool_calls=[]),
        ])
        agent = Agent(provider=provider, tools=registry, session_id="sess-z")

        await agent.run("격리 실행해줘")

        tool_result_msg = agent.messages[2]
        assert "오류" in tool_result_msg["content"] or "sandbox" in tool_result_msg["content"].lower()

    async def test_sandboxed_tool_does_not_execute_directly_without_sandbox(self):
        """sandbox 없으면 sandboxed tool의 execute()가 직접 호출되지 않는다."""
        executed = []

        class TrackingTool(Tool):
            name = "track_op"
            description = "추적용 tool"
            parameters = {"type": "object", "properties": {}, "required": []}
            is_sandboxed = True

            async def execute(self) -> str:
                executed.append(True)
                return "직접 실행됨"

        registry = ToolRegistry()
        registry.register(TrackingTool())

        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[
                ToolCall(id="1", name="track_op", arguments={})
            ]),
            LLMResponse(content="완료", tool_calls=[]),
        ])
        agent = Agent(provider=provider, tools=registry)

        await agent.run("실행해줘")

        assert executed == [], "sandboxed tool이 직접 실행되면 안 됨"


class TestAgentToolStartCallback:
    async def test_on_tool_start_called_with_tool_name(self):
        """tool 실행 전 on_tool_start 콜백이 tool 이름과 함께 호출된다."""
        called_with = []

        async def on_tool_start(tool_name: str) -> None:
            called_with.append(tool_name)

        tool_call = ToolCall(id="1", name="echo", arguments={"message": "hi"})
        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[tool_call]),
            LLMResponse(content="완료", tool_calls=[]),
        ])
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = Agent(provider=provider, tools=registry, on_tool_start=on_tool_start)

        await agent.run("echo 실행")

        assert called_with == ["echo"]

    async def test_on_tool_start_not_required(self):
        """on_tool_start 없이도 정상 실행된다."""
        tool_call = ToolCall(id="1", name="echo", arguments={"message": "hi"})
        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[tool_call]),
            LLMResponse(content="완료", tool_calls=[]),
        ])
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = Agent(provider=provider, tools=registry)

        result = await agent.run("echo 실행")

        assert result == "완료"

    async def test_on_tool_start_error_does_not_stop_execution(self):
        """콜백에서 예외가 발생해도 tool 실행은 계속된다."""
        async def failing_callback(tool_name: str) -> None:
            raise RuntimeError("콜백 오류")

        tool_call = ToolCall(id="1", name="echo", arguments={"message": "hi"})
        provider = CountingProvider([
            LLMResponse(content=None, tool_calls=[tool_call]),
            LLMResponse(content="완료", tool_calls=[]),
        ])
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = Agent(provider=provider, tools=registry, on_tool_start=failing_callback)

        result = await agent.run("echo 실행")

        assert result == "완료"


class TestAgentLoopDetection:
    async def test_returns_error_when_same_tool_and_args_repeated(self):
        """동일한 tool+args가 반복 호출되면 에러 메시지를 반환하고 중단한다."""
        tool_call = ToolCall(id="1", name="echo", arguments={"message": "hi"})
        responses = [LLMResponse(content=None, tool_calls=[tool_call])] * 20
        provider = CountingProvider(responses)
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = Agent(provider=provider, tools=registry, max_turns=20)

        result = await agent.run("루프 테스트")

        assert "반복" in result or "루프" in result or "중단" in result

    async def test_different_args_do_not_trigger_loop_detection(self):
        """같은 tool이라도 args가 다르면 루프로 감지하지 않는다."""
        responses = [
            LLMResponse(content=None, tool_calls=[ToolCall(id="1", name="echo", arguments={"message": "a"})]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="2", name="echo", arguments={"message": "b"})]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="3", name="echo", arguments={"message": "c"})]),
            LLMResponse(content=None, tool_calls=[ToolCall(id="4", name="echo", arguments={"message": "d"})]),
            LLMResponse(content="완료", tool_calls=[]),
        ]
        provider = CountingProvider(responses)
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = Agent(provider=provider, tools=registry, max_turns=20)

        result = await agent.run("다른 인자 테스트")

        assert result == "완료"

    async def test_loop_detected_before_max_turns(self):
        """루프 감지는 max_turns보다 먼저 중단시킨다."""
        tool_call = ToolCall(id="1", name="echo", arguments={"message": "same"})
        responses = [LLMResponse(content=None, tool_calls=[tool_call])] * 20
        provider = CountingProvider(responses)
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = Agent(provider=provider, tools=registry, max_turns=20)

        await agent.run("루프 테스트")

        # max_turns(20)보다 훨씬 적은 횟수에서 중단되어야 함
        assert provider.call_count < 10


class TestAgentHistory:
    async def test_maintains_conversation_history(self):
        provider = CountingProvider([
            LLMResponse(content="첫 번째 응답", tool_calls=[]),
            LLMResponse(content="두 번째 응답", tool_calls=[]),
        ])
        agent = Agent(provider=provider, tools=ToolRegistry())

        await agent.run("첫 번째 메시지")
        await agent.run("두 번째 메시지")

        # 두 번째 호출 시 이전 대화가 포함되어야 함
        assert len(agent.messages) == 4  # user, assistant, user, assistant
