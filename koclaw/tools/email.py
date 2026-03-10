import os
import re
from email.message import EmailMessage

from koclaw.core.tool import Tool


class EmailTool(Tool):
    name = "send_email"
    description = (
        "이메일을 전송합니다. "
        "보고서 전달, 요약 결과 공유, 알림 발송 등에 활용하세요. "
        "Gmail SMTP를 사용하며 .env에 GMAIL_USER와 GMAIL_APP_PASSWORD가 필요합니다."
    )
    parameters = {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "수신자 이메일 주소 (예: user@example.com)",
            },
            "subject": {
                "type": "string",
                "description": "이메일 제목",
            },
            "body": {
                "type": "string",
                "description": "이메일 본문 내용",
            },
        },
        "required": ["to", "subject", "body"],
    }
    is_sandboxed = False

    async def execute(self, to: str, subject: str, body: str) -> str:
        try:
            import aiosmtplib
        except ImportError:
            return (
                "오류: aiosmtplib이 설치되지 않았습니다. "
                "`uv sync --all-extras` 또는 `pip install 'koclaw[email]'`을 실행하세요."
            )

        gmail_user = os.getenv("GMAIL_USER")
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")

        if not gmail_user or not gmail_password:
            return (
                "오류: 이메일 설정이 없습니다. "
                ".env 파일에 GMAIL_USER와 GMAIL_APP_PASSWORD를 설정하세요."
            )

        if not _is_valid_email(to):
            return f"오류: 올바르지 않은 이메일 주소입니다: {to}"

        msg = EmailMessage()
        msg["From"] = gmail_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        try:
            await aiosmtplib.send(
                msg,
                hostname="smtp.gmail.com",
                port=587,
                username=gmail_user,
                password=gmail_password,
                start_tls=True,
            )
        except Exception as e:
            return f"오류: 이메일 전송에 실패했습니다 — {e}"

        return f"✅ 이메일이 전송되었습니다: {to}"


def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))
