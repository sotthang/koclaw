from unittest.mock import AsyncMock, patch

import pytest

from koclaw.tools.email import EmailTool, _is_valid_email


@pytest.fixture
def tool():
    return EmailTool()


# ── 정상 전송 ─────────────────────────────────────────────────────────────────


async def test_sends_email_successfully(tool):
    with patch.dict(
        "os.environ", {"GMAIL_USER": "sender@gmail.com", "GMAIL_APP_PASSWORD": "testpass"}
    ):
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            result = await tool.execute(
                to="recipient@example.com",
                subject="테스트 제목",
                body="테스트 본문입니다.",
            )

    assert "✅" in result
    assert "recipient@example.com" in result
    mock_send.assert_called_once()


async def test_smtp_called_with_correct_params(tool):
    with patch.dict(
        "os.environ", {"GMAIL_USER": "sender@gmail.com", "GMAIL_APP_PASSWORD": "secret"}
    ):
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            await tool.execute(
                to="someone@example.com",
                subject="제목",
                body="본문",
            )

    _, kwargs = mock_send.call_args
    assert kwargs["hostname"] == "smtp.gmail.com"
    assert kwargs["port"] == 587
    assert kwargs["username"] == "sender@gmail.com"
    assert kwargs["password"] == "secret"
    assert kwargs["start_tls"] is True


# ── 환경변수 미설정 ───────────────────────────────────────────────────────────


async def test_returns_error_when_gmail_user_missing(tool):
    with patch.dict("os.environ", {"GMAIL_APP_PASSWORD": "testpass"}, clear=False):
        import os

        original = os.environ.pop("GMAIL_USER", None)
        try:
            result = await tool.execute(
                to="recipient@example.com",
                subject="제목",
                body="본문",
            )
        finally:
            if original is not None:
                os.environ["GMAIL_USER"] = original

    assert "오류" in result
    assert "GMAIL_USER" in result


async def test_returns_error_when_env_not_set(tool):
    env_patch = {"GMAIL_USER": "", "GMAIL_APP_PASSWORD": ""}
    with patch.dict("os.environ", env_patch):
        result = await tool.execute(
            to="recipient@example.com",
            subject="제목",
            body="본문",
        )

    assert "오류" in result


# ── 이메일 주소 유효성 검사 ───────────────────────────────────────────────────


async def test_returns_error_for_invalid_email(tool):
    with patch.dict(
        "os.environ", {"GMAIL_USER": "sender@gmail.com", "GMAIL_APP_PASSWORD": "testpass"}
    ):
        result = await tool.execute(
            to="not-an-email",
            subject="제목",
            body="본문",
        )

    assert "오류" in result
    assert "not-an-email" in result


async def test_returns_error_for_email_without_domain(tool):
    with patch.dict(
        "os.environ", {"GMAIL_USER": "sender@gmail.com", "GMAIL_APP_PASSWORD": "testpass"}
    ):
        result = await tool.execute(
            to="user@",
            subject="제목",
            body="본문",
        )

    assert "오류" in result


# ── SMTP 전송 실패 ────────────────────────────────────────────────────────────


async def test_returns_error_on_smtp_failure(tool):
    with patch.dict(
        "os.environ", {"GMAIL_USER": "sender@gmail.com", "GMAIL_APP_PASSWORD": "testpass"}
    ):
        with patch("aiosmtplib.send", side_effect=Exception("연결 실패")):
            result = await tool.execute(
                to="recipient@example.com",
                subject="제목",
                body="본문",
            )

    assert "오류" in result
    assert "연결 실패" in result


# ── Tool 속성 ─────────────────────────────────────────────────────────────────


def test_is_not_sandboxed(tool):
    assert tool.is_sandboxed is False


def test_tool_name(tool):
    assert tool.name == "send_email"


def test_has_required_parameters(tool):
    required = tool.parameters["required"]
    assert "to" in required
    assert "subject" in required
    assert "body" in required


# ── 이메일 유효성 헬퍼 ────────────────────────────────────────────────────────


def test_valid_email_formats():
    assert _is_valid_email("user@example.com") is True
    assert _is_valid_email("user.name+tag@sub.domain.co.kr") is True


def test_invalid_email_formats():
    assert _is_valid_email("not-an-email") is False
    assert _is_valid_email("missing@tld") is False
    assert _is_valid_email("@nodomain.com") is False
    assert _is_valid_email("spaces in@email.com") is False
