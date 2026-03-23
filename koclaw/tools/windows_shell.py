from __future__ import annotations

from typing import TYPE_CHECKING

from koclaw.core.tool import Tool

if TYPE_CHECKING:
    from koclaw.core.windows_computer_use_manager import WindowsComputerUseManager


class WindowsShellTool(Tool):
    name = "windows_shell"
    description = (
        "Windows PC에서 PowerShell 명령을 실행합니다. "
        "디스크 용량 조회, 프로세스 목록, 파일 조작, 시스템 정보 수집, "
        "레지스트리 조회, 서비스 관리 등 Windows 관리 작업에 사용하세요. "
        "화면 제어가 필요 없는 Windows 작업은 computer_use 대신 이 tool을 우선 사용하세요."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "실행할 PowerShell 명령. 예: "
                    "'Get-PSDrive C | Select-Object Used,Free', "
                    "'Get-Process | Sort-Object CPU -Descending | Select-Object -First 10', "
                    "'Get-Service | Where-Object Status -eq Running'"
                ),
            },
            "timeout": {
                "type": "number",
                "description": "명령 타임아웃 (초, 기본값: 60)",
            },
        },
        "required": ["command"],
    }
    needs_session_context = True

    def __init__(self, manager: "WindowsComputerUseManager"):
        self._manager = manager

    async def execute(
        self, command: str, timeout: float = 60.0, _session_id: str = "default", **kwargs
    ) -> str:
        return await self._manager.run_command(_session_id, command, timeout=timeout)
