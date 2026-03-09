from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from koclaw.channels.discord import DiscordChannel, _discord_file_fetcher, parse_discord_message


def make_message(
    *,
    content="안녕",
    author_id=111,
    bot_user_id=999,
    guild=True,
    mentions=None,
    attachments=None,
    is_thread=False,
    channel_id=42,
    thread_id=77,
    parent_channel_id=42,
):
    msg = MagicMock()
    msg.content = content
    msg.author.id = author_id
    msg.author.bot = author_id == bot_user_id
    msg.guild = MagicMock() if guild else None
    msg.attachments = attachments or []

    if mentions is not None:
        msg.mentions = mentions
    else:
        msg.mentions = []

    if is_thread:
        msg.channel = MagicMock()
        msg.channel.id = thread_id
        msg.channel.parent_id = parent_channel_id
        msg.channel.__class__.__name__ = "Thread"
        msg.channel.send = AsyncMock(return_value=MagicMock(edit=AsyncMock()))
    else:
        msg.channel = MagicMock()
        msg.channel.id = channel_id
        msg.channel.__class__.__name__ = "TextChannel"
        msg.channel.send = AsyncMock(return_value=MagicMock(edit=AsyncMock()))

    return msg


# --- parse_discord_message ---

def test_parse_removes_bot_mention():
    bot = MagicMock()
    bot.id = 999
    msg = make_message(content="<@999> 안녕", mentions=[bot])
    parsed = parse_discord_message(msg, bot_user_id=999)
    assert parsed["text"] == "안녕"


def test_parse_session_id_dm():
    msg = make_message(guild=False, author_id=123)
    parsed = parse_discord_message(msg, bot_user_id=999)
    assert parsed["session_id"] == "discord:dm:123"


def test_parse_session_id_channel():
    msg = make_message(guild=True, channel_id=42, is_thread=False)
    parsed = parse_discord_message(msg, bot_user_id=999)
    assert parsed["session_id"] == "discord:42"


def test_parse_session_id_thread():
    msg = make_message(guild=True, is_thread=True, thread_id=77, parent_channel_id=42)
    parsed = parse_discord_message(msg, bot_user_id=999)
    assert parsed["session_id"] == "discord:thread:42:77"


def test_parse_attachments():
    att = MagicMock()
    att.filename = "test.pdf"
    att.url = "https://cdn.discord.com/test.pdf"
    msg = make_message(attachments=[att])
    parsed = parse_discord_message(msg, bot_user_id=999)
    assert parsed["files"] == [{"name": "test.pdf", "url": "https://cdn.discord.com/test.pdf"}]


# --- DiscordChannel.should_handle ---

def test_ignores_own_message():
    channel = DiscordChannel(agent_fn=AsyncMock())
    msg = make_message(author_id=999)
    assert channel.should_handle(msg, bot_user_id=999) is False


def test_handles_channel_message_without_mention():
    channel = DiscordChannel(agent_fn=AsyncMock())
    msg = make_message(guild=True, mentions=[])
    assert channel.should_handle(msg, bot_user_id=999) is True


def test_handles_dm():
    channel = DiscordChannel(agent_fn=AsyncMock())
    msg = make_message(guild=False, author_id=123)
    assert channel.should_handle(msg, bot_user_id=999) is True


def test_handles_mention():
    bot = MagicMock()
    bot.id = 999
    channel = DiscordChannel(agent_fn=AsyncMock())
    msg = make_message(guild=True, mentions=[bot])
    assert channel.should_handle(msg, bot_user_id=999) is True


# --- DiscordChannel.handle_message ---

async def test_handle_message_calls_agent():
    agent_fn = AsyncMock(return_value="응답입니다")
    channel = DiscordChannel(agent_fn=agent_fn)
    msg = make_message(content="질문", guild=False, author_id=123)

    await channel.handle_message(msg, bot_user_id=999)

    agent_fn.assert_called_once()
    call_kwargs = agent_fn.call_args.kwargs
    assert call_kwargs["user_message"] == "질문"
    assert call_kwargs["session_id"] == "discord:dm:123"
    assert call_kwargs["user_id"] == 123


async def test_handle_message_passes_files_to_agent():
    """첨부파일이 agent_fn에 전달되는지 확인"""
    agent_fn = AsyncMock(return_value="파일 분석 완료")
    channel = DiscordChannel(agent_fn=agent_fn)

    att = MagicMock()
    att.filename = "report.pdf"
    att.url = "https://cdn.discordapp.com/report.pdf"
    msg = make_message(guild=False, author_id=123, attachments=[att])

    await channel.handle_message(msg, bot_user_id=999)

    call_kwargs = agent_fn.call_args.kwargs
    assert call_kwargs["files"] == [{"name": "report.pdf", "url": "https://cdn.discordapp.com/report.pdf"}]


async def test_handle_message_edits_with_response():
    agent_fn = AsyncMock(return_value="최종 응답")
    channel = DiscordChannel(agent_fn=agent_fn)
    msg = make_message(guild=False, author_id=123)
    thinking_msg = MagicMock(edit=AsyncMock())
    msg.channel.send = AsyncMock(return_value=thinking_msg)

    await channel.handle_message(msg, bot_user_id=999)

    thinking_msg.edit.assert_called_once_with(content="최종 응답")


