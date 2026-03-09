import anthropic

from koclaw.core.llm import LLMProvider, LLMResponse, ToolCall

DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        system, converted = self._convert_messages(messages)
        kwargs = dict(model=self._model, max_tokens=4096, messages=converted)
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [self._to_claude_tool(t) for t in tools]

        response = await self._client.messages.create(**kwargs)
        return self._parse_response(response)

    def _convert_messages(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        system = None
        converted = []
        for msg in messages:
            role = msg["role"]
            if role == "system":
                system = msg["content"]
            elif role == "assistant" and "tool_calls" in msg:
                content = []
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["arguments"],
                    })
                converted.append({"role": "assistant", "content": content})
            elif role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": msg["content"],
                    }],
                })
            else:
                content = msg["content"]
                if isinstance(content, list):
                    content = [self._convert_content_part(p) for p in content]
                converted.append({"role": role, "content": content})
        return system, converted

    def _convert_content_part(self, part: dict) -> dict:
        if part.get("type") == "image":
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": part["mime_type"],
                    "data": part["data"],
                },
            }
        return part

    def _to_claude_tool(self, tool: dict) -> dict:
        return {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"],
        }

    def _parse_response(self, response) -> LLMResponse:
        text = None
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text = block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=block.input)
                )

        return LLMResponse(content=text, tool_calls=tool_calls)
