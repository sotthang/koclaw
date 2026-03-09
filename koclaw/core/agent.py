import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from koclaw.core.llm import LLMProvider, LLMResponse, ToolCall
from koclaw.core.tool import ToolRegistry

if TYPE_CHECKING:
    from koclaw.core.sandbox import SandboxManager

logger = logging.getLogger(__name__)
MAX_TURNS_DEFAULT = 20
_MAX_SAME_TOOL_CALLS = 3


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry,
        max_turns: int = MAX_TURNS_DEFAULT,
        system_prompt: str | None = None,
        sandbox: "SandboxManager | None" = None,
        session_id: str | None = None,
        parent_session_id: str | None = None,
        on_tool_start: Callable[[str], Awaitable[None]] | None = None,
    ):
        self._provider = provider
        self._tools = tools
        self._max_turns = max_turns
        self._system_prompt = system_prompt
        self._sandbox = sandbox
        self._session_id = session_id
        self._parent_session_id = parent_session_id
        self._on_tool_start = on_tool_start
        self.messages: list[dict] = []

    async def run(self, user_message: str | list) -> str:
        self.messages.append({"role": "user", "content": user_message})

        tool_call_counts: dict[str, int] = {}

        for _ in range(self._max_turns):
            messages = self.messages
            if self._system_prompt:
                messages = [{"role": "system", "content": self._system_prompt}] + messages

            response = await self._provider.complete(
                messages=messages,
                tools=self._tools.schemas() or None,
            )

            if not response.has_tool_calls:
                self.messages.append({"role": "assistant", "content": response.content})
                return response.content

            # 동일 tool+args 반복 호출 감지 (무한루프 방어)
            for tc in response.tool_calls:
                key = f"{tc.name}:{json.dumps(tc.arguments, sort_keys=True)}"
                tool_call_counts[key] = tool_call_counts.get(key, 0) + 1
                if tool_call_counts[key] > _MAX_SAME_TOOL_CALLS:
                    error_msg = (
                        f"오류: '{tc.name}' tool이 동일한 인자로 {_MAX_SAME_TOOL_CALLS}회 이상 "
                        f"반복 호출되었습니다. 무한 루프로 판단하여 중단합니다."
                    )
                    logger.warning("[agent] loop detected: %s", key)
                    return error_msg

            self.messages.append(self._response_to_message(response))
            tool_results = await self._execute_tools_parallel(response.tool_calls)
            self.messages.extend(tool_results)

        raise RuntimeError(f"최대 실행 횟수({self._max_turns})를 초과했습니다")

    async def _run_tool(self, tool_call: ToolCall) -> str:
        tool = self._tools.get(tool_call.name)
        if tool is None:
            raise KeyError(f"Tool '{tool_call.name}' not found")

        if tool.is_sandboxed:
            if self._sandbox is None:
                return "오류: 이 도구는 샌드박스 환경이 필요합니다. 관리자에게 문의하세요."
            return await self._sandbox.execute(
                self._session_id or "default",
                tool_call.name,
                tool_call.arguments,
                parent_session_id=self._parent_session_id,
            )
        return await self._tools.execute(tool_call.name, tool_call.arguments)

    async def _execute_tools_parallel(self, tool_calls: list[ToolCall]) -> list[dict]:
        async def execute_one(tool_call: ToolCall) -> dict:
            logger.info("[tool] %s args=%r", tool_call.name, tool_call.arguments)
            if self._on_tool_start is not None:
                try:
                    await self._on_tool_start(tool_call.name)
                except Exception:
                    pass
            try:
                result = await self._run_tool(tool_call)
                logger.info("[tool] %s → %r", tool_call.name, str(result)[:200])
            except Exception as e:
                logger.error("[tool] %s error: %s", tool_call.name, e)
                result = f"Error: {e}"
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            }

        return list(await asyncio.gather(*[execute_one(tc) for tc in tool_calls]))

    def _response_to_message(self, response: LLMResponse) -> dict:
        return {
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "thought_signature": tc.thought_signature,
                }
                for tc in response.tool_calls
            ],
            "_raw_provider_data": response.raw_provider_data,
        }