async def test_handle_message_calls_agent_for_channel_without_mention():
    agent_fn = AsyncMock(return_value="채널 응답")
    channel = DiscordChannel(agent_fn=agent_fn)
    msg = make_message(guild=True, mentions=[], content="질문이요")

    await channel.handle_message(msg, bot_user_id=999)

    agent_fn.assert_called_once()


async def test_handle_reaction_x_deletes_bot_message():
    """:x: 반응 → 봇 메시지 삭제"""
    channel = DiscordChannel(agent_fn=AsyncMock())

    mock_message = AsyncMock()
    mock_message.author.id = 999  # bot

    mock_channel = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)

    mock_client = MagicMock()
    mock_client.get_channel = MagicMock(return_value=mock_channel)

    payload = MagicMock()
    payload.emoji.name = "❌"
    payload.channel_id = 42
    payload.message_id = 1234

    await channel.handle_reaction_added(payload, client=mock_client, bot_user_id=999)

    mock_message.delete.assert_called_once()


async def test_handle_reaction_x_ignores_non_bot_message():
    """:x: 반응이라도 봇 메시지 아니면 무시"""
    channel = DiscordChannel(agent_fn=AsyncMock())

    mock_message = AsyncMock()
    mock_message.author.id = 111  # not bot

    mock_channel = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_message)

    mock_client = MagicMock()
    mock_client.get_channel = MagicMock(return_value=mock_channel)

    payload = MagicMock()
    payload.emoji.name = "❌"
    payload.channel_id = 42
    payload.message_id = 1234

    await channel.handle_reaction_added(payload, client=mock_client, bot_user_id=999)

    mock_message.delete.assert_not_called()


async def test_handle_reaction_ignores_other_emojis():
    """:x: 외 이모지는 무시"""
    channel = DiscordChannel(agent_fn=AsyncMock())

    mock_client = MagicMock()

    payload = MagicMock()
    payload.emoji.name = "👍"

    await channel.handle_reaction_added(payload, client=mock_client, bot_user_id=999)

    mock_client.get_channel.assert_not_called()


async def test_handle_message_returns_error_on_exception():
    agent_fn = AsyncMock(side_effect=RuntimeError("LLM 오류"))
    channel = DiscordChannel(agent_fn=agent_fn)
    msg = make_message(guild=False, author_id=123)
    thinking_msg = MagicMock(edit=AsyncMock())
    msg.channel.send = AsyncMock(return_value=thinking_msg)

    await channel.handle_message(msg, bot_user_id=999)

    edit_content = thinking_msg.edit.call_args.kwargs["content"]
    assert "오류" in edit_content


async def test_handle_message_passes_progress_callback_to_agent():
    """agent_fn에 progress_callback이 전달된다."""
    received_callback = []

    async def capturing_agent_fn(**kwargs):
        received_callback.append(kwargs.get("progress_callback"))
        return "응답"

    channel = DiscordChannel(agent_fn=capturing_agent_fn)
    msg = make_message(guild=False, author_id=123)

    await channel.handle_message(msg, bot_user_id=999)

    assert received_callback[0] is not None


async def test_handle_message_updates_thinking_on_tool_call():
    """progress_callback 호출 시 thinking 메시지가 tool 상태로 업데이트된다."""
    async def agent_fn_with_tool(**kwargs):
        cb = kwargs.get("progress_callback")
        if cb:
            await cb("web_search")
        return "최종 응답"

    channel = DiscordChannel(agent_fn=agent_fn_with_tool)
    msg = make_message(guild=False, author_id=123)
    thinking_msg = MagicMock(edit=AsyncMock())
    msg.channel.send = AsyncMock(return_value=thinking_msg)

    await channel.handle_message(msg, bot_user_id=999)

    assert thinking_msg.edit.call_count >= 2
    first_edit_content = thinking_msg.edit.call_args_list[0].kwargs["content"]
    assert "web_search" in first_edit_content


# ── Discord file_fetcher SSRF 방어 ────────────────────────────────────────────

async def test_discord_file_fetcher_blocks_private_ip():
    """사설 IP URL은 ValueError를 발생시킨다."""
    with pytest.raises(ValueError, match="허용되지 않는 URL"):
        await _discord_file_fetcher("http://192.168.1.1/file.pdf")


async def test_discord_file_fetcher_blocks_localhost():
    """localhost URL은 ValueError를 발생시킨다."""
    with pytest.raises(ValueError, match="허용되지 않는 URL"):
        await _discord_file_fetcher("http://localhost/secret")


async def test_discord_file_fetcher_allows_public_url():
    """공개 URL은 정상 다운로드된다."""
    mock_response = MagicMock()
    mock_response.content = b"file data"
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _discord_file_fetcher("https://cdn.discordapp.com/attachments/file.pdf")

    assert result == b"file data"


async def test_handle_help_command():
    agent_fn = AsyncMock()
    channel = DiscordChannel(agent_fn=agent_fn)
    msg = make_message(content="help", guild=False, author_id=123)
    thinking_msg = MagicMock(edit=AsyncMock())
    msg.channel.send = AsyncMock(return_value=thinking_msg)

    await channel.handle_message(msg, bot_user_id=999)

    agent_fn.assert_not_called()
    edit_content = thinking_msg.edit.call_args.kwargs["content"]
    assert "koclaw" in edit_content
