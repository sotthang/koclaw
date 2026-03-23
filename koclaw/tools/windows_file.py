from __future__ import annotations

import json
from typing import TYPE_CHECKING

from koclaw.core.tool import Tool

if TYPE_CHECKING:
    from koclaw.core.windows_computer_use_manager import WindowsComputerUseManager


class WindowsFileTool(Tool):
    name = "windows_file"
    description = (
        "Windows PC의 파일(PDF, Excel, DOCX, PPTX 등) 내용을 읽습니다. "
        "파일 경로는 Windows 경로 형식 (예: C:\\Users\\사용자\\Downloads\\report.xlsx)으로 지정하세요. "
        "대용량 파일 처리 방법: "
        "1) file_info로 파일 크기·페이지수·시트 목록을 먼저 확인하세요. "
        "2) PDF/PPTX는 page_start/page_end로 범위를 나눠 30~50페이지씩 추출하세요. "
        "3) Excel은 시트별로 추출하고, 행이 많으면 row_start/row_end로 나눠 처리하세요. "
        "4) 각 청크를 요약하면서 전체 내용을 파악하세요."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["file_info", "extract"],
                "description": (
                    "file_info: 파일 크기·페이지수·시트 목록 조회 (대용량 파일 처리 전 먼저 호출) | "
                    "extract: 텍스트 추출 (범위 지정 가능)"
                ),
            },
            "path": {
                "type": "string",
                "description": "Windows 파일 경로 (예: C:\\Users\\사용자\\Downloads\\report.pdf)",
            },
            "sheet": {
                "type": "string",
                "description": "Excel 시트 이름 (미지정 시 전체 시트)",
            },
            "page_start": {
                "type": "integer",
                "description": "PDF/PPTX 시작 페이지/슬라이드 번호 (1-based)",
            },
            "page_end": {
                "type": "integer",
                "description": "PDF/PPTX 끝 페이지/슬라이드 번호 (1-based, 포함)",
            },
            "row_start": {
                "type": "integer",
                "description": "Excel 시작 행 (1-based)",
            },
            "row_end": {
                "type": "integer",
                "description": "Excel 끝 행 (1-based, 포함)",
            },
        },
        "required": ["action", "path"],
    }

    def __init__(self, manager: "WindowsComputerUseManager"):
        self._manager = manager

    async def execute(
        self,
        action: str,
        path: str,
        sheet: str | None = None,
        page_start: int | None = None,
        page_end: int | None = None,
        row_start: int | None = None,
        row_end: int | None = None,
        **kwargs,
    ) -> str:
        if action == "file_info":
            info = await self._manager.file_info(path)
            if "error" in info:
                return f"오류: {info['error']}"
            return json.dumps(info, ensure_ascii=False, indent=2)

        if action == "extract":
            return await self._manager.extract_text(
                path=path,
                sheet=sheet,
                page_start=page_start,
                page_end=page_end,
                row_start=row_start,
                row_end=row_end,
            )

        return f"오류: 알 수 없는 action: {action}"
