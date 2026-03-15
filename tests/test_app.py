from unittest.mock import AsyncMock

import pytest

from koclaw.app import create_agent_fn, create_provider, to_slack_mrkdwn
from koclaw.core.llm import FallbackProvider, LLMResponse
from koclaw.providers.claude import ClaudeProvider
from koclaw.providers.gemini import GeminiProvider
from koclaw.providers.ollama import OllamaProvider
from koclaw.providers.openai import OpenAIProvider

# ── create_provider ───────────────────────────────────────────────────────────


class TestCreateProvider:
    def test_creates_claude_provider(self):
        provider = create_provider({"DEFAULT_LLM_PROVIDER": "claude", "ANTHROPIC_API_KEY": "key"})
        assert isinstance(provider, ClaudeProvider)

    def test_creates_openai_provider(self):
        provider = create_provider({"DEFAULT_LLM_PROVIDER": "openai", "OPENAI_API_KEY": "key"})
        assert isinstance(provider, OpenAIProvider)

    def test_creates_gemini_provider(self):
        provider = create_provider({"DEFAULT_LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "key"})
        assert isinstance(provider, GeminiProvider)

    def test_gemini_uses_default_model_from_env(self):
        provider = create_provider(
            {
                "DEFAULT_LLM_PROVIDER": "gemini",
                "GEMINI_API_KEY": "key",
                "DEFAULT_MODEL": "gemini-1.5-flash",
            }
        )
        assert isinstance(provider, GeminiProvider)
        assert provider._model == "gemini-1.5-flash"

    def test_creates_ollama_provider(self):
        provider = create_provider({"DEFAULT_LLM_PROVIDER": "ollama"})
        assert isinstance(provider, OllamaProvider)

    def test_creates_fallback_chain_when_multiple_keys(self):
        provider = create_provider(
            {
                "DEFAULT_LLM_PROVIDER": "claude",
                "ANTHROPIC_API_KEY": "key1",
                "OPENAI_API_KEY": "key2",
            }
        )
        assert isinstance(provider, FallbackProvider)

    def test_raises_when_no_provider_configured(self):
        with pytest.raises(ValueError, match="LLM provider"):
            create_provider({})

    def test_fallback_providers_from_env(self):
        provider = create_provider(
            {
                "DEFAULT_LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "key1",
                "FALLBACK_LLM_PROVIDERS": "claude",
                "ANTHROPIC_API_KEY": "key2",
            }
        )
        assert isinstance(provider, FallbackProvider)
        assert isinstance(provider._providers[0], OpenAIProvider)
        assert isinstance(provider._providers[1], ClaudeProvider)

    def test_fallback_providers_multiple(self):
        provider = create_provider(
            {
                "DEFAULT_LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "key1",
                "FALLBACK_LLM_PROVIDERS": "claude,gemini",
                "ANTHROPIC_API_KEY": "key2",
                "GEMINI_API_KEY": "key3",
            }
        )
        assert isinstance(provider, FallbackProvider)
        assert len(provider._providers) == 3

    def test_fallback_provider_skipped_without_api_key(self):
        provider = create_provider(
            {
                "DEFAULT_LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "key1",
                "FALLBACK_LLM_PROVIDERS": "claude",
                # ANTHROPIC_API_KEY 없음
            }
        )
        assert isinstance(provider, OpenAIProvider)

    def test_per_provider_model_overrides_default_model(self):
        """CLAUDE_MODEL이 있으면 DEFAULT_MODEL 대신 사용"""
        provider = create_provider(
            {
                "DEFAULT_LLM_PROVIDER": "claude",
                "ANTHROPIC_API_KEY": "key",
                "CLAUDE_MODEL": "claude-opus-4-6",
                "DEFAULT_MODEL": "claude-sonnet-4-6",
            }
        )
        assert provider._model == "claude-opus-4-6"

    def test_openai_per_provider_model(self):
        provider = create_provider(
            {
                "DEFAULT_LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "key",
                "OPENAI_MODEL": "gpt-5.3",
            }
        )
        assert provider._model == "gpt-5.3"

    def test_gemini_per_provider_model(self):
        provider = create_provider(
            {
                "DEFAULT_LLM_PROVIDER": "gemini",
                "GEMINI_API_KEY": "key",
                "GEMINI_MODEL": "gemini-3-flash-preview",
            }
        )
        assert provider._model == "gemini-3-flash-preview"

    def test_fallback_uses_own_model_not_primary_model(self):
        """폴백 provider는 자신의 모델 설정을 사용"""
        provider = create_provider(
            {
                "DEFAULT_LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "key1",
                "OPENAI_MODEL": "gpt-5.3",
                "FALLBACK_LLM_PROVIDERS": "claude",
                "ANTHROPIC_API_KEY": "key2",
                "CLAUDE_MODEL": "claude-sonnet-4-6",
            }
        )
        assert isinstance(provider, FallbackProvider)
        assert provider._providers[0]._model == "gpt-5.3"
        assert provider._providers[1]._model == "claude-sonnet-4-6"


# ── create_agent_fn ───────────────────────────────────────────────────────────


class TestCreateAgentFn:
    async def test_system_prompt_instructs_to_ignore_external_data_instructions(self, tmp_path):
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=LLMResponse(content="응답", tool_calls=[]))

        agent_fn = create_agent_fn(provider=mock_provider, tools=ToolRegistry(), db=db)
        await agent_fn(session_id="ch_001", user_message="안녕", files=[])

        call_kwargs = mock_provider.complete.call_args.kwargs
        system_prompt = call_kwargs["messages"][0]["content"]
        assert "[외부 데이터 시작:" in system_prompt
        assert "[외부 데이터 끝:" in system_prompt

    async def test_system_prompt_guides_file_tool_usage(self, tmp_path):
        """시스템 프롬프트에 파일 분석 시 file tool 사용 안내가 포함되어야 한다."""
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=LLMResponse(content="응답", tool_calls=[]))

        agent_fn = create_agent_fn(provider=mock_provider, tools=ToolRegistry(), db=db)
        await agent_fn(session_id="ch_001", user_message="안녕", files=[])

        call_kwargs = mock_provider.complete.call_args.kwargs
        system_prompt = call_kwargs["messages"][0]["content"]
        assert "file" in system_prompt
        assert "scope=session" in system_prompt

    async def test_system_prompt_contains_current_datetime(self, tmp_path):
        from datetime import datetime

        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=LLMResponse(content="응답", tool_calls=[]))

        agent_fn = create_agent_fn(provider=mock_provider, tools=ToolRegistry(), db=db)
        await agent_fn(session_id="ch_001", user_message="지금 몇시야", files=[])

        call_kwargs = mock_provider.complete.call_args.kwargs
        system_prompt = call_kwargs["messages"][0]["content"]
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in system_prompt

    async def test_loads_history_from_db(self, tmp_path):
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_message("ch_001", "user", "이전 메시지")
        await db.save_message("ch_001", "assistant", "이전 응답")

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(content="새 응답", tool_calls=[])
        )

        agent_fn = create_agent_fn(provider=mock_provider, tools=ToolRegistry(), db=db)
        result = await agent_fn(session_id="ch_001", user_message="새 질문", files=[])

        assert result == "새 응답"
        # LLM 호출 시 이전 히스토리가 포함되어야 함
        call_messages = mock_provider.complete.call_args.kwargs["messages"]
        contents = [m["content"] for m in call_messages]
        assert "이전 메시지" in contents
        assert "새 질문" in contents

    async def test_saves_messages_to_db(self, tmp_path):
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(content="저장될 응답", tool_calls=[])
        )

        agent_fn = create_agent_fn(provider=mock_provider, tools=ToolRegistry(), db=db)
        await agent_fn(session_id="ch_001", user_message="저장될 질문", files=[])

        messages = await db.get_messages("ch_001")
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "저장될 질문"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "저장될 응답"

    async def test_file_content_appended_to_user_message(self, tmp_path):
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(content="파일 분석 완료", tool_calls=[])
        )

        async def fake_fetcher(url: str) -> bytes:
            return "파일의 실제 내용입니다".encode("utf-8")

        agent_fn = create_agent_fn(
            provider=mock_provider,
            tools=ToolRegistry(),
            db=db,
            file_fetcher=fake_fetcher,
        )
        await agent_fn(
            session_id="ch_001",
            user_message="이 파일 요약해줘",
            files=[{"id": "F001", "name": "report.txt", "url": "https://slack.example.com/file"}],
        )

        call_messages = mock_provider.complete.call_args.kwargs["messages"]
        user_msg = next(m for m in call_messages if m["role"] == "user")
        assert "파일의 실제 내용입니다" in user_msg["content"]
        assert "report.txt" in user_msg["content"]

    async def test_session_tool_registered_per_call(self, tmp_path):
        from koclaw.core.tool import Tool, ToolRegistry
        from koclaw.storage.db import Database

        class SessionTool(Tool):
            name = "session_tool"
            description = "세션 tool"
            parameters = {"type": "object", "properties": {}, "required": []}
            is_sandboxed = False

            def __init__(self, session_id: str):
                self.captured_session_id = session_id

            async def execute(self) -> str:
                return self.captured_session_id

        db = Database(tmp_path / "test.db")
        await db.initialize()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=LLMResponse(content="응답", tool_calls=[]))

        captured = {}

        def factory(session_id: str, user_id: str | None) -> SessionTool:
            t = SessionTool(session_id=session_id)
            captured["tool"] = t
            return t

        agent_fn = create_agent_fn(
            provider=mock_provider,
            tools=ToolRegistry(),
            db=db,
            session_tool_factories=[factory],
        )
        await agent_fn(session_id="ch_test", user_message="hi", files=[])

        assert captured["tool"].captured_session_id == "ch_test"

    async def test_user_id_passed_to_session_tool_factory(self, tmp_path):
        """agent_fn에 user_id를 전달하면 session_tool_factory에도 전달된다"""
        from koclaw.core.tool import Tool, ToolRegistry
        from koclaw.storage.db import Database

        class DummyTool(Tool):
            name = "dummy"
            description = "dummy"
            parameters = {"type": "object", "properties": {}, "required": []}
            is_sandboxed = False

            def __init__(self, session_id, user_id):
                self.user_id = user_id

            async def execute(self) -> str:
                return ""

        db = Database(tmp_path / "test.db")
        await db.initialize()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=LLMResponse(content="ok", tool_calls=[]))

        captured = {}

        def factory(session_id: str, user_id: str | None):
            t = DummyTool(session_id=session_id, user_id=user_id)
            captured["tool"] = t
            return t

        agent_fn = create_agent_fn(
            provider=mock_provider,
            tools=ToolRegistry(),
            db=db,
            session_tool_factories=[factory],
        )
        await agent_fn(session_id="slack:D001", user_message="hi", files=[], user_id="U999")

        assert captured["tool"].user_id == "U999"

    async def test_memories_injected_into_system_prompt(self, tmp_path):
        """세션에 해당하는 메모리가 시스템 프롬프트에 주입된다"""
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_memory("user", "U1", "이름: 홍길동")

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=LLMResponse(content="ok", tool_calls=[]))

        agent_fn = create_agent_fn(provider=mock_provider, tools=ToolRegistry(), db=db)
        await agent_fn(session_id="slack:D001", user_message="안녕", files=[], user_id="U1")

        call_kwargs = mock_provider.complete.call_args.kwargs
        system_prompt = call_kwargs["messages"][0]["content"]
        assert "홍길동" in system_prompt

    async def test_channel_memory_injected_for_channel_session(self, tmp_path):
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_memory("channel", "slack:C001", "채널 목적: 개발팀")

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=LLMResponse(content="ok", tool_calls=[]))

        agent_fn = create_agent_fn(provider=mock_provider, tools=ToolRegistry(), db=db)
        await agent_fn(session_id="slack:C001", user_message="안녕", files=[], user_id="U1")

        call_kwargs = mock_provider.complete.call_args.kwargs
        system_prompt = call_kwargs["messages"][0]["content"]
        assert "개발팀" in system_prompt

    async def test_summarization_triggered_when_messages_exceed_threshold(self, tmp_path):
        """메시지가 임계값 초과 시 요약이 생성되고 오래된 메시지가 삭제된다"""
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        # 임계값(20)을 넘도록 메시지 저장
        for i in range(20):
            await db.save_message("ch_001", "user", f"질문 {i}")
            await db.save_message("ch_001", "assistant", f"답변 {i}")

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(content="새 응답", tool_calls=[])
        )

        agent_fn = create_agent_fn(provider=mock_provider, tools=ToolRegistry(), db=db)
        await agent_fn(session_id="ch_001", user_message="새 질문", files=[])

        summary = await db.get_summary("ch_001")
        assert summary is not None
        remaining = await db.count_messages("ch_001")
        assert remaining <= 10  # 최근 메시지만 남아있어야 함

    async def test_summary_prepended_to_history(self, tmp_path):
        """이전에 저장된 요약이 대화 히스토리 앞에 추가된다"""
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        await db.save_summary("ch_001", "이전 대화 요약: 파이썬 질문을 했음")

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=LLMResponse(content="ok", tool_calls=[]))

        agent_fn = create_agent_fn(provider=mock_provider, tools=ToolRegistry(), db=db)
        await agent_fn(session_id="ch_001", user_message="계속해서 질문", files=[])

        call_kwargs = mock_provider.complete.call_args.kwargs
        all_content = " ".join(str(m.get("content", "")) for m in call_kwargs["messages"])
        assert "파이썬" in all_content

    async def test_slack_file_saved_to_workspace(self, tmp_path):
        """Option A: workspace가 있으면 Slack 파일을 workspace/{session_id}/에 저장"""
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        workspace = tmp_path / "workspace"

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(content="분석 완료", tool_calls=[])
        )

        async def fake_fetcher(url: str) -> bytes:
            return "파일 바이너리 내용".encode("utf-8")

        agent_fn = create_agent_fn(
            provider=mock_provider,
            tools=ToolRegistry(),
            db=db,
            file_fetcher=fake_fetcher,
            workspace=workspace,
        )
        await agent_fn(
            session_id="ch_001",
            user_message="분석해줘",
            files=[{"id": "F001", "name": "report.txt", "url": "https://slack.example.com/file"}],
        )

        saved = workspace / "ch_001" / "report.txt"
        assert saved.exists()
        assert saved.read_bytes() == "파일 바이너리 내용".encode("utf-8")

    async def test_llm_notified_about_saved_file_not_raw_content(self, tmp_path):
        """Option A: LLM에게 파일 저장 안내가 전달되고 파일 원본 내용은 직접 포함되지 않음"""
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        workspace = tmp_path / "workspace"

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(content="분석 완료", tool_calls=[])
        )

        async def fake_fetcher(url: str) -> bytes:
            return "파일 원본 내용 절대 LLM에 직접 노출 안됨".encode("utf-8")

        agent_fn = create_agent_fn(
            provider=mock_provider,
            tools=ToolRegistry(),
            db=db,
            file_fetcher=fake_fetcher,
            workspace=workspace,
        )
        await agent_fn(
            session_id="ch_001",
            user_message="분석해줘",
            files=[{"id": "F001", "name": "report.txt", "url": "https://slack.example.com/file"}],
        )

        call_messages = mock_provider.complete.call_args.kwargs["messages"]
        user_msg = next(m for m in call_messages if m["role"] == "user")
        assert "report.txt" in user_msg["content"]
        assert "file" in user_msg["content"]  # file tool 안내
        assert "파일 원본 내용 절대 LLM에 직접 노출 안됨" not in user_msg["content"]

    async def test_image_file_sent_as_multimodal_with_workspace(self, tmp_path):
        """workspace 있을 때 이미지는 멀티모달로 전달, 비이미지는 디스크에 저장"""
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()
        workspace = tmp_path / "workspace"

        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(content="이미지 분석 완료", tool_calls=[])
        )

        async def fake_fetcher(url: str) -> bytes:
            if "photo" in url:
                return png_bytes
            return b"text content"

        agent_fn = create_agent_fn(
            provider=mock_provider,
            tools=ToolRegistry(),
            db=db,
            file_fetcher=fake_fetcher,
            workspace=workspace,
        )
        await agent_fn(
            session_id="ch_001",
            user_message="분석해줘",
            files=[
                {"id": "F001", "name": "photo.png", "url": "https://slack.example.com/photo"},
                {"id": "F002", "name": "report.txt", "url": "https://slack.example.com/report"},
            ],
        )

        # 이미지는 디스크에 저장되지 않고 멀티모달로 전달
        assert not (workspace / "ch_001" / "photo.png").exists()
        # 비이미지는 디스크에 저장
        assert (workspace / "ch_001" / "report.txt").exists()
        # LLM에는 이미지 파트가 포함된 리스트 메시지 전달
        call_messages = mock_provider.complete.call_args.kwargs["messages"]
        user_msg = next(m for m in call_messages if m["role"] == "user")
        assert isinstance(user_msg["content"], list)
        image_parts = [p for p in user_msg["content"] if p.get("type") == "image"]
        assert len(image_parts) == 1
        assert image_parts[0]["mime_type"] == "image/png"

    async def test_image_file_sent_as_multimodal_message(self, tmp_path):
        """이미지 파일이 있고 workspace 없을 때 멀티모달 메시지로 전달"""
        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()

        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(content="이미지 분석 완료", tool_calls=[])
        )

        async def fake_fetcher(url: str) -> bytes:
            return png_bytes

        agent_fn = create_agent_fn(
            provider=mock_provider,
            tools=ToolRegistry(),
            db=db,
            file_fetcher=fake_fetcher,
        )
        await agent_fn(
            session_id="ch_001",
            user_message="이 이미지 분석해줘",
            files=[{"id": "F001", "name": "photo.png", "url": "https://slack.example.com/file"}],
        )

        call_messages = mock_provider.complete.call_args.kwargs["messages"]
        user_msg = next(m for m in call_messages if m["role"] == "user")
        assert isinstance(user_msg["content"], list)
        image_parts = [p for p in user_msg["content"] if p.get("type") == "image"]
        assert len(image_parts) == 1
        assert image_parts[0]["mime_type"] == "image/png"


