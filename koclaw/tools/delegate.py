import asyncio
import logging

from koclaw.core.agent import Agent
from koclaw.core.llm import LLMProvider
from koclaw.core.tool import Tool, ToolRegistry

logger = logging.getLogger(__name__)

_SUB_AGENT_MAX_TURNS = 20
_SUB_AGENT_TIMEOUT = 120.0


class DelegateTool(Tool):
    name = "delegate"
    description = (
        "독립적인 하위 태스크를 전문 서브 에이전트에게 위임합니다. "
        "복잡한 요청을 역할별로 분리하거나, 여러 태스크를 동시에 병렬 처리할 때 사용하세요. "
        "예: 여러 항목을 각각 리서치한 뒤 결과를 종합하거나, "
        "데이터 수집과 분석을 별도 에이전트에게 맡길 수 있습니다."
    )
    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "서브 에이전트에게 맡길 구체적인 태스크 설명. 독립적으로 실행 가능해야 합니다.",
            },
            "allowed_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "서브 에이전트가 사용할 tool 이름 목록. "
                    '예: ["web_search", "browse"]. '
                    "생략하면 delegate를 제외한 모든 tool을 사용합니다."
                ),
            },
        },
        "required": ["task"],
    }

    def __init__(self, provider: LLMProvider, registry: ToolRegistry) -> None:
        self._provider = provider
        self._registry = registry

    async def execute(self, task: str, allowed_tools: list[str] | None = None) -> str:
        sub_registry = ToolRegistry()

        if allowed_tools:
            missing = []
            for tool_name in allowed_tools:
                tool = self._registry.get(tool_name)
                if tool:
                    sub_registry.register(tool)
                else:
                    missing.append(tool_name)
            if missing:
                logger.warning("[delegate] 존재하지 않는 tool 무시됨: %s", missing)
        else:
            # delegate 자신은 제외 — 무한 재귀 방지
            for tool_name, tool in self._registry._tools.items():
                if tool_name != "delegate":
                    sub_registry.register(tool)

        system_prompt = (
            "당신은 다음 태스크만 처리하는 전문 에이전트입니다. "
            "주어진 태스크를 완수하고 결과를 간결하게 반환하세요.\n\n"
            f"태스크: {task}"
        )

        sub_agent = Agent(
            provider=self._provider,
            tools=sub_registry,
            system_prompt=system_prompt,
            max_turns=_SUB_AGENT_MAX_TURNS,
        )

        logger.info("[delegate] 서브 에이전트 시작: %r (tools=%s)", task[:60], allowed_tools)
        try:
            result = await asyncio.wait_for(sub_agent.run(task), timeout=_SUB_AGENT_TIMEOUT)
            logger.info("[delegate] 서브 에이전트 완료: %r", str(result)[:100])
            return result
        except asyncio.TimeoutError:
            logger.warning("[delegate] 서브 에이전트 타임아웃: %r", task[:60])
            return f"서브 에이전트가 시간 초과되었습니다 ({int(_SUB_AGENT_TIMEOUT)}초). 태스크를 더 작게 나눠 주세요."
        except Exception as e:
            logger.error("[delegate] 서브 에이전트 오류: %s", e)
            return f"서브 에이전트 실행 중 오류가 발생했습니다: {e}"
