from unittest.mock import MagicMock, patch

from koclaw.tools.rss import RssFeedTool


def _make_feed(title: str, entries: list, bozo: bool = False, bozo_exception=None) -> MagicMock:
    feed = MagicMock()
    feed.feed.title = title
    feed.bozo = bozo
    feed.bozo_exception = bozo_exception
    feed.entries = entries
    return feed


def _make_entry(title: str, link: str, summary: str = "", published: str = "") -> MagicMock:
    entry = MagicMock()
    entry.title = title
    entry.link = link
    entry.published = published
    entry.get = lambda key, default="": {"summary": summary, "description": ""}.get(key, default)
    return entry


class TestRssFeedToolBasic:
    async def test_returns_feed_title_and_entries(self):
        """피드 제목과 항목 제목·URL이 결과에 포함된다."""
        entry = _make_entry("Great Article", "https://example.com/article")
        mock_feed = _make_feed("Hacker News", [entry])

        with patch("feedparser.parse", return_value=mock_feed):
            tool = RssFeedTool()
            result = await tool.execute(url="https://news.ycombinator.com/rss")

        assert "Hacker News" in result
        assert "Great Article" in result
        assert "https://example.com/article" in result

    async def test_respects_limit(self):
        """limit 개수만큼만 항목을 반환한다."""
        entries = [_make_entry(f"Article {i}", f"https://example.com/{i}") for i in range(10)]
        mock_feed = _make_feed("Test Feed", entries)

        with patch("feedparser.parse", return_value=mock_feed):
            tool = RssFeedTool()
            result = await tool.execute(url="https://example.com/rss", limit=3)

        assert "Article 0" in result
        assert "Article 1" in result
        assert "Article 2" in result
        assert "Article 3" not in result

    async def test_default_limit_is_10(self):
        """기본 limit은 10이다."""
        entries = [_make_entry(f"Article {i}", f"https://example.com/{i}") for i in range(15)]
        mock_feed = _make_feed("Test Feed", entries)

        with patch("feedparser.parse", return_value=mock_feed):
            tool = RssFeedTool()
            result = await tool.execute(url="https://example.com/rss")

        assert "Article 9" in result
        assert "Article 10" not in result

    async def test_includes_summary_when_available(self):
        """요약이 있으면 결과에 포함한다."""
        entry = _make_entry("Article", "https://example.com", summary="이 글의 요약입니다.")
        mock_feed = _make_feed("Feed", [entry])

        with patch("feedparser.parse", return_value=mock_feed):
            tool = RssFeedTool()
            result = await tool.execute(url="https://example.com/rss")

        assert "이 글의 요약입니다." in result

    async def test_wraps_content_with_external_label(self):
        """결과가 외부 데이터 래핑으로 감싸진다 (프롬프트 인젝션 방어)."""
        entry = _make_entry("Article", "https://example.com")
        mock_feed = _make_feed("Feed", [entry])

        with patch("feedparser.parse", return_value=mock_feed):
            tool = RssFeedTool()
            result = await tool.execute(url="https://example.com/rss")

        assert "[외부 데이터 시작:" in result
        assert "[외부 데이터 끝:" in result


class TestRssFeedToolErrorHandling:
    async def test_empty_feed_returns_info_message(self):
        """피드에 항목이 없으면 안내 메시지를 반환한다."""
        mock_feed = _make_feed("Empty Feed", entries=[])

        with patch("feedparser.parse", return_value=mock_feed):
            tool = RssFeedTool()
            result = await tool.execute(url="https://example.com/rss")

        assert "없" in result or "항목" in result

    async def test_bozo_feed_with_no_entries_returns_error(self):
        """bozo=True이고 항목이 없으면 오류 메시지를 반환한다."""
        mock_feed = _make_feed("Bad Feed", entries=[], bozo=True,
                               bozo_exception=Exception("Connection failed"))

        with patch("feedparser.parse", return_value=mock_feed):
            tool = RssFeedTool()
            result = await tool.execute(url="https://invalid.example.com/rss")

        assert "오류" in result or "읽을 수 없" in result

    async def test_bozo_feed_with_entries_still_returns_content(self):
        """bozo=True라도 항목이 있으면 내용을 반환한다 (일부 피드는 bozo이지만 정상)."""
        entry = _make_entry("Article", "https://example.com")
        mock_feed = _make_feed("Feed", [entry], bozo=True,
                               bozo_exception=Exception("Minor warning"))

        with patch("feedparser.parse", return_value=mock_feed):
            tool = RssFeedTool()
            result = await tool.execute(url="https://example.com/rss")

        assert "Article" in result

    async def test_feedparser_not_installed_returns_error(self):
        """feedparser 미설치 시 안내 메시지를 반환한다."""
        import koclaw.tools.rss as rss_module
        original = rss_module.feedparser

        try:
            rss_module.feedparser = None
            tool = RssFeedTool()
            result = await tool.execute(url="https://example.com/rss")
        finally:
            rss_module.feedparser = original

        assert "feedparser" in result

    async def test_exception_during_parse_returns_error(self):
        """파싱 중 예외 발생 시 오류 메시지를 반환한다."""
        with patch("feedparser.parse", side_effect=OSError("네트워크 오류")):
            tool = RssFeedTool()
            result = await tool.execute(url="https://example.com/rss")

        assert "오류" in result


class TestRssSsrfDefense:
    async def test_blocks_private_ip_url(self):
        """사설 IP URL은 차단한다."""
        tool = RssFeedTool()
        result = await tool.execute(url="http://192.168.1.1/feed.xml")
        assert "접근할 수 없습니다" in result or "차단" in result or "허용" in result

    async def test_blocks_localhost_url(self):
        """localhost URL은 차단한다."""
        tool = RssFeedTool()
        result = await tool.execute(url="http://localhost/rss")
        assert "접근할 수 없습니다" in result or "차단" in result or "허용" in result

    async def test_blocks_loopback_ip(self):
        """루프백 IP URL은 차단한다."""
        tool = RssFeedTool()
        result = await tool.execute(url="http://127.0.0.1/rss")
        assert "접근할 수 없습니다" in result or "차단" in result or "허용" in result

    async def test_allows_public_url(self):
        """공개 URL은 feedparser로 정상 전달된다."""
        entry = _make_entry("Article", "https://example.com")
        mock_feed = _make_feed("Feed", [entry])

        with patch("feedparser.parse", return_value=mock_feed):
            tool = RssFeedTool()
            result = await tool.execute(url="https://news.ycombinator.com/rss")

        assert "Article" in result


class TestRssFeedToolMetadata:
    def test_tool_name(self):
        assert RssFeedTool.name == "rss_feed"

    def test_tool_is_not_sandboxed(self):
        assert RssFeedTool.is_sandboxed is False

    def test_tool_has_url_parameter(self):
        params = RssFeedTool.parameters
        assert "url" in params["properties"]
        assert "url" in params["required"]

    def test_tool_has_limit_parameter(self):
        params = RssFeedTool.parameters
        assert "limit" in params["properties"]
