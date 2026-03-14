from __future__ import annotations

from typing import TYPE_CHECKING

from koclaw.core.tool import Tool

if TYPE_CHECKING:
    from koclaw.core.computer_use_manager import ComputerUseManager


class ComputerUseTool(Tool):
    name = "computer_use"
    description = (
        "가상 데스크탑(Docker)을 제어합니다. "
        "브라우저 열기, 마우스 클릭, 텍스트 입력, 스크린샷, 셸 명령 실행 등을 자동화합니다. "
        "작업 전 screenshot으로 현재 화면을 확인하고 좌표를 파악한 후 클릭/입력하세요. "
        "run_command로 패키지 설치·파일 조작·에러 진단 등 터미널 작업이 가능합니다. "
        "에러가 발생하면 출력을 읽고 원인을 파악해 후속 명령으로 스스로 해결하세요."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "screenshot",
                    "click",
                    "type",
                    "key",
                    "open_url",
                    "scroll",
                    "run_command",
                    "copy_from",
                    "reset",
                ],
                "description": (
                    "screenshot: 현재 화면 캡처 | "
                    "click: 좌표 클릭 (x, y 필요) | "
                    "type: 텍스트 입력 (text 필요) | "
                    "key: 키 입력 (key_name 필요, 예: Return, ctrl+c) | "
                    "open_url: URL 열기 (url 필요) | "
                    "scroll: 스크롤 (x, y, direction 필요) | "
                    "run_command: 셸 명령 실행 (command 필요) — 패키지 설치·파일 조작·에러 수정 | "
                    "copy_from: 컨테이너 파일을 채팅에 파일로 전송 (container_path 필요) — 차트·PDF·CSV 등 | "
                    "reset: 가상 데스크탑 초기화 — 현재 컨테이너 삭제, 다음 요청 시 새 환경 시작"
                ),
            },
            "x": {"type": "integer", "description": "클릭/스크롤 X 좌표"},
            "y": {"type": "integer", "description": "클릭/스크롤 Y 좌표"},
            "text": {"type": "string", "description": "입력할 텍스트"},
            "key_name": {
                "type": "string",
                "description": "입력할 키 (예: Return, ctrl+c, ctrl+l, ctrl+a)",
            },
            "url": {"type": "string", "description": "열 URL"},
            "direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "스크롤 방향",
            },
            "amount": {"type": "integer", "description": "스크롤 횟수 (기본값: 3)"},
            "command": {
                "type": "string",
                "description": "실행할 셸 명령 (예: 'apt-get install -y curl', 'python3 script.py', 'ls /tmp')",
            },
            "container_path": {
                "type": "string",
                "description": "copy_from 시 채팅으로 전송할 컨테이너 내 파일 경로",
            },
        },
        "required": ["action"],
    }
    is_sandboxed = False
    needs_session_context = True

    def __init__(self, manager: "ComputerUseManager"):
        self._manager = manager

    async def execute(self, action: str, _session_id: str = "default", **kwargs) -> str:
        session_id = _session_id

        if action == "screenshot":
            return await self._manager.screenshot(session_id)

        if action == "click":
            x = kwargs.get("x")
            y = kwargs.get("y")
            if x is None or y is None:
                return "오류: click 액션에는 x, y 좌표가 필요합니다."
            return await self._manager.click(session_id, int(x), int(y))

        if action == "type":
            text = kwargs.get("text", "")
            if not text:
                return "오류: type 액션에는 text가 필요합니다."
            return await self._manager.type_text(session_id, text)

        if action == "key":
            key_name = kwargs.get("key_name", "")
            if not key_name:
                return "오류: key 액션에는 key_name이 필요합니다."
            return await self._manager.key(session_id, key_name)

        if action == "open_url":
            url = kwargs.get("url", "")
            if not url:
                return "오류: open_url 액션에는 url이 필요합니다."
            return await self._manager.open_url(session_id, url)

        if action == "scroll":
            x = kwargs.get("x", 640)
            y = kwargs.get("y", 360)
            direction = kwargs.get("direction", "down")
            amount = kwargs.get("amount", 3)
            return await self._manager.scroll(session_id, int(x), int(y), direction, int(amount))

        if action == "run_command":
            command = kwargs.get("command", "")
            if not command:
                return "오류: run_command 액션에는 command가 필요합니다."
            return await self._manager.run_command(session_id, command)

        if action == "copy_from":
            container_path = kwargs.get("container_path", "")
            if not container_path:
                return "오류: copy_from 액션에는 container_path가 필요합니다."
            return await self._manager.copy_from(session_id, container_path)

        if action == "reset":
            return await self._manager.reset(session_id)

        return f"오류: 알 수 없는 action: {action}"
