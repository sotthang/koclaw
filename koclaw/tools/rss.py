import asyncio
import re

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore[assignment]

from koclaw.core.prompt_guard import wrap_external_content
from koclaw.core.tool import Tool
from koclaw.tools.browse import _is_safe_url

MAX_SUMMARY_LENGTH = 200


class RssFeedTool(Tool):
    name = "rss_feed"
    description = (
        "RSS/Atom 피드에서 최신 글 목록을 가져옵니다. "
        "뉴스, 블로그, GitHub 릴리즈 등 RSS를 제공하는 모든 소스에서 사용할 수 있습니다. "
        "예: 해커뉴스(https://news.ycombinator.com/rss), 연합뉴스, GitHub 릴리즈 등"
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "RSS/Atom 피드 URL"},
            "limit": {
                "type": "integer",
                "description": "가져올 최대 항목 수 (기본값: 10)",
                "default": 10,
            },
        },
        "required": ["url"],
    }
    is_sandboxed = False

    async def execute(self, url: str, limit: int = 10) -> str:
        if not _is_safe_url(url):
            return "오류: 이 URL에 접근할 수 없습니다 (내부 네트워크 또는 허용되지 않는 프로토콜)"

        if feedparser is None:
            return "RSS 읽기 불가: feedparser 패키지가 설치되지 않았습니다. (pip install feedparser)"

        try:
            feed = await asyncio.to_thread(feedparser.parse, url)
        except Exception as e:
            return f"RSS 피드 읽기 오류: {e}"

        if feed.bozo and not feed.entries:
            return f"RSS 피드를 읽을 수 없습니다: {feed.bozo_exception}"

        if not feed.entries:
            return "피드에 항목이 없습니다."

        feed_title = getattr(feed.feed, "title", url)
        entries = feed.entries[:limit]

        lines = [f"📡 {feed_title} ({len(entries)}개 항목)\n"]
        for i, entry in enumerate(entries, 1):
            title = getattr(entry, "title", "(제목 없음)")
            link = getattr(entry, "link", "")
            published = getattr(entry, "published", "")
            summary = entry.get("summary", "") or entry.get("description", "")

            if summary:
                summary = re.sub(r"<[^>]+>", "", summary).strip()
                if len(summary) > MAX_SUMMARY_LENGTH:
                    summary = summary[:MAX_SUMMARY_LENGTH] + "..."

            item = f"{i}. {title}"
            if published:
                item += f" ({published})"
            if link:
                item += f"\n   {link}"
            if summary:
                item += f"\n   {summary}"
            lines.append(item)

        content = "\n\n".join(lines)
        return wrap_external_content(f"RSS: {feed_title}", content)
