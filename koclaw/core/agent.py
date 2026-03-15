import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from koclaw.core.llm import LLMProvider, LLMResponse, ToolCall
from koclaw.core.tool import ToolRegistry

logger = logging.getLogger(__name__)
MAX_TURNS_DEFAULT = 20
_MAX_SAME_TOOL_CALLS = 5


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry,
        max_turns: int = MAX_TURNS_DEFAULT,
        system_prompt: str | None = None,
        session_id: str | None = None,
        on_tool_start: Callable[[str], Awaitable[None]] | None = None,
    ):
        self._provider = provider
        self._tools = tools
        self._max_turns = max_turns
        self._system_prompt = system_prompt
        self._session_id = session_id
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
                # screenshot은 상태 확인용으로 반복 호출이 자연스러우므로 제외
                if tc.name == "computer_use" and tc.arguments.get("action") == "screenshot":
                    continue
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

        args = tool_call.arguments
        if getattr(tool, "needs_session_context", False):
            args = {**args, "_session_id": self._session_id or "default"}
        return await self._tools.execute(tool_call.name, args)

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
            # screenshot 결과에 "[화면 크기: WxH]\n" prefix가 붙을 수 있음
            # LLM에는 순수 base64만 전달하고, 해상도 정보는 별도 보존
            image_b64 = result
            screen_size_hint = ""
            if (
                tool_call.name == "computer_use"
                and tool_call.arguments.get("action") == "screenshot"
                and isinstance(result, str)
                and result.startswith("[화면 크기:")
                and "\n" in result
            ):
                screen_size_hint, image_b64 = result.split("\n", 1)

            is_screenshot = (
                tool_call.name == "computer_use"
                and tool_call.arguments.get("action") == "screenshot"
                and isinstance(result, str)
                and not image_b64.startswith("스크린샷 실패")
                and not image_b64.startswith("Error")
            )
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": image_b64 if is_screenshot else result,
                "_is_image": is_screenshot,
                "_screen_size_hint": screen_size_hint,
            }

        # computer_use는 클릭→타이핑→키입력 순서가 중요하므로 순차 실행
        if any(tc.name == "computer_use" for tc in tool_calls):
            results = []
            for tc in tool_calls:
                results.append(await execute_one(tc))
            return results

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