class TestFileDownloadSizeLimit:
    async def test_oversized_file_is_skipped_and_user_notified(self, tmp_path, monkeypatch):
        """파일이 크기 제한 초과 시 처리를 건너뛰고 사용자에게 안내한다."""
        import koclaw.core.config as cfg_module

        monkeypatch.setattr(cfg_module, "MAX_FILE_DOWNLOAD_BYTES", 10)

        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(return_value=LLMResponse(content="응답", tool_calls=[]))

        async def oversized_fetcher(url: str) -> bytes:
            return b"x" * 100  # 10바이트 제한 초과

        agent_fn = create_agent_fn(
            provider=mock_provider,
            tools=ToolRegistry(),
            db=db,
            file_fetcher=oversized_fetcher,
        )
        await agent_fn(
            session_id="ch_001",
            user_message="분석해줘",
            files=[{"id": "F001", "name": "big.pdf", "url": "https://example.com/big.pdf"}],
        )

        call_messages = mock_provider.complete.call_args.kwargs["messages"]
        user_msg = next(m for m in call_messages if m["role"] == "user")
        assert "너무 큽니다" in str(user_msg["content"]) or "크기 제한" in str(user_msg["content"])

    async def test_normal_sized_file_is_processed(self, tmp_path, monkeypatch):
        """크기 제한 이하인 파일은 정상 처리된다."""
        import koclaw.core.config as cfg_module

        monkeypatch.setattr(cfg_module, "MAX_FILE_DOWNLOAD_BYTES", 1024)

        from koclaw.core.tool import ToolRegistry
        from koclaw.storage.db import Database

        db = Database(tmp_path / "test.db")
        await db.initialize()

        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value=LLMResponse(content="파일 분석 완료", tool_calls=[])
        )

        async def small_fetcher(url: str) -> bytes:
            return "작은 파일 내용입니다".encode("utf-8")

        agent_fn = create_agent_fn(
            provider=mock_provider,
            tools=ToolRegistry(),
            db=db,
            file_fetcher=small_fetcher,
        )
        await agent_fn(
            session_id="ch_001",
            user_message="분석해줘",
            files=[{"id": "F001", "name": "small.txt", "url": "https://example.com/small.txt"}],
        )

        call_messages = mock_provider.complete.call_args.kwargs["messages"]
        user_msg = next(m for m in call_messages if m["role"] == "user")
        assert "작은 파일 내용입니다" in str(user_msg["content"])


class TestToSlackMrkdwn:
    def test_converts_double_asterisk_to_single(self):
        assert to_slack_mrkdwn("**굵은 텍스트**") == "*굵은 텍스트*"

    def test_converts_headers_to_bold(self):
        assert to_slack_mrkdwn("### 제목") == "*제목*"
        assert to_slack_mrkdwn("## 제목") == "*제목*"
        assert to_slack_mrkdwn("# 제목") == "*제목*"

    def test_removes_horizontal_rules(self):
        assert to_slack_mrkdwn("---") == ""
        assert to_slack_mrkdwn("----") == ""

    def test_converts_markdown_list_star_to_bullet(self):
        assert to_slack_mrkdwn("*   항목") == "• 항목"
        assert to_slack_mrkdwn("*  항목") == "• 항목"

    def test_preserves_slack_bold(self):
        assert to_slack_mrkdwn("*이미 슬랙 볼드*") == "*이미 슬랙 볼드*"

    def test_converts_mixed_response(self):
        text = "### 1. 제목\n*   **배경:** 내용\n---"
        result = to_slack_mrkdwn(text)
        assert "### " not in result
        assert "**" not in result
        assert "---" not in result
        assert "*1. 제목*" in result
        assert "• *배경:* 내용" in result
