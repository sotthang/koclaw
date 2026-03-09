import asyncio
import json
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_MEMORY_MB = "256m"
_CPUS = "0.5"
_PIDS_LIMIT = "64"
_TIMEOUT_SEC = 30.0


def _fs_session_id(session_id: str) -> str:
    """session_id를 파일시스템/Docker 볼륨 경로로 사용하기 위해 ':' → '_' 변환."""
    return session_id.replace(":", "_")


def _validate_session_id(workspace_root: Path, session_id: str) -> Path:
    """session_id가 workspace_root 밖을 가리키는지 검사한다."""
    safe_id = _fs_session_id(session_id)
    resolved = (workspace_root / safe_id).resolve()
    root = workspace_root.resolve()
    if not str(resolved).startswith(str(root) + "/") and resolved != root:
        raise ValueError(f"허용되지 않은 session_id: {session_id!r}")
    return resolved


class SandboxManager:
    """세션별 Docker 컨테이너에서 격리 tool을 실행하는 매니저.

    - 매 실행마다 새 컨테이너 생성 (재사용 없음)
    - --network none, CPU/메모리 제한, --rm 으로 보안 격리
    - /workspace/{session_id}/ 볼륨 마운트
    - IPC: 파일시스템 기반 (.sandbox_input.json → stdout)
    """

    def __init__(
        self,
        workspace_root: str | Path,
        image: str = "koclaw-sandbox",
        host_workspace_root: str | Path | None = None,
    ):
        self._workspace_root = Path(workspace_root).resolve()
        self._host_workspace_root = (
            Path(host_workspace_root).resolve() if host_workspace_root else self._workspace_root
        )
        self._image = image

    async def execute(
        self,
        session_id: str,
        tool_name: str,
        args: dict,
        parent_session_id: str | None = None,
    ) -> str:
        """격리 컨테이너에서 tool을 실행하고 결과를 반환한다."""
        session_dir = _validate_session_id(self._workspace_root, session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        input_file = session_dir / ".sandbox_input.json"
        payload = json.dumps({"tool": tool_name, "args": args}, ensure_ascii=False)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=session_dir, delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        tmp_path.rename(input_file)

        host_session_dir = self._host_workspace_root / _fs_session_id(session_id)
        volume = f"{host_session_dir}:/workspace"
        cmd = [
            "docker", "run",
            "--rm",
            "--network", "none",
            "--memory", _MEMORY_MB,
            "--memory-swap", _MEMORY_MB,  # swap 사용 차단 (memory와 동일값으로 설정)
            "--cpus", _CPUS,
            "--pids-limit", _PIDS_LIMIT,
            "-v", volume,
        ]
        if parent_session_id is not None:
            _validate_session_id(self._workspace_root, parent_session_id)
            host_parent_dir = self._host_workspace_root / _fs_session_id(parent_session_id)
            cmd += ["-v", f"{host_parent_dir}:/parent_workspace:ro"]
        cmd += [
            self._image,
            "python", "/app/sandbox_runner.py",
        ]

        logger.info("[sandbox] %s tool=%s session=%s", cmd[:2], tool_name, session_id)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                proc.kill()
                raise RuntimeError(
                    f"샌드박스 실행 타임아웃 ({_TIMEOUT_SEC:.0f}초): tool={tool_name}"
                )
        finally:
            if input_file.exists():
                input_file.unlink()

        if proc.returncode != 0:
            raise RuntimeError(
                f"샌드박스 실행 실패 (exit={proc.returncode}): {stderr.decode().strip()}"
            )

        return stdout.decode().strip()
