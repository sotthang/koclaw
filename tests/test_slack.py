from unittest.mock import ANY, AsyncMock, MagicMock

from koclaw.channels.slack import SlackChannel, parse_slack_event


class TestParseSlackEvent:
    def test_parses_text_message(self):
        event = {
            "channel": "C001",
            "user": "U001",
            "text": "<@BOT_ID> 안녕하세요",
        }
        parsed = parse_slack_event(event, bot_user_id="BOT_ID")
        assert parsed["session_id"] == "slack:C001"
        assert parsed["user_id"] == "U001"
        assert parsed["text"] == "안녕하세요"
        assert parsed["files"] == []

    def test_removes_bot_mention_from_text(self):
        event = {
            "channel": "C001",
            "user": "U001",
            "text": "<@BOTID>   날씨 알려줘",
        }
        parsed = parse_slack_event(event, bot_user_id="BOTID")
        assert parsed["text"] == "날씨 알려줘"

    def test_includes_thread_ts_when_in_thread(self):
        event = {
            "channel": "C001",
            "user": "U001",
            "text": "<@BOT> 안녕",
            "thread_ts": "9999.0000",
        }
        parsed = parse_slack_event(event, bot_user_id="BOT")
        assert parsed["thread_ts"] == "9999.0000"
        assert parsed["session_id"] == "slack:C001:9999.0000"

    def test_thread_ts_is_none_when_not_in_thread(self):
        event = {"channel": "C001", "user": "U001", "text": "<@BOT> 안녕"}
        parsed = parse_slack_event(event, bot_user_id="BOT")
        assert parsed["thread_ts"] is None
        assert parsed["session_id"] == "slack:C001"

    def test_dm_channel_uses_user_scoped_session_id(self):
        """DM 채널(D로 시작)은 slack:dm:USER_ID 형태의 session_id를 사용한다."""
        event = {"channel": "D001XYZ", "user": "U999", "text": "<@BOT> 안녕"}
        parsed = parse_slack_event(event, bot_user_id="BOT")
        assert parsed["session_id"] == "slack:dm:U999"

    def test_dm_channel_in_thread_preserves_user_scope(self):
        """DM 스레드도 slack:dm:USER_ID 형태를 유지한다."""
        event = {"channel": "D001XYZ", "user": "U999", "text": "<@BOT> 안녕", "thread_ts": "1234.5"}
        parsed = parse_slack_event(event, bot_user_id="BOT")
        assert parsed["session_id"] == "slack:dm:U999"

    def test_group_dm_uses_user_scoped_session_id(self):
        """그룹 DM 채널(G로 시작)도 slack:dm:USER_ID 형태의 session_id를 사용한다."""
        event = {"channel": "G001XYZ", "user": "U999", "text": "<@BOT> 안녕"}
        parsed = parse_slack_event(event, bot_user_id="BOT")
        assert parsed["session_id"] == "slack:dm:U999"

    def test_group_dm_in_thread_preserves_user_scope(self):
        """그룹 DM 스레드도 slack:dm:USER_ID 형태를 유지한다."""
        event = {"channel": "G001XYZ", "user": "U999", "text": "<@BOT> 안녕", "thread_ts": "1234.5"}
        parsed = parse_slack_event(event, bot_user_id="BOT")
        assert parsed["session_id"] == "slack:dm:U999"

    def test_parses_file_attachments(self):
        event = {
            "channel": "C001",
            "user": "U001",
            "text": "<@BOT> 이 파일 분석해줘",
            "files": [
                {"id": "F001", "name": "report.pdf", "url_private": "https://files.slack.com/report.pdf"},
            ],
        }
        parsed = parse_slack_event(event, bot_user_id="BOT")
        assert len(parsed["files"]) == 1
        assert parsed["files"][0]["name"] == "report.pdf"


