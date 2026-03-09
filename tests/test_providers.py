from unittest.mock import AsyncMock, MagicMock, patch

from koclaw.providers.claude import ClaudeProvider
from koclaw.providers.gemini import GeminiProvider
from koclaw.providers.openai import OpenAIProvider

# ── Claude ──────────────────────────────────────────────────────────────────

class TestClaudeProvider:
    def _make_text_response(self, text: str):
        block = MagicMock()
        block.type = "text"
        block.text = text
        response = MagicMock()
        response.content = [block]
        return response

    def _make_tool_response(self, tool_id: str, name: str, inputs: dict):
        block = MagicMock()
        block.type = "tool_use"
        block.id = tool_id
        block.name = name
        block.input = inputs
        response = MagicMock()
        response.content = [block]
        return response

    async def test_returns_text_response(self):
        fake_response = self._make_text_response("안녕하세요")

        with patch("koclaw.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=fake_response)

            provider = ClaudeProvider(api_key="test-key")
            result = await provider.complete([{"role": "user", "content": "안녕"}])

        assert result.content == "안녕하세요"
        assert result.has_tool_calls is False

    async def test_returns_tool_call_response(self):
        fake_response = self._make_tool_response("id-1", "search", {"query": "날씨"})

        with patch("koclaw.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=fake_response)

            provider = ClaudeProvider(api_key="test-key")
            result = await provider.complete(
                [{"role": "user", "content": "날씨 검색"}],
                tools=[{"name": "search", "description": "검색", "parameters": {}}],
            )

        assert result.has_tool_calls is True
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[0].arguments == {"query": "날씨"}

    async def test_converts_tools_to_claude_format(self):
        fake_response = self._make_text_response("ok")

        with patch("koclaw.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=fake_response)

            provider = ClaudeProvider(api_key="test-key")
            await provider.complete(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{
                    "name": "echo",
                    "description": "에코",
                    "parameters": {"type": "object", "properties": {}},
                }],
            )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["tools"][0]["input_schema"] == {
            "type": "object", "properties": {}
        }

    async def test_extracts_system_message_as_system_param(self):
        """system 메시지를 messages 배열에서 제거하고 system 파라미터로 전달"""
        fake_response = self._make_text_response("응답")

        with patch("koclaw.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=fake_response)

            provider = ClaudeProvider(api_key="test-key")
            await provider.complete([
                {"role": "system", "content": "당신은 koclaw입니다."},
                {"role": "user", "content": "안녕"},
            ])

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs.get("system") == "당신은 koclaw입니다."
        assert all(m["role"] != "system" for m in call_kwargs["messages"])

    async def test_converts_multimodal_user_message_with_image(self):
        """user 메시지 content가 리스트이면 이미지 파트를 Claude API 형식으로 변환"""
        import base64
        fake_response = self._make_text_response("이미지 분석 결과")

        with patch("koclaw.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=fake_response)

            provider = ClaudeProvider(api_key="test-key")
            await provider.complete([{
                "role": "user",
                "content": [
                    {"type": "text", "text": "이미지 분석해줘"},
                    {
                        "type": "image",
                        "data": base64.b64encode(b"fake_image").decode(),
                        "mime_type": "image/png",
                    },
                ],
            }])

        call_kwargs = mock_client.messages.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert isinstance(user_content, list)
        assert user_content[0] == {"type": "text", "text": "이미지 분석해줘"}
        image_part = user_content[1]
        assert image_part["type"] == "image"
        assert image_part["source"]["type"] == "base64"
        assert image_part["source"]["media_type"] == "image/png"
        assert image_part["source"]["data"] == base64.b64encode(b"fake_image").decode()

    async def test_converts_tool_call_history_to_claude_format(self):
        """이전 tool call이 포함된 메시지를 Claude API 형식으로 변환"""
        fake_response = self._make_text_response("결과")

        with patch("koclaw.providers.claude.anthropic.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create = AsyncMock(return_value=fake_response)

            provider = ClaudeProvider(api_key="test-key")
            await provider.complete([
                {"role": "user", "content": "스케줄 등록해줘"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "tool-1", "name": "scheduler", "arguments": {"action": "add"}, "thought_signature": None}
                    ],
                    "_raw_provider_data": None,
                },
                {"role": "tool", "tool_call_id": "tool-1", "content": "✅ 등록됨"},
            ])

        call_kwargs = mock_client.messages.create.call_args.kwargs
        messages = call_kwargs["messages"]

        # assistant 메시지가 Claude tool_use 형식이어야 함
        assistant_msg = messages[1]
        assert assistant_msg["role"] == "assistant"
        assert isinstance(assistant_msg["content"], list)
        tool_use_block = next(b for b in assistant_msg["content"] if b.get("type") == "tool_use")
        assert tool_use_block["id"] == "tool-1"
        assert tool_use_block["name"] == "scheduler"
        assert tool_use_block["input"] == {"action": "add"}

        # tool result가 user 메시지 + tool_result 형식이어야 함
        tool_result_msg = messages[2]
        assert tool_result_msg["role"] == "user"
        assert isinstance(tool_result_msg["content"], list)
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["tool_use_id"] == "tool-1"
        assert tool_result_msg["content"][0]["content"] == "✅ 등록됨"


# ── OpenAI ───────────────────────────────────────────────────────────────────

class TestOpenAIProvider:
    def _make_text_response(self, text: str):
        message = MagicMock()
        message.content = text
        message.tool_calls = None
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    def _make_tool_response(self, tool_id: str, name: str, arguments: str):
        tool_call = MagicMock()
        tool_call.id = tool_id
        tool_call.function.name = name
        tool_call.function.arguments = arguments
        message = MagicMock()
        message.content = None
        message.tool_calls = [tool_call]
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        return response

    async def test_returns_text_response(self):
        fake_response = self._make_text_response("응답입니다")

        with patch("koclaw.providers.openai.openai.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

            provider = OpenAIProvider(api_key="test-key")
            result = await provider.complete([{"role": "user", "content": "hi"}])

        assert result.content == "응답입니다"
        assert result.has_tool_calls is False

    async def test_returns_tool_call_response(self):
        import json
        fake_response = self._make_tool_response(
            "call-1", "echo", json.dumps({"message": "hello"})
        )

        with patch("koclaw.providers.openai.openai.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

            provider = OpenAIProvider(api_key="test-key")
            result = await provider.complete([{"role": "user", "content": "hi"}])

        assert result.has_tool_calls is True
        assert result.tool_calls[0].name == "echo"
        assert result.tool_calls[0].arguments == {"message": "hello"}

    async def test_gemini_returns_text_response(self):
        with patch("koclaw.providers.gemini.genai.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            part = MagicMock()
            part.text = "안녕하세요"
            part.function_call = None
            candidate = MagicMock()
            candidate.content.parts = [part]
            fake_response = MagicMock()
            fake_response.candidates = [candidate]

            mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)

            provider = GeminiProvider(api_key="test-key")
            result = await provider.complete([{"role": "user", "content": "hi"}])

        assert result.content == "안녕하세요"
        assert result.has_tool_calls is False

    async def test_gemini_returns_tool_call_response(self):
        with patch("koclaw.providers.gemini.genai.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            fc = MagicMock()
            fc.name = "search"
            fc.args = {"query": "날씨"}
            part = MagicMock()
            part.text = None
            part.function_call = fc
            candidate = MagicMock()
            candidate.content.parts = [part]
            fake_response = MagicMock()
            fake_response.candidates = [candidate]

            mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)

            provider = GeminiProvider(api_key="test-key")
            result = await provider.complete(
                [{"role": "user", "content": "날씨 알려줘"}],
                tools=[{"name": "search", "description": "검색", "parameters": {}}],
            )

        assert result.has_tool_calls is True
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[0].arguments == {"query": "날씨"}

    async def test_gemini_preserves_thought_signature_in_tool_call(self):
        with patch("koclaw.providers.gemini.genai.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            fc = MagicMock()
            fc.name = "search"
            fc.args = {"query": "날씨"}
            fc.thought_signature = b"sig_abc"
            part = MagicMock()
            part.text = None
            part.function_call = fc
            candidate = MagicMock()
            candidate.content.parts = [part]
            fake_response = MagicMock()
            fake_response.candidates = [candidate]
            mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)

            provider = GeminiProvider(api_key="test-key")
            result = await provider.complete([{"role": "user", "content": "날씨"}])

        assert result.tool_calls[0].thought_signature == b"sig_abc"

    async def test_gemini_stores_raw_content_in_response(self):
        with patch("koclaw.providers.gemini.genai.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            raw_content = MagicMock()
            raw_content.parts = []
            candidate = MagicMock()
            candidate.content = raw_content
            fake_response = MagicMock()
            fake_response.candidates = [candidate]
            mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)

            provider = GeminiProvider(api_key="test-key")
            result = await provider.complete([{"role": "user", "content": "hi"}])

        assert result.raw_provider_data is raw_content

    async def test_gemini_uses_raw_content_for_assistant_messages(self):
        with patch("koclaw.providers.gemini.genai.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=MagicMock(candidates=[MagicMock(content=MagicMock(parts=[]))])
            )

            raw_content = MagicMock()  # 원본 Gemini Content (thought_signature 포함)
            provider = GeminiProvider(api_key="test-key")
            await provider.complete([
                {"role": "user", "content": "날씨"},
                {
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": "1", "name": "search", "arguments": {}, "thought_signature": None}],
                    "_raw_provider_data": raw_content,
                },
                {"role": "tool", "tool_call_id": "1", "content": "맑음"},
            ])

        call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
        contents = call_kwargs["contents"]
        # assistant 위치에 raw_content가 직접 사용되어야 함
        assert raw_content in contents

    async def test_gemini_passes_system_message_as_system_instruction(self):
        with patch("koclaw.providers.gemini.genai.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            part = MagicMock()
            part.text = "응답"
            part.function_call = None
            candidate = MagicMock()
            candidate.content.parts = [part]
            fake_response = MagicMock()
            fake_response.candidates = [candidate]
            mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)

            provider = GeminiProvider(api_key="test-key")
            await provider.complete([
                {"role": "system", "content": "당신은 koclaw입니다."},
                {"role": "user", "content": "안녕"},
            ])

        call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
        config = call_kwargs["config"]
        assert config.system_instruction == "당신은 koclaw입니다."
        # contents에는 system 메시지가 포함되지 않아야 함
        contents = call_kwargs["contents"]
        assert all(c.role != "system" for c in contents)

    async def test_gemini_converts_multimodal_user_message_with_image(self):
        """user 메시지 content가 리스트이면 이미지 파트를 inline_data로 변환"""
        import base64

        with patch("koclaw.providers.gemini.genai.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            part = MagicMock()
            part.text = "응답"
            part.function_call = None
            candidate = MagicMock()
            candidate.content.parts = [part]
            fake_response = MagicMock()
            fake_response.candidates = [candidate]
            mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)

            provider = GeminiProvider(api_key="test-key")
            await provider.complete([{
                "role": "user",
                "content": [
                    {"type": "text", "text": "이미지 분석해줘"},
                    {
                        "type": "image",
                        "data": base64.b64encode(b"fake_image").decode(),
                        "mime_type": "image/png",
                    },
                ],
            }])

        call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
        user_parts = call_kwargs["contents"][0].parts
        assert len(user_parts) == 2
        assert user_parts[0].text == "이미지 분석해줘"
        assert user_parts[1].inline_data is not None
        assert user_parts[1].inline_data.mime_type == "image/png"
        assert user_parts[1].inline_data.data == b"fake_image"

    async def test_gemini_default_model_is_flash_preview(self):
        with patch("koclaw.providers.gemini.genai.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.aio.models.generate_content = AsyncMock(
                return_value=MagicMock(candidates=[MagicMock(content=MagicMock(parts=[]))])
            )

            provider = GeminiProvider(api_key="test-key")

        assert provider._model == "gemini-3-flash-preview"

    async def test_converts_tool_call_history_to_openai_format(self):
        """이전 tool call이 포함된 메시지를 OpenAI API 형식으로 변환"""
        import json
        fake_response = self._make_text_response("결과")

        with patch("koclaw.providers.openai.openai.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

            provider = OpenAIProvider(api_key="test-key")
            await provider.complete([
                {"role": "user", "content": "스케줄 등록해줘"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "tool-1", "name": "scheduler", "arguments": {"action": "add"}, "thought_signature": None}
                    ],
                    "_raw_provider_data": None,
                },
                {"role": "tool", "tool_call_id": "tool-1", "content": "✅ 등록됨"},
            ])

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]

        # assistant 메시지가 OpenAI tool_calls 형식이어야 함
        assistant_msg = messages[1]
        assert assistant_msg["role"] == "assistant"
        tc = assistant_msg["tool_calls"][0]
        assert tc["id"] == "tool-1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "scheduler"
        assert json.loads(tc["function"]["arguments"]) == {"action": "add"}

        # tool result는 role=tool, tool_call_id 유지
        tool_result_msg = messages[2]
        assert tool_result_msg["role"] == "tool"
        assert tool_result_msg["tool_call_id"] == "tool-1"
        assert tool_result_msg["content"] == "✅ 등록됨"

    async def test_converts_multimodal_user_message_with_image(self):
        """user 메시지 content가 리스트이면 이미지 파트를 OpenAI image_url 형식으로 변환"""
        import base64
        fake_response = self._make_text_response("이미지 분석 결과")

        with patch("koclaw.providers.openai.openai.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

            provider = OpenAIProvider(api_key="test-key")
            await provider.complete([{
                "role": "user",
                "content": [
                    {"type": "text", "text": "이미지 분석해줘"},
                    {
                        "type": "image",
                        "data": base64.b64encode(b"fake_image").decode(),
                        "mime_type": "image/png",
                    },
                ],
            }])

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        assert isinstance(user_content, list)
        assert user_content[0] == {"type": "text", "text": "이미지 분석해줘"}
        image_part = user_content[1]
        assert image_part["type"] == "image_url"
        expected_url = "data:image/png;base64," + base64.b64encode(b"fake_image").decode()
        assert image_part["image_url"]["url"] == expected_url

    async def test_ollama_uses_custom_base_url(self):
        fake_response = self._make_text_response("ollama 응답")

        with patch("koclaw.providers.openai.openai.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

            provider = OpenAIProvider(
                api_key="ollama",
                base_url="http://localhost:11434/v1",
                model="llama3",
            )
            await provider.complete([{"role": "user", "content": "hi"}])

        mock_cls.assert_called_once_with(
            api_key="ollama",
            base_url="http://localhost:11434/v1",
        )
