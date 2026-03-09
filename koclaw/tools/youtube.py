import asyncio
import re

from youtube_transcript_api import YouTubeTranscriptApi

from koclaw.core.prompt_guard import wrap_external_content
from koclaw.core.tool import Tool


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"youtube\.com/watch\?v=([^&]+)",
        r"youtu\.be/([^?]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


class YouTubeTool(Tool):
    name = "youtube_summary"
    description = "유튜브 영상의 자막을 추출합니다"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "유튜브 URL"},
        },
        "required": ["url"],
    }
    is_sandboxed = False

    async def execute(self, url: str) -> str:
        video_id = extract_video_id(url)
        if not video_id:
            return f"오류: 유효하지 않은 유튜브 URL입니다. ({url})"

        try:
            transcript = await asyncio.to_thread(
                YouTubeTranscriptApi().fetch, video_id, languages=["ko", "en"]
            )
            text = " ".join(t.text for t in transcript)
            return wrap_external_content("유튜브 자막", text)
        except Exception as e:
            return f"자막 추출 실패: {e}"
