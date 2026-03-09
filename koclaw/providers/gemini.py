import base64
import uuid

from google import genai
from google.genai import types

from koclaw.core.llm import LLMProvider, LLMResponse, ToolCall

DEFAULT_MODEL = "gemini-3-flash-preview"


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def complete(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        contents = self._to_gemini_contents(messages)

        config_kwargs: dict = {}
        if system_parts:
            config_kwargs["system_instruction"] = "\n".join(system_parts)
        if tools:
            config_kwargs["tools"] = [
                types.Tool(function_declarations=[
                    types.FunctionDeclaration(
                        name=t["name"],
                        description=t["description"],
                        parameters=t["parameters"],
                    )
                    for t in tools
                ])
            ]

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        raw_content = response.candidates[0].content
        return self._parse_response(response, raw_content)

    def _to_gemini_contents(self, messages: list[dict]) -> list:
        # tool_call_id → tool_name 매핑 (function_response 생성에 필요)
        id_to_name: dict[str, str] = {}
        for msg in messages:
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []):
                    id_to_name[tc["id"]] = tc["name"]

        contents = []
        for msg in messages:
            role = msg["role"]
            if role == "user":
                content = msg["content"]
                if isinstance(content, list):
                    parts = []
                    for p in content:
                        if p["type"] == "text":
                            parts.append(types.Part(text=p["text"]))
                        elif p["type"] == "image":
                            parts.append(types.Part(
                                inline_data=types.Blob(
                                    data=base64.b64decode(p["data"]),
                                    mime_type=p["mime_type"],
                                )
                            ))
                else:
                    parts = [types.Part(text=content)]
                contents.append(types.Content(role="user", parts=parts))
            elif role == "assistant":
                # 원본 Gemini Content 있으면 그대로 사용 (thought_signature 보존)
                if msg.get("_raw_provider_data") is not None:
                    contents.append(msg["_raw_provider_data"])
                    continue
                parts = []
                if msg.get("content"):
                    parts.append(types.Part(text=msg["content"]))
                for tc in msg.get("tool_calls", []):
                    parts.append(types.Part(
                        function_call=types.FunctionCall(name=tc["name"], args=tc["arguments"])
                    ))
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                name = id_to_name.get(msg["tool_call_id"], "unknown")
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(
                        function_response=types.FunctionResponse(
                            name=name,
                            response={"result": msg["content"]},
                        )
                    )],
                ))
        return contents

    def _parse_response(self, response, raw_content=None) -> LLMResponse:
        text_parts = []
        tool_calls = []

        for part in response.candidates[0].content.parts:
            if part.text:
                text_parts.append(part.text)
            if part.function_call:
                fc = part.function_call
                tool_calls.append(ToolCall(
                    id=str(uuid.uuid4()),
                    name=fc.name,
                    arguments=dict(fc.args),
                    thought_signature=getattr(fc, "thought_signature", None) or None,
                ))

        return LLMResponse(
            content="\n".join(text_parts) or None,
            tool_calls=tool_calls,
            raw_provider_data=raw_content,
        )
