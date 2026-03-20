import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    thought_signature: bytes | None = None


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_provider_data: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse: ...


class FallbackProvider(LLMProvider):
    def __init__(self, providers: list[LLMProvider]):
        self._providers = providers

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        last_error = None
        for provider in self._providers:
            try:
                return await provider.complete(messages, tools)
            except Exception as e:
                logger.warning(
                    "[fallback] %s 실패 → 다음 provider로 전환: %s",
                    type(provider).__name__,
                    e,
                )
                last_error = e
        raise RuntimeError("모든 LLM provider가 실패했습니다") from last_error
