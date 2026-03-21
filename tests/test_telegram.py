from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koclaw.channels.telegram import (
    TelegramChannel,
    _telegram_file_fetcher,
    parse_telegram_update,
)


def make_update(
    *,
    text="안녕",
    user_id=111,
    chat_id=42,
    chat_type="private",
    bot_user_id=999,
    message_thread_id=None,
    document=None,
    photo=None,
    entities=None,
    reply_to_user_id=None,
):
    update = MagicMock()
    message = MagicMock()
    update.effective_message = message

    message.text = text
    message.caption = None
    message.message_thread_id = message_thread_id
    message.document = document
    message.photo = photo or []
    message.entities = entities or []

    message.from_user = MagicMock()
    message.from_user.id = user_id

    message.chat = MagicMock()
    message.chat.id = chat_id
    message.chat.type = chat_type

    if reply_to_user_id is not None:
        message.reply_to_message = MagicMock()
        message.reply_to_message.from_user = MagicMock()
        message.reply_to_message.from_user.id = reply_to_user_id
    else:
        message.reply_to_message = None

    return update


# --- parse_telegram_update ---


def test_parse_session_id_private():
    update = make_update(chat_type="private", chat_id=123)
    parsed = parse_telegram_update(update, "testbot")
    assert parsed["session_id"] == "telegram:dm:123"


def test_parse_session_id_group():
    update = make_update(chat_type="supergroup", chat_id=-100)
    parsed = parse_telegram_update(update, "testbot")
    assert parsed["session_id"] == "telegram:-100"


def test_parse_session_id_topic():
    update = make_update(chat_type="supergroup", chat_id=-100, message_thread_id=5)
    parsed = parse_telegram_update(update, "testbot")
    assert parsed["session_id"] == "telegram:topic:-100:5"


def test_parse_removes_bot_mention():
    update = make_update(text="@testbot 질문이요", chat_type="supergroup")
    parsed = parse_telegram_update(update, "testbot")
    assert parsed["text"] == "질문이요"


def test_parse_document():
    doc = MagicMock()
    doc.file_name = "report.pdf"
    doc.file_id = "FILE123"
    update = make_update(document=doc, chat_type="private")
    parsed = parse_telegram_update(update, "testbot")
    assert parsed["files"] == [{"name": "report.pdf", "url": "tg-file://FILE123"}]


def test_parse_photo():
    small = MagicMock()
    small.file_id = "SMALL"
    small.file_size = 1000

    large = MagicMock()
    large.file_id = "LARGE"
    large.file_size = 9000

    update = make_update(photo=[small, large], chat_type="private")
    update.effective_message.text = None
    update.effective_message.caption = "사진"
    parsed = parse_telegram_update(update, "testbot")
    assert parsed["files"] == [{"name": "photo.jpg", "url": "tg-file://LARGE"}]


def test_parse_user_id():
    update = make_update(user_id=555, chat_type="private")
    parsed = parse_telegram_update(update, "testbot")
    assert parsed["user_id"] == 555


def test_parse_returns_none_for_no_message():
    update = MagicMock()
    update.effective_message = None
    assert parse_telegram_update(update, "testbot") is None


# --- TelegramChannel.should_handle ---


def test_ignores_own_message():
    channel = TelegramChannel(agent_fn=AsyncMock())
    update = make_update(user_id=999, chat_type="private")
    assert channel.should_handle(update, bot_user_id=999, bot_username="testbot") is False


def test_handles_private_message():
    channel = TelegramChannel(agent_fn=AsyncMock())
    update = make_update(user_id=111, chat_type="private")
    assert channel.should_handle(update, bot_user_id=999, bot_username="testbot") is True


def test_group_ignores_without_mention_or_reply():
    channel = TelegramChannel(agent_fn=AsyncMock())
    update = make_update(user_id=111, chat_type="supergroup", entities=[])
    assert channel.should_handle(update, bot_user_id=999, bot_username="testbot") is False


def test_group_handles_mention():
    channel = TelegramChannel(agent_fn=AsyncMock())
    entity = MagicMock()
    entity.type = "mention"
    entity.offset = 0
    entity.length = 8  # "@testbot" = 8자
    update = make_update(
        user_id=111,
        chat_type="supergroup",
        text="@testbot 안녕",
        entities=[entity],
    )
    assert channel.should_handle(update, bot_user_id=999, bot_username="testbot") is True


def test_group_handles_reply_to_bot():
    channel = TelegramChannel(agent_fn=AsyncMock())
    update = make_update(user_id=111, chat_type="supergroup", reply_to_user_id=999)
    assert channel.should_handle(update, bot_user_id=999, bot_username="testbot") is True


def test_group_ignores_reply_to_non_bot():
    channel = TelegramChannel(agent_fn=AsyncMock())
    update = make_update(user_id=111, chat_type="supergroup", reply_to_user_id=333)
    assert channel.should_handle(update, bot_user_id=999, bot_username="testbot") is False


