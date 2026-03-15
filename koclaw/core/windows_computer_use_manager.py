"""Windows 네이티브 데스크탑 제어 매니저.

windows_agent/server.py (Windows에서 실행 중인 FastAPI 서버)에
HTTP로 명령을 전달해 실제 Windows 화면을 제어합니다.

ComputerUseManager와 동일한 인터페이스를 제공하므로
ComputerUseTool을 그대로 사용할 수 있습니다.
"""

from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0


class WindowsComputerUseManager:
    """Windows Agent HTTP 서버를 통해 Windows 데스크탑을 제어하는 매니저.

    - 모든 세션이 하나의 Windows 데스크탑을 공유
    - 스크린샷·파일은 세션별로 누적 저장
    - Docker 없이 동작
    """

    def __init__(self, url: str, api_key: str = ""):
        """
        Args:
            url: windows_agent/server.py 주소 (예: http://localhost:7777)
            api_key: WINDOWS_AGENT_API_KEY 값 (미설정 시 인증 생략)
        """
        self._url = url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._screenshots: dict[str, list[bytes]] = {}
        self._files: dict[str, list[tuple[str, bytes]]] = {}

    # ── 내부 헬퍼 ──────────────────────────────────────────

    async def _get(self, path: str, timeout: float = _DEFAULT_TIMEOUT) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self._url}{path}", headers=self._headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, body: dict, timeout: float = _DEFAULT_TIMEOUT) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._url}{path}", json=body, headers=self._headers, timeout=timeout
            )
            resp.raise_for_status()
            return resp.json()

    # ── 공개 메서드 (ComputerUseManager 인터페이스) ────────

    async def restore_containers(self) -> None:
        """Docker 방식과의 호환성을 위한 no-op."""

    async def get_screen_size(self, session_id: str) -> str:
        """화면 해상도를 반환한다."""
        try:
            data = await self._get("/screen_size")
        except httpx.HTTPError as e:
            return f"해상도 조회 실패: {e}"
        return f"화면 크기: {data['width']}x{data['height']} px"

    async def screenshot(self, session_id: str) -> str:
        """스크린샷을 찍고 base64 PNG로 반환. PNG bytes를 내부에 누적 저장."""
        try:
            data = await self._get("/screenshot")
        except httpx.HTTPError as e:
            return f"스크린샷 실패: Windows Agent 연결 오류 — {e}"

        b64 = data["data"]
        self._screenshots.setdefault(session_id, []).append(base64.b64decode(b64))
        width = data.get("width", 0)
        height = data.get("height", 0)
        if width and height:
            return f"[화면 크기: {width}x{height}]\n{b64}"
        return b64

    def pop_screenshots(self, session_id: str) -> list[bytes]:
        """해당 세션에 쌓인 스크린샷 PNG bytes를 꺼내고 초기화한다."""
        return self._screenshots.pop(session_id, [])

    def pop_files(self, session_id: str) -> list[tuple[str, bytes]]:
        """copy_from으로 수거된 파일 (name, bytes) 목록을 꺼내고 초기화한다."""
        return self._files.pop(session_id, [])

    async def click(self, session_id: str, x: int, y: int, button: int = 1) -> str:
        """지정 좌표를 마우스 클릭."""
        try:
            await self._post("/click", {"x": x, "y": y, "button": button, "double": False})
        except httpx.HTTPError as e:
            return f"클릭 실패: {e}"
        return f"✅ ({x}, {y}) 클릭 완료"

    async def double_click(self, session_id: str, x: int, y: int) -> str:
        """지정 좌표를 더블클릭."""
        try:
            await self._post("/click", {"x": x, "y": y, "button": 1, "double": True})
        except httpx.HTTPError as e:
            return f"더블클릭 실패: {e}"
        return f"✅ ({x}, {y}) 더블클릭 완료"

    async def drag(
        self, session_id: str, x1: int, y1: int, x2: int, y2: int, duration: float = 0.3
    ) -> str:
        """마우스 드래그."""
        try:
            await self._post(
                "/drag", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration": duration}
            )
        except httpx.HTTPError as e:
            return f"드래그 실패: {e}"
        return f"✅ ({x1}, {y1}) → ({x2}, {y2}) 드래그 완료"

    async def type_text(self, session_id: str, text: str) -> str:
        """텍스트 입력 (클립보드 경유 — 한글 포함 모든 문자 지원)."""
        try:
            await self._post("/type", {"text": text})
        except httpx.HTTPError as e:
            return f"텍스트 입력 실패: {e}"
        return f"✅ 텍스트 입력 완료: {text[:50]}"

    async def key(self, session_id: str, key_name: str) -> str:
        """키 입력 (예: Return, ctrl+c, ctrl+l)."""
        try:
            await self._post("/key", {"key_name": key_name})
        except httpx.HTTPError as e:
            return f"키 입력 실패: {e}"
        return f"✅ 키 입력 완료: {key_name}"

    async def scroll(
        self, session_id: str, x: int, y: int, direction: str = "down", amount: int = 3
    ) -> str:
        """스크롤."""
        try:
            await self._post("/scroll", {"x": x, "y": y, "direction": direction, "amount": amount})
        except httpx.HTTPError as e:
            return f"스크롤 실패: {e}"
        return f"✅ {direction} 스크롤 완료"

    async def run_command(self, session_id: str, command: str, timeout: float = 60.0) -> str:
        """PowerShell 명령을 실행하고 stdout+stderr를 반환."""
        try:
            data = await self._post(
                "/command",
                {"command": command, "timeout": timeout},
                timeout=timeout + 10,
            )
        except httpx.HTTPError as e:
            return f"명령 실행 실패: {e}"
        return data.get("output", "(출력 없음)")

    async def open_url(self, session_id: str, url: str) -> str:
        """기본 브라우저에서 URL 열기 (PowerShell Start-Process 사용)."""
        result = await self.run_command(session_id, f'Start-Process "{url}"')
        if "실패" in result:
            return result
        return f"✅ URL 열기 요청: {url}"

    async def copy_from(self, session_id: str, container_path: str) -> str:
        """Windows 파일을 읽어 채널 업로드 큐에 추가."""
        try:
            data = await self._post("/read_file", {"path": container_path}, timeout=30.0)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return f"파일 없음: {container_path}"
            return f"파일 읽기 실패: {e}"
        except httpx.HTTPError as e:
            return f"파일 읽기 실패: {e}"

        filename = data["name"]
        file_bytes = base64.b64decode(data["data"])
        self._files.setdefault(session_id, []).append((filename, file_bytes))
        return f"✅ {filename} ({len(file_bytes):,} bytes) — 채팅에 파일로 업로드됩니다"

    async def list_windows(self, session_id: str) -> str:
        """현재 열려 있는 창 목록을 반환한다."""
        try:
            data = await self._get("/windows")
        except httpx.HTTPError as e:
            return f"창 목록 조회 실패: {e}"
        windows = data.get("windows", [])
        if not windows:
            return "열려 있는 창이 없습니다."
        lines = [f"• {w.get('Name', '?')} — {w.get('MainWindowTitle', '')}" for w in windows]
        return "현재 열려 있는 창 목록:\n" + "\n".join(lines)

    async def reset(self, session_id: str) -> str:
        """세션 상태(스크린샷·파일 큐)를 초기화한다."""
        self._screenshots.pop(session_id, None)
        self._files.pop(session_id, None)
        return "✅ 세션 상태가 초기화됐습니다."

    async def stop(self, session_id: str) -> None:
        """Docker 방식과의 호환성을 위한 no-op."""

    async def stop_all(self) -> None:
        """Docker 방식과의 호환성을 위한 no-op."""

    def stream_url(self) -> str:
        return f"{self._url}/stream"

    def view_url(self) -> str:
        return f"{self._url}/view"
