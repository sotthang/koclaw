
import pytest

from koclaw.core.llm import FallbackProvider, LLMProvider, LLMResponse, ToolCall


class FakeLLMProvider(LLMProvider):
    def __init__(self, response: LLMResponse):
        self._response = response

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        return self._response


class FailingProvider(LLMProvider):
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        raise RuntimeError("provider unavailable")


class TestLLMResponse:
    def test_response_with_content(self):
        response = LLMResponse(content="안녕하세요", tool_calls=[])
        assert response.content == "안녕하세요"
        assert response.tool_calls == []
        assert response.has_tool_calls is False

    def test_response_with_tool_calls(self):
        tool_call = ToolCall(id="1", name="search", arguments={"query": "날씨"})
        response = LLMResponse(content=None, tool_calls=[tool_call])
        assert response.has_tool_calls is True
        assert response.tool_calls[0].name == "search"

    def test_tool_call_attributes(self):
        tool_call = ToolCall(id="abc", name="echo", arguments={"message": "hi"})
        assert tool_call.id == "abc"
        assert tool_call.name == "echo"
        assert tool_call.arguments == {"message": "hi"}


class TestFallbackProvider:
    async def test_uses_primary_provider(self):
        expected = LLMResponse(content="응답", tool_calls=[])
        primary = FakeLLMProvider(expected)
        fallback = FallbackProvider([primary])

        result = await fallback.complete([{"role": "user", "content": "hi"}])
        assert result.content == "응답"

    async def test_falls_back_on_failure(self):
        fallback_response = LLMResponse(content="폴백 응답", tool_calls=[])
        fallback = FallbackProvider([
            FailingProvider(),
            FakeLLMProvider(fallback_response),
        ])

        result = await fallback.complete([{"role": "user", "content": "hi"}])
        assert result.content == "폴백 응답"

    async def test_raises_when_all_providers_fail(self):
        fallback = FallbackProvider([FailingProvider(), FailingProvider()])

        with pytest.raises(RuntimeError, match="모든 LLM provider가 실패했습니다"):
            await fallback.complete([{"role": "user", "content": "hi"}])