# --- TelegramChannel.handle_message ---


def make_context(bot_id=999, bot_username="testbot"):
    context = MagicMock()
    context.bot = AsyncMock()
    context.bot.id = bot_id
    context.bot.username = bot_username
    thinking = AsyncMock()
    thinking.edit_text = AsyncMock()
    context.bot.send_message = AsyncMock(return_value=thinking)
    return context, thinking


async def test_handle_message_calls_agent():
    agent_fn = AsyncMock(return_value="응답입니다")
    channel = TelegramChannel(agent_fn=agent_fn)
    update = make_update(text="질문", user_id=111, chat_id=123, chat_type="private")
    context, thinking = make_context()

    await channel.handle_message(update, context)

    agent_fn.assert_called_once()
    kwargs = agent_fn.call_args.kwargs
    assert kwargs["user_message"] == "질문"
    assert kwargs["session_id"] == "telegram:dm:123"
    assert kwargs["user_id"] == "111"


async def test_handle_message_edits_with_response():
    agent_fn = AsyncMock(return_value="최종 응답")
    channel = TelegramChannel(agent_fn=agent_fn)
    update = make_update(chat_type="private")
    context, thinking = make_context()

    await channel.handle_message(update, context)

    thinking.edit_text.assert_called()
    last_call = thinking.edit_text.call_args_list[-1]
    assert "최종 응답" in str(last_call)


async def test_handle_message_returns_error_on_exception():
    agent_fn = AsyncMock(side_effect=RuntimeError("LLM 오류"))
    channel = TelegramChannel(agent_fn=agent_fn)
    update = make_update(chat_type="private")
    context, thinking = make_context()

    await channel.handle_message(update, context)

    last_call = thinking.edit_text.call_args_list[-1]
    assert "오류" in str(last_call)


async def test_handle_help_command():
    agent_fn = AsyncMock()
    channel = TelegramChannel(agent_fn=agent_fn)
    update = make_update(text="help", chat_type="private")
    context, thinking = make_context()

    await channel.handle_message(update, context)

    agent_fn.assert_not_called()
    thinking.edit_text.assert_called_once()
    call_args = thinking.edit_text.call_args
    assert "koclaw" in str(call_args)


async def test_handle_message_passes_progress_callback():
    received = []

    async def capturing_agent_fn(**kwargs):
        received.append(kwargs.get("progress_callback"))
        return "응답"

    channel = TelegramChannel(agent_fn=capturing_agent_fn)
    update = make_update(chat_type="private")
    context, _ = make_context()

    await channel.handle_message(update, context)

    assert received[0] is not None


async def test_handle_message_updates_thinking_on_tool_call():
    async def agent_fn_with_tool(**kwargs):
        cb = kwargs.get("progress_callback")
        if cb:
            await cb("web_search")
        return "최종 응답"

    channel = TelegramChannel(agent_fn=agent_fn_with_tool)
    update = make_update(chat_type="private")
    context, thinking = make_context()

    await channel.handle_message(update, context)

    assert thinking.edit_text.call_count >= 2
    first_call_text = str(thinking.edit_text.call_args_list[0])
    assert "web_search" in first_call_text


async def test_handle_message_ignored_in_group_without_mention():
    agent_fn = AsyncMock()
    channel = TelegramChannel(agent_fn=agent_fn)
    update = make_update(text="아무 말", chat_type="supergroup", entities=[])
    context, _ = make_context()

    await channel.handle_message(update, context)

    agent_fn.assert_not_called()


# --- _telegram_file_fetcher ---


async def test_telegram_file_fetcher_tg_scheme():
    """tg-file:// 스킴은 bot.get_file()을 사용한다."""
    mock_bot = AsyncMock()
    mock_tg_file = AsyncMock()
    mock_tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"file data"))
    mock_bot.get_file = AsyncMock(return_value=mock_tg_file)

    result = await _telegram_file_fetcher("tg-file://FILE123", mock_bot)

    mock_bot.get_file.assert_called_once_with("FILE123")
    assert result == b"file data"


async def test_telegram_file_fetcher_blocks_private_ip():
    """사설 IP URL은 ValueError를 발생시킨다."""
    mock_bot = AsyncMock()
    with pytest.raises(ValueError, match="허용되지 않는 URL"):
        await _telegram_file_fetcher("http://192.168.1.1/file.pdf", mock_bot)


async def test_telegram_file_fetcher_blocks_localhost():
    """localhost URL은 ValueError를 발생시킨다."""
    mock_bot = AsyncMock()
    with pytest.raises(ValueError, match="허용되지 않는 URL"):
        await _telegram_file_fetcher("http://localhost/secret", mock_bot)


async def test_telegram_file_fetcher_allows_public_url():
    """공개 URL은 정상 다운로드된다."""
    mock_bot = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = b"public file"
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _telegram_file_fetcher("https://example.com/file.pdf", mock_bot)

    assert result == b"public file"
