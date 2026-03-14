import asyncio
import logging
import socket

logger = logging.getLogger(__name__)

_STARTUP_WAIT_SEC = 4.0
_EXEC_TIMEOUT_SEC = 15.0


def _safe_container_name(session_id: str) -> str:
    """session_id를 Docker 컨테이너 이름으로 사용 가능하게 변환"""
    return "koclaw-cu-" + session_id.replace(":", "_").replace("/", "_")[:50]


class ComputerUseManager:
    """세션별 Docker 컨테이너에서 가상 데스크탑을 실행하는 매니저.

    - 세션당 하나의 컨테이너 유지 (영속적 데스크탑 상태)
    - Xvfb 가상 디스플레이 + Chromium 브라우저
    - xdotool로 마우스/키보드 제어
    - scrot으로 스크린샷 캡처
    """

    def __init__(
        self, image: str = "koclaw-computer-use", workspace=None, host_workspace=None, db=None
    ):
        self._image = image
        self._workspace = workspace
        # Docker 안에서 실행 시 호스트 실제 경로가 컨테이너 내부 경로와 다를 수 있음
        self._host_workspace = host_workspace if host_workspace is not None else workspace
        self._db = db
        self._containers: dict[str, str] = {}  # session_id -> container_id
        self._screenshots: dict[str, list[bytes]] = {}  # session_id -> [png_bytes]
        self._files: dict[str, list[tuple[str, bytes]]] = {}  # session_id -> [(name, bytes)]
        self._vnc_ports: dict[str, int] = {}  # session_id -> host port

    def _find_free_port(self, start: int = 6080) -> int:
        """사용 가능한 포트를 찾아 반환"""
        for port in range(start, start + 100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("", port))
                    return port
                except OSError:
                    continue
        return start

    async def _docker_exec(
        self, container_id: str, *cmd: str, timeout: float = _EXEC_TIMEOUT_SEC
    ) -> tuple[str, str]:
        """컨테이너 내에서 명령 실행, (stdout, stderr) 반환"""
        full_cmd = ["docker", "exec", "-e", "DISPLAY=:99", container_id] + list(cmd)
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"명령 타임아웃: {' '.join(cmd[:3])}")
        return stdout.decode(errors="replace"), stderr.decode(errors="replace")

    async def _container_running(self, container_id: str) -> bool:
        """컨테이너가 실행 중인지 확인"""
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            container_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() == "true"

    async def _ensure_container(self, session_id: str) -> str:
        """세션용 컨테이너가 실행 중인지 확인하고, 없으면 시작한다."""
        if session_id in self._containers:
            cid = self._containers[session_id]
            if await self._container_running(cid):
                return cid
            del self._containers[session_id]

        name = _safe_container_name(session_id)

        # 같은 이름의 중단된 컨테이너 제거
        rm_proc = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await rm_proc.communicate()

        vnc_port = self._find_free_port(6080)

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--memory",
            "1g",
            "--cpus",
            "1.0",
            "--shm-size",
            "256m",
            "-p",
            f"{vnc_port}:6080",
        ]

        # 세션 워크스페이스를 /workspace:ro로 마운트 — 사용자 첨부파일 공유
        # host_workspace: Docker 호스트 기준 실제 경로 (koclaw가 Docker 안에서 실행될 때 필요)
        if self._host_workspace is not None:
            from pathlib import Path

            host_session_dir = Path(self._host_workspace) / session_id.replace(":", "_")
            # mkdir은 koclaw가 볼 수 있는 경로(_workspace)로 수행
            if self._workspace is not None:
                Path(self._workspace, session_id.replace(":", "_")).mkdir(
                    parents=True, exist_ok=True
                )
            cmd += ["-v", f"{host_session_dir}:/workspace:ro"]

        cmd.append(self._image)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"컨테이너 시작 실패: {stderr.decode().strip()}")

        cid = stdout.decode().strip()
        self._containers[session_id] = cid
        self._vnc_ports[session_id] = vnc_port

        if self._db is not None:
            await self._db.save_container(session_id, cid, vnc_port)

        # Xvfb와 Chromium 시작 대기
        await asyncio.sleep(_STARTUP_WAIT_SEC)
        logger.info(
            "[computer_use] 컨테이너 시작: session=%s cid=%s noVNC=http://localhost:%d",
            session_id,
            cid[:12],
            vnc_port,
        )
        return cid

    async def restore_containers(self) -> None:
        """앱 시작 시 DB에 저장된 컨테이너를 복원한다. 죽어있으면 DB에서 삭제."""
        if self._db is None:
            return
        rows = await self._db.get_all_containers()
        for row in rows:
            session_id = row["session_id"]
            cid = row["container_id"]
            vnc_port = row["vnc_port"]
            if await self._container_running(cid):
                self._containers[session_id] = cid
                self._vnc_ports[session_id] = vnc_port
                logger.info("[computer_use] 컨테이너 복원: session=%s cid=%s", session_id, cid[:12])
            else:
                await self._db.delete_container(session_id)
                logger.info("[computer_use] 죽은 컨테이너 DB 정리: session=%s", session_id)

    async def reset(self, session_id: str) -> str:
        """세션 컨테이너를 초기화한다 (기존 컨테이너 삭제 → 새 컨테이너는 다음 요청 시 시작)."""
        await self.stop(session_id)
        if self._db is not None:
            await self._db.delete_container(session_id)
        logger.info("[computer_use] 컨테이너 초기화: session=%s", session_id)
        return "✅ 가상 데스크탑이 초기화됐습니다. 다음 작업 시 새 환경이 시작됩니다."

    async def screenshot(self, session_id: str) -> str:
        """스크린샷을 찍고 base64 PNG로 반환. PNG bytes를 내부에 누적 저장."""
        import base64

        cid = await self._ensure_container(session_id)
        stdout, stderr = await self._docker_exec(
            cid,
            "bash",
            "-c",
            "scrot -o /tmp/screenshot.png 2>/dev/null && base64 -w 0 /tmp/screenshot.png",
        )
        if not stdout.strip():
            return f"스크린샷 실패: {stderr.strip()}"
        b64 = stdout.strip()
        # PNG bytes를 세션별로 누적 (채널 핸들러가 pop_screenshots로 수거)
        self._screenshots.setdefault(session_id, []).append(base64.b64decode(b64))
        return b64

    def pop_screenshots(self, session_id: str) -> list[bytes]:
        """해당 세션에 쌓인 스크린샷 PNG bytes를 꺼내고 초기화한다."""
        return self._screenshots.pop(session_id, [])

    def pop_files(self, session_id: str) -> list[tuple[str, bytes]]:
        """copy_from으로 수거된 파일 (name, bytes) 목록을 꺼내고 초기화한다."""
        return self._files.pop(session_id, [])

    async def copy_from(self, session_id: str, container_path: str) -> str:
        """컨테이너 파일을 호스트로 복사하고 채널 업로드 큐에 추가한다."""
        import tempfile
        from pathlib import Path

        cid = await self._ensure_container(session_id)
        filename = Path(container_path).name
        with tempfile.NamedTemporaryFile(suffix=Path(container_path).suffix, delete=False) as tmp:
            host_path = tmp.name

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "cp",
                f"{cid}:{container_path}",
                host_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                return f"파일 복사 실패: {stderr.decode().strip()}"

            data = Path(host_path).read_bytes()
            self._files.setdefault(session_id, []).append((filename, data))
            return f"✅ {filename} ({len(data):,} bytes) — 채팅에 파일로 업로드됩니다"
        finally:
            Path(host_path).unlink(missing_ok=True)

    async def click(self, session_id: str, x: int, y: int, button: int = 1) -> str:
        """지정 좌표를 마우스 클릭"""
        cid = await self._ensure_container(session_id)
        await self._docker_exec(
            cid,
            "xdotool",
            "mousemove",
            str(x),
            str(y),
            "click",
            str(button),
        )
        return f"✅ ({x}, {y}) 클릭 완료"

    async def type_text(self, session_id: str, text: str) -> str:
        """텍스트 입력"""
        cid = await self._ensure_container(session_id)
        await self._docker_exec(
            cid,
            "xdotool",
            "type",
            "--clearmodifiers",
            "--delay",
            "50",
            text,
        )
        return f"✅ 텍스트 입력 완료: {text[:50]}"

    async def key(self, session_id: str, key_name: str) -> str:
        """키 입력 (예: Return, ctrl+c, ctrl+l)"""
        cid = await self._ensure_container(session_id)
        await self._docker_exec(cid, "xdotool", "key", key_name)
        return f"✅ 키 입력 완료: {key_name}"

    async def run_command(self, session_id: str, command: str, timeout: float = 60.0) -> str:
        """컨테이너 안에서 셸 명령을 실행하고 stdout+stderr를 반환.

        패키지 설치, 파일 조작, 에러 진단 등 터미널 작업에 사용.
        AI가 출력을 보고 후속 명령으로 에러를 자동 수정할 수 있다.
        """
        cid = await self._ensure_container(session_id)
        stdout, stderr = await self._docker_exec(cid, "bash", "-c", command, timeout=timeout)
        parts = []
        if stdout.strip():
            parts.append(stdout.strip())
        if stderr.strip():
            parts.append(f"[stderr]\n{stderr.strip()}")
        return "\n".join(parts) if parts else "(출력 없음)"

    async def open_url(self, session_id: str, url: str) -> str:
        """브라우저에서 URL 열기"""
        cid = await self._ensure_container(session_id)
        # Firefox 창 포커스 후 주소창에 URL 입력
        await self._docker_exec(
            cid,
            "bash",
            "-c",
            "xdotool search --onlyvisible --class firefox windowactivate --sync 2>/dev/null || true",
        )
        await asyncio.sleep(0.3)
        await self._docker_exec(cid, "xdotool", "key", "ctrl+l")
        await asyncio.sleep(0.3)
        await self._docker_exec(cid, "xdotool", "type", "--clearmodifiers", url)
        await asyncio.sleep(0.2)
        await self._docker_exec(cid, "xdotool", "key", "Return")
        return f"✅ URL 열기 요청: {url}"

    async def scroll(
        self, session_id: str, x: int, y: int, direction: str = "down", amount: int = 3
    ) -> str:
        """스크롤 (button 4=위, 5=아래)"""
        cid = await self._ensure_container(session_id)
        button = "5" if direction == "down" else "4"
        await self._docker_exec(
            cid,
            "xdotool",
            "mousemove",
            str(x),
            str(y),
            "click",
            "--repeat",
            str(amount),
            button,
        )
        return f"✅ {direction} 스크롤 완료"

    async def stop(self, session_id: str) -> None:
        """세션 컨테이너 종료"""
        if session_id not in self._containers:
            return
        cid = self._containers.pop(session_id)
        self._vnc_ports.pop(session_id, None)
        stop_proc = await asyncio.create_subprocess_exec(
            "docker",
            "stop",
            cid,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await stop_proc.communicate()
        if self._db is not None:
            await self._db.delete_container(session_id)
        logger.info("[computer_use] 컨테이너 종료: session=%s", session_id)

    async def stop_all(self) -> None:
        """모든 세션 컨테이너 종료"""
        for session_id in list(self._containers.keys()):
            await self.stop(session_id)
