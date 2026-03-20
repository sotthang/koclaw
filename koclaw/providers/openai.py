import json

import openai

from koclaw.core.llm import LLMProvider, LLMResponse, ToolCall

DEFAULT_MODEL = "gpt-5.3"


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str | None = None,
    ):
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        kwargs = dict(model=self._model, messages=self._convert_messages(messages))
        if tools:
            kwargs["tools"] = [self._to_openai_tool(t) for t in tools]

        response = await self._client.chat.completions.create(**kwargs)
        return self._parse_response(response)

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        converted = []
        # tool 메시지 배치가 끝난 후 삽입할 이미지 user 메시지를 임시 보관
        pending_image_messages: list[dict] = []

        for msg in messages:
            role = msg["role"]

            # tool 배치가 끝나는 시점(다른 role 등장)에 이미지 user 메시지 삽입
            # OpenAI는 tool 메시지에 이미지를 지원하지 않으므로 user 메시지로 분리
            if role != "tool" and pending_image_messages:
                converted.extend(pending_image_messages)
                pending_image_messages = []

            if role == "assistant" and "tool_calls" in msg:
                converted.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content"),
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                                },
                            }
                            for tc in msg["tool_calls"]
                        ],
                    }
                )
            elif role == "tool":
                if msg.get("_is_image"):
                    # tool 메시지는 텍스트로, 실제 이미지는 뒤따르는 user 메시지로 전달
                    hint = msg.get("_screen_size_hint", "")
                    text = f"스크린샷을 캡처했습니다.{' ' + hint if hint else ''}"
                    converted.append(
                        {
                            "role": "tool",
                            "tool_call_id": msg["tool_call_id"],
                            "content": text,
                        }
                    )
                    pending_image_messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{msg.get('_mime_type', 'image/png')};base64,{msg['content']}"
                                    },
                                }
                            ],
                        }
                    )
                else:
                    converted.append(
                        {
                            "role": "tool",
                            "tool_call_id": msg["tool_call_id"],
                            "content": msg["content"],
                        }
                    )
            else:
                content = msg["content"]
                if isinstance(content, list):
                    content = [self._convert_content_part(p) for p in content]
                converted.append({"role": role, "content": content})

        # 마지막 배치가 tool 메시지로 끝났을 경우 처리
        if pending_image_messages:
            converted.extend(pending_image_messages)

        return converted

    def _convert_content_part(self, part: dict) -> dict:
        if part.get("type") == "image":
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{part['mime_type']};base64,{part['data']}",
                },
            }
        return part

    def _to_openai_tool(self, tool: dict) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }

    def _parse_response(self, response) -> LLMResponse:
        message = response.choices[0].message
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        return LLMResponse(content=message.content, tool_calls=tool_calls)