class TestSlackChannel:
    def _make_channel(self):
        mock_app = MagicMock()
        mock_agent_fn = AsyncMock(return_value="테스트 응답")
        return SlackChannel(app=mock_app, agent_fn=mock_agent_fn), mock_app, mock_agent_fn

    async def test_sends_thinking_message_then_updates(self):
        channel, mock_app, mock_agent_fn = self._make_channel()

        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_mention(
            event={"channel": "C001", "user": "U001", "text": "<@BOT> 안녕"},
            say=mock_say,
            client=mock_client,
            bot_user_id="BOT",
        )

        # "⏳ 생각 중..." 먼저 전송
        mock_say.assert_called_once_with("⏳ 생각 중...")
        # 최종 응답으로 메시지 업데이트
        mock_client.chat_update.assert_called_once()
        update_call = mock_client.chat_update.call_args.kwargs
        assert update_call["text"] == "테스트 응답"

    async def test_calls_agent_with_parsed_message(self):
        channel, mock_app, mock_agent_fn = self._make_channel()

        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_mention(
            event={"channel": "C001", "user": "U001", "text": "<@BOT> 날씨 알려줘"},
            say=mock_say,
            client=mock_client,
            bot_user_id="BOT",
        )

        mock_agent_fn.assert_called_once_with(
            session_id="slack:C001",
            user_message="날씨 알려줘",
            files=[],
            user_id="U001",
            progress_callback=ANY,
        )

    async def test_updates_with_error_message_on_failure(self):
        mock_app = MagicMock()
        mock_agent_fn = AsyncMock(side_effect=RuntimeError("처리 실패"))
        channel = SlackChannel(app=mock_app, agent_fn=mock_agent_fn)

        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_mention(
            event={"channel": "C001", "user": "U001", "text": "<@BOT> 질문"},
            say=mock_say,
            client=mock_client,
            bot_user_id="BOT",
        )

        update_call = mock_client.chat_update.call_args.kwargs
        assert "오류" in update_call["text"] or "실패" in update_call["text"]

    def test_should_handle_dm_message(self):
        channel, _, _ = self._make_channel()
        event = {"channel": "D001", "user": "U001", "text": "안녕", "channel_type": "im"}
        assert channel.should_handle_message(event, bot_user_id="BOT") is True

    def test_should_handle_channel_message_without_mention(self):
        channel, _, _ = self._make_channel()
        event = {"channel": "C001", "user": "U001", "text": "안녕", "channel_type": "channel"}
        assert channel.should_handle_message(event, bot_user_id="BOT") is True

    def test_should_not_handle_message_with_bot_mention(self):
        channel, _, _ = self._make_channel()
        event = {"channel": "C001", "user": "U001", "text": "<@BOT> 안녕", "channel_type": "channel"}
        assert channel.should_handle_message(event, bot_user_id="BOT") is False

    def test_should_not_handle_bot_own_message(self):
        channel, _, _ = self._make_channel()
        event = {"channel": "C001", "bot_id": "B001", "text": "봇 응답"}
        assert channel.should_handle_message(event, bot_user_id="BOT") is False

    def test_should_not_handle_message_changed_subtype(self):
        channel, _, _ = self._make_channel()
        event = {
            "channel": "C001",
            "subtype": "message_changed",
            "message": {"user": "U001", "text": "https://youtu.be/abc"},
        }
        assert channel.should_handle_message(event, bot_user_id="BOT") is False

    def test_should_handle_file_share_subtype(self):
        channel, _, _ = self._make_channel()
        event = {
            "channel": "D001",
            "channel_type": "im",
            "user": "U001",
            "text": "이 파일 요약해줘",
            "subtype": "file_share",
            "files": [{"id": "F001", "name": "doc.hwp", "url_private": "https://files.slack.com/doc.hwp"}],
        }
        assert channel.should_handle_message(event, bot_user_id="BOT") is True

    async def test_handle_dm_calls_agent_without_mention_stripping(self):
        channel, mock_app, mock_agent_fn = self._make_channel()

        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_dm(
            event={"channel": "D001", "user": "U001", "text": "안녕하세요"},
            say=mock_say,
            client=mock_client,
        )

        mock_agent_fn.assert_called_once_with(
            session_id="slack:D001",
            user_message="안녕하세요",
            files=[],
            user_id="U001",
            progress_callback=ANY,
        )

    async def test_handle_mention_replies_in_thread_when_thread_ts_present(self):
        channel, _, _ = self._make_channel()
        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_mention(
            event={"channel": "C001", "user": "U001", "text": "<@BOT> 안녕", "thread_ts": "9999.0000"},
            say=mock_say,
            client=mock_client,
            bot_user_id="BOT",
        )

        mock_say.assert_called_once_with("⏳ 생각 중...", thread_ts="9999.0000")

    async def test_handle_mention_uses_thread_session_id(self):
        channel, _, mock_agent_fn = self._make_channel()
        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_mention(
            event={"channel": "C001", "user": "U001", "text": "<@BOT> 안녕", "thread_ts": "9999.0000"},
            say=mock_say,
            client=mock_client,
            bot_user_id="BOT",
        )

        mock_agent_fn.assert_called_once_with(
            session_id="slack:C001:9999.0000",
            user_message="안녕",
            files=[],
            user_id="U001",
            progress_callback=ANY,
        )

    async def test_handle_dm_replies_in_thread_when_thread_ts_present(self):
        channel, _, _ = self._make_channel()
        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_dm(
            event={"channel": "D001", "user": "U001", "text": "질문", "thread_ts": "8888.0000"},
            say=mock_say,
            client=mock_client,
        )

        mock_say.assert_called_once_with("⏳ 생각 중...", thread_ts="8888.0000")

    async def test_handle_dm_sends_thinking_then_updates(self):
        channel, mock_app, mock_agent_fn = self._make_channel()

        mock_say = AsyncMock(return_value={"ts": "9999.0001"})
        mock_client = AsyncMock()

        await channel.handle_dm(
            event={"channel": "D001", "user": "U001", "text": "질문"},
            say=mock_say,
            client=mock_client,
        )

        mock_say.assert_called_once_with("⏳ 생각 중...")
        mock_client.chat_update.assert_called_once()
        update_call = mock_client.chat_update.call_args.kwargs
        assert update_call["text"] == "테스트 응답"

    async def test_handle_dm_saves_slack_ts_to_db(self):
        """DM 응답 후 slack_ts를 DB에 저장"""
        mock_db = MagicMock()
        mock_db.get_last_message_id = AsyncMock(return_value=99)
        mock_db.update_message_slack_ts = AsyncMock()

        mock_agent_fn = AsyncMock(return_value="응답")
        channel = SlackChannel(app=MagicMock(), agent_fn=mock_agent_fn, db=mock_db)

        mock_say = AsyncMock(return_value={"ts": "1111.2222"})
        mock_client = AsyncMock()

        await channel.handle_dm(
            event={"channel": "D001", "user": "U001", "text": "안녕"},
            say=mock_say,
            client=mock_client,
        )

        mock_db.get_last_message_id.assert_called_once_with("slack:D001")
        mock_db.update_message_slack_ts.assert_called_once_with(99, "1111.2222")

    async def test_handle_reaction_added_x_deletes_message(self):
        """:x: 이모지 → Slack 메시지 삭제 + DB 삭제"""
        mock_db = MagicMock()
        mock_db.delete_message_pair_by_slack_ts = AsyncMock(return_value=True)

        channel = SlackChannel(app=MagicMock(), agent_fn=AsyncMock(), db=mock_db)
        mock_client = AsyncMock()

        await channel.handle_reaction_added(
            event={
                "reaction": "x",
                "item": {"type": "message", "channel": "D001", "ts": "1111.2222"},
                "item_user": "B_BOT",
            },
            client=mock_client,
            bot_user_id="B_BOT",
        )

        mock_client.chat_delete.assert_called_once_with(channel="D001", ts="1111.2222")
        mock_db.delete_message_pair_by_slack_ts.assert_called_once_with("1111.2222")

    async def test_handle_reaction_added_ignores_other_emojis(self):
        """:x: 외 이모지는 무시"""
        mock_db = MagicMock()
        mock_db.delete_message_pair_by_slack_ts = AsyncMock()

        channel = SlackChannel(app=MagicMock(), agent_fn=AsyncMock(), db=mock_db)
        mock_client = AsyncMock()

        await channel.handle_reaction_added(
            event={
                "reaction": "thumbsup",
                "item": {"type": "message", "channel": "D001", "ts": "1111.2222"},
                "item_user": "B_BOT",
            },
            client=mock_client,
            bot_user_id="B_BOT",
        )

        mock_client.chat_delete.assert_not_called()
        mock_db.delete_message_pair_by_slack_ts.assert_not_called()

    async def test_dm_help_returns_help_text_without_calling_agent(self):
        """/help 또는 help 입력 시 agent 호출 없이 도움말 반환"""
        channel, mock_app, mock_agent_fn = self._make_channel()
        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_dm(
            event={"channel": "D001", "user": "U001", "text": "/help"},
            say=mock_say,
            client=mock_client,
        )

        mock_agent_fn.assert_not_called()
        update_call = mock_client.chat_update.call_args.kwargs
        assert update_call["text"]

    async def test_mention_help_returns_help_text_without_calling_agent(self):
        """@bot /help 입력 시 agent 호출 없이 도움말 반환"""
        channel, mock_app, mock_agent_fn = self._make_channel()
        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_mention(
            event={"channel": "C001", "user": "U001", "text": "<@BOT> /help"},
            say=mock_say,
            client=mock_client,
            bot_user_id="BOT",
        )

        mock_agent_fn.assert_not_called()
        update_call = mock_client.chat_update.call_args.kwargs
        assert update_call["text"]

    async def test_help_keywords_all_recognized(self):
        """help, /help, 도움말, /도움말 모두 인식"""
        channel, _, _ = self._make_channel()
        for keyword in ["help", "/help", "도움말", "/도움말", "HELP", " /help "]:
            assert channel._is_help_request(keyword), f"'{keyword}'가 help로 인식되지 않음"

    async def test_handle_mention_passes_progress_callback_to_agent(self):
        """handle_mention이 agent_fn에 progress_callback을 전달한다."""
        received_callback = []

        async def capturing_agent_fn(**kwargs):
            received_callback.append(kwargs.get("progress_callback"))
            return "응답"

        channel = SlackChannel(app=MagicMock(), agent_fn=capturing_agent_fn)
        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_mention(
            event={"channel": "C001", "user": "U001", "text": "<@BOT> 검색해줘"},
            say=mock_say,
            client=mock_client,
            bot_user_id="BOT",
        )

        assert received_callback[0] is not None

    async def test_handle_mention_updates_message_on_tool_call(self):
        """progress_callback 호출 시 메시지가 tool 상태로 업데이트된다."""
        async def agent_fn_with_tool(**kwargs):
            cb = kwargs.get("progress_callback")
            if cb:
                await cb("web_search")
            return "최종 응답"

        channel = SlackChannel(app=MagicMock(), agent_fn=agent_fn_with_tool)
        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_mention(
            event={"channel": "C001", "user": "U001", "text": "<@BOT> 검색해줘"},
            say=mock_say,
            client=mock_client,
            bot_user_id="BOT",
        )

        assert mock_client.chat_update.call_count >= 2
        first_update_text = mock_client.chat_update.call_args_list[0].kwargs["text"]
        assert "web_search" in first_update_text

    async def test_handle_dm_passes_progress_callback_to_agent(self):
        """handle_dm이 agent_fn에 progress_callback을 전달한다."""
        received_callback = []

        async def capturing_agent_fn(**kwargs):
            received_callback.append(kwargs.get("progress_callback"))
            return "응답"

        channel = SlackChannel(app=MagicMock(), agent_fn=capturing_agent_fn)
        mock_say = AsyncMock(return_value={"ts": "1234.5678"})
        mock_client = AsyncMock()

        await channel.handle_dm(
            event={"channel": "D001", "user": "U001", "text": "검색해줘"},
            say=mock_say,
            client=mock_client,
        )

        assert received_callback[0] is not None

    async def test_handle_reaction_added_ignores_non_bot_messages(self):
        """:x: 이모지라도 봇 메시지가 아니면 무시"""
        mock_db = MagicMock()
        mock_db.delete_message_pair_by_slack_ts = AsyncMock()

        channel = SlackChannel(app=MagicMock(), agent_fn=AsyncMock(), db=mock_db)
        mock_client = AsyncMock()

        await channel.handle_reaction_added(
            event={
                "reaction": "x",
                "item": {"type": "message", "channel": "D001", "ts": "1111.2222"},
                "item_user": "U_OTHER_USER",
            },
            client=mock_client,
            bot_user_id="B_BOT",
        )

        mock_client.chat_delete.assert_not_called()
