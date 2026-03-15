import asyncio
import logging

from ddgs import DDGS
from ddgs.exceptions import RatelimitException

from koclaw.core import config as _cfg
from koclaw.core.prompt_guard import wrap_external_content
from koclaw.core.tool import Tool

logger = logging.getLogger(__name__)


class SearchTool(Tool):
    name = "web_search"
    description = "웹에서 정보를 검색합니다"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "검색어"},
        },
        "required": ["query"],
    }
    is_sandboxed = False

    async def execute(self, query: str) -> str:
        for attempt in range(_cfg.SEARCH_MAX_RETRIES):
            try:

                def _search():
                    with DDGS() as ddgs:
                        return list(ddgs.text(query, region="kr-ko", max_results=8))

                results = await asyncio.to_thread(_search)

                if not results:
                    return "검색 결과가 없습니다."

                lines = []
                for r in results:
                    lines.append(f"**{r['title']}**\n{r['body']}\n{r['href']}")
                content = "\n\n".join(lines)
                return wrap_external_content("웹 검색 결과", content)

            except RatelimitException:
                if attempt < _cfg.SEARCH_MAX_RETRIES - 1:
                    delay = _cfg.SEARCH_RETRY_DELAY * (2**attempt)  # 2s → 4s → 8s
                    logger.warning(
                        "[search] rate limited, %.0fs 후 재시도 (%d/%d)",
                        delay,
                        attempt + 1,
                        _cfg.SEARCH_MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                else:
                    return "검색 서비스가 일시적으로 제한되었습니다. 잠시 후 다시 시도해주세요."
            except Exception as e:
                logger.error("[search] 오류: %s", e)
                return f"검색 중 오류가 발생했습니다: {type(e).__name__}"
        return "검색 서비스가 일시적으로 제한되었습니다. 잠시 후 다시 시도해주세요."
