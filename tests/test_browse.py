from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koclaw.tools.browse import BrowseTool


@pytest.fixture
def tool():
    return BrowseTool()


async def test_returns_page_text(tool):
    html = "<html><body><p>안녕하세요</p><p>테스트 페이지입니다</p></body></html>"
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute(url="https://example.com")

    assert "안녕하세요" in result
    assert "테스트 페이지입니다" in result


async def test_wraps_with_prompt_guard(tool):
    html = "<html><body><p>내용</p></body></html>"
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute(url="https://example.com")

    assert "[외부 데이터 시작:" in result
    assert "[외부 데이터 끝:" in result


async def test_strips_script_and_style_tags(tool):
    html = """<html><body>
        <script>alert('xss')</script>
        <style>body { color: red; }</style>
        <p>실제 내용</p>
    </body></html>"""
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute(url="https://example.com")

    assert "alert" not in result
    assert "color: red" not in result
    assert "실제 내용" in result


async def test_returns_error_on_http_failure(tool):
    import httpx

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("연결 실패"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute(url="https://example.com")

    assert "오류" in result


async def test_is_not_sandboxed(tool):
    assert tool.is_sandboxed is False


# ── SSRF 방어 ─────────────────────────────────────────────────────────────────

async def test_blocks_localhost(tool):
    result = await tool.execute(url="http://localhost/admin")
    assert "접근할 수 없습니다" in result


async def test_blocks_loopback_ip(tool):
    result = await tool.execute(url="http://127.0.0.1/etc/passwd")
    assert "접근할 수 없습니다" in result


async def test_blocks_private_ip_class_a(tool):
    result = await tool.execute(url="http://10.0.0.1/admin")
    assert "접근할 수 없습니다" in result


async def test_blocks_private_ip_class_b(tool):
    result = await tool.execute(url="http://172.16.0.1/admin")
    assert "접근할 수 없습니다" in result


async def test_blocks_private_ip_class_c(tool):
    result = await tool.execute(url="http://192.168.1.1/admin")
    assert "접근할 수 없습니다" in result


async def test_blocks_file_scheme(tool):
    result = await tool.execute(url="file:///etc/passwd")
    assert "접근할 수 없습니다" in result


async def test_blocks_non_http_scheme(tool):
    result = await tool.execute(url="ftp://example.com/file")
    assert "접근할 수 없습니다" in result


async def test_allows_public_https(tool):
    html = "<html><body><p>공개 내용</p></body></html>"
    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute(url="https://example.com")

    assert "공개 내용" in result
