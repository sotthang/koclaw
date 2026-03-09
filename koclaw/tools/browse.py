import ipaddress
from urllib.parse import urlparse

import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[assignment,misc]

from koclaw.core.prompt_guard import wrap_external_content
from koclaw.core.tool import Tool

TIMEOUT = 15.0
USER_AGENT = "Mozilla/5.0 (compatible; koclaw-bot/1.0)"
_ALLOWED_SCHEMES = {"http", "https"}


def _is_safe_url(url: str) -> bool:
    """SSRF 방어: 내부 네트워크 및 비허용 프로토콜 차단."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    if hostname.lower() in ("localhost", "localhost.localdomain"):
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass  # 도메인명인 경우 — DNS 조회는 하지 않음

    return True


class BrowseTool(Tool):
    name = "browse"
    description = "URL의 웹페이지 내용을 읽어옵니다. 특정 페이지의 전체 내용이 필요할 때 사용하세요."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "읽을 웹페이지 URL"},
        },
        "required": ["url"],
    }
    is_sandboxed = False

    async def execute(self, url: str) -> str:
        if not _is_safe_url(url):
            return "오류: 이 URL에 접근할 수 없습니다 (내부 네트워크 또는 허용되지 않는 프로토콜)"

        if BeautifulSoup is None:
            return "웹 스크래핑 불가: beautifulsoup4 패키지가 설치되지 않았습니다. (pip install beautifulsoup4)"
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=TIMEOUT,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as e:
            return f"페이지 읽기 오류: {e}"

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # 연속 빈 줄 정리
        lines = [line for line in text.splitlines() if line.strip()]
        content = "\n".join(lines)

        return wrap_external_content(f"웹페이지: {url}", content)
