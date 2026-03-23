from __future__ import annotations

from typing import TYPE_CHECKING

from koclaw.core.tool import Tool

if TYPE_CHECKING:
    from koclaw.core.windows_computer_use_manager import WindowsComputerUseManager


class BrowserTool(Tool):
    name = "browser"
    description = (
        "⚠️ 사용자가 '브라우저', '화면', '스크린샷', '클릭', 'browser' 등 브라우저 제어를 명시적으로 언급한 경우에만 사용하세요. "
        "그 외 일반 웹 검색·조회 작업에는 browse/search tool을 사용하세요. "
        "Playwright 기반 브라우저 자동화 tool. "
        "selector로 요소를 직접 지정해 클릭·입력·스크롤을 수행합니다. "
        "selector는 텍스트('17일', 'text=확인'), CSS('.btn', '#id'), XPath('//button') 형식 모두 지원합니다. "
        "screenshot 결과는 채널에 이미지로 자동 업로드됩니다. "
        "응답 텍스트에 마크다운 이미지를 포함하지 마세요."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "navigate",
                    "screenshot",
                    "click",
                    "type",
                    "scroll",
                    "evaluate",
                    "content",
                    "wait_for",
                    "select",
                    "close",
                ],
                "description": (
                    "navigate: URL로 이동 (url 필요, wait_until 선택) | "
                    "screenshot: 브라우저 현재 화면 캡처 | "
                    "click: selector로 요소 클릭 (selector 필요) | "
                    "type: 요소에 텍스트 입력 (selector, text 필요) | "
                    "scroll: 페이지 스크롤 (direction, amount 선택) | "
                    "evaluate: JavaScript 실행 (script 필요) | "
                    "content: 현재 페이지 텍스트 내용 추출 | "
                    "wait_for: selector가 나타날 때까지 대기 (selector 필요) | "
                    "select: <select> 요소 선택 (selector, value 필요) | "
                    "close: 브라우저 닫기"
                ),
            },
            "url": {"type": "string", "description": "이동할 URL"},
            "wait_until": {
                "type": "string",
                "enum": ["load", "domcontentloaded", "networkidle"],
                "description": "페이지 로딩 완료 조건 (기본값: domcontentloaded)",
            },
            "selector": {
                "type": "string",
                "description": (
                    "요소 selector — 텍스트('17일', 'text=확인'), "
                    "CSS('.btn', '#submit', 'input[name=q]'), "
                    "XPath('//button[@type=\"submit\"]') 모두 지원"
                ),
            },
            "text": {"type": "string", "description": "입력할 텍스트"},
            "clear_first": {
                "type": "boolean",
                "description": "입력 전 기존 내용 삭제 여부 (기본값: true)",
            },
            "direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "스크롤 방향 (기본값: down)",
            },
            "amount": {"type": "integer", "description": "스크롤 횟수 (기본값: 3)"},
            "script": {"type": "string", "description": "실행할 JavaScript 표현식"},
            "value": {"type": "string", "description": "<select> 요소의 option value"},
            "timeout": {"type": "number", "description": "wait_for 대기 시간(초, 기본값: 10)"},
        },
        "required": ["action"],
    }
    is_sandboxed = False
    needs_session_context = True

    def __init__(self, manager: "WindowsComputerUseManager"):
        self._manager = manager

    async def execute(self, action: str, _session_id: str = "default", **kwargs) -> str:
        session_id = _session_id

        if action == "navigate":
            url = kwargs.get("url", "")
            if not url:
                return "오류: navigate 액션에는 url이 필요합니다."
            wait_until = kwargs.get("wait_until", "domcontentloaded")
            return await self._manager.browser_navigate(session_id, url, wait_until)

        if action == "screenshot":
            return await self._manager.browser_screenshot(session_id)

        if action == "click":
            selector = kwargs.get("selector", "")
            if not selector:
                return "오류: click 액션에는 selector가 필요합니다."
            return await self._manager.browser_click(session_id, selector)

        if action == "type":
            selector = kwargs.get("selector", "")
            text = kwargs.get("text", "")
            if not selector or not text:
                return "오류: type 액션에는 selector와 text가 필요합니다."
            clear_first = kwargs.get("clear_first", True)
            return await self._manager.browser_type(session_id, selector, text, clear_first)

        if action == "scroll":
            direction = kwargs.get("direction", "down")
            amount = kwargs.get("amount", 3)
            return await self._manager.browser_scroll(session_id, direction, int(amount))

        if action == "evaluate":
            script = kwargs.get("script", "")
            if not script:
                return "오류: evaluate 액션에는 script가 필요합니다."
            return await self._manager.browser_evaluate(session_id, script)

        if action == "content":
            return await self._manager.browser_content(session_id)

        if action == "wait_for":
            selector = kwargs.get("selector", "")
            if not selector:
                return "오류: wait_for 액션에는 selector가 필요합니다."
            timeout = float(kwargs.get("timeout", 10.0))
            return await self._manager.browser_wait_for(session_id, selector, timeout)

        if action == "select":
            selector = kwargs.get("selector", "")
            value = kwargs.get("value", "")
            if not selector or not value:
                return "오류: select 액션에는 selector와 value가 필요합니다."
            return await self._manager.browser_select(session_id, selector, value)

        if action == "close":
            return await self._manager.browser_close(session_id)

        return f"오류: 알 수 없는 action: {action}"
