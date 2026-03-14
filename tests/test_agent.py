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

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        self.call_count += 1
        return next(self._responses)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestAgentDirectResponse:
    async def test_returns_llm_content_when_no_tool_calls(self):
        provider = CountingProvider([LLMResponse(content="안녕하세요!", tool_calls=[])])
        agent = Agent(provider=provider, tools=ToolRegistry())

        result = await agent.run("안녕")

        assert result == "안녕하세요!"

    async def test_user_message_included_in_llm_call(self):
        provider = CountingProvider([LLMResponse(content="응답", tool_calls=[])])
        agent = Agent(provider=provider, tools=ToolRegistry())

        await agent.run("테스트 메시지")

        # LLM이 정확히 1번 호출됨
        assert provider.call_count == 1


class TestAgentToolExecution:
    async def test_executes_tool_and_returns_final_response(self):
        tool_call = ToolCall(id="1", name="echo", arguments={"message": "tool 결과"})
        provider = CountingProvider(
            [
                LLMResponse(content=None, tool_calls=[tool_call]),
                LLMResponse(content="tool 결과를 받았습니다", tool_calls=[]),
            ]
        )
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

        provider = CountingProvider(
            [
                LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCall(id="1", name="slow", arguments={}),
                        ToolCall(id="2", name="fast", arguments={}),
                    ],
                ),
                LLMResponse(content="둘 다 완료", tool_calls=[]),
            ]
        )
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
        provider = CountingProvider(
            [
                LLMResponse(content=None, tool_calls=[tool_call]),
                LLMResponse(content="에러가 발생했네요", tool_calls=[]),
            ]
        )
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


class TestAgentToolStartCallback:
    async def test_on_tool_start_called_with_tool_name(self):
        """tool 실행 전 on_tool_start 콜백이 tool 이름과 함께 호출된다."""
        called_with = []

        async def on_tool_start(tool_name: str) -> None:
            called_with.append(tool_name)

        tool_call = ToolCall(id="1", name="echo", arguments={"message": "hi"})
        provider = CountingProvider(
            [
                LLMResponse(content=None, tool_calls=[tool_call]),
                LLMResponse(content="완료", tool_calls=[]),
            ]
        )
        registry = ToolRegistry()
        registry.register(EchoTool())
        agent = Agent(provider=provider, tools=registry, on_tool_start=on_tool_start)

        await agent.run("echo 실행")

        assert called_with == ["echo"]

    async def test_on_tool_start_not_required(self):
        """on_tool_start 없이도 정상 실행된다."""
        tool_call = ToolCall(id="1", name="echo", arguments={"message": "hi"})
        provider = CountingProvider(
            [
                LLMResponse(content=None, tool_calls=[tool_call]),
                LLMResponse(content="완료", tool_calls=[]),
            ]
        )
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
        provider = CountingProvider(
            [
                LLMResponse(content=None, tool_calls=[tool_call]),
                LLMResponse(content="완료", tool_calls=[]),
            ]
        )
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
            LLMResponse(
                content=None, tool_calls=[ToolCall(id="1", name="echo", arguments={"message": "a"})]
            ),
            LLMResponse(
                content=None, tool_calls=[ToolCall(id="2", name="echo", arguments={"message": "b"})]
            ),
            LLMResponse(
                content=None, tool_calls=[ToolCall(id="3", name="echo", arguments={"message": "c"})]
            ),
            LLMResponse(
                content=None, tool_calls=[ToolCall(id="4", name="echo", arguments={"message": "d"})]
            ),
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
        provider = CountingProvider(
            [
                LLMResponse(content="첫 번째 응답", tool_calls=[]),
                LLMResponse(content="두 번째 응답", tool_calls=[]),
            ]
        )
        agent = Agent(provider=provider, tools=ToolRegistry())

        await agent.run("첫 번째 메시지")
        await agent.run("두 번째 메시지")

        # 두 번째 호출 시 이전 대화가 포함되어야 함
        assert len(agent.messages) == 4  # user, assistant, user, assistant
