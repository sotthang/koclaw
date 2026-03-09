import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koclaw.core.sandbox import SandboxManager


@pytest.fixture
def workspace(tmp_path):
    return tmp_path


@pytest.fixture
def sandbox(workspace):
    return SandboxManager(workspace_root=workspace, image="koclaw-sandbox")


@pytest.fixture
def sandbox_with_host_path(workspace, tmp_path):
    host_root = tmp_path / "host_workspace"
    return SandboxManager(workspace_root=workspace, image="koclaw-sandbox", host_workspace_root=host_root)


def make_mock_proc(stdout: str = "ok", returncode: int = 0):
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# 1. 세션별 workspace 디렉토리 생성
@pytest.mark.asyncio
async def test_execute_creates_session_workspace(sandbox, workspace):
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("result")):
        await sandbox.execute("sess-abc", "memory", {"action": "read"})
    assert (workspace / "sess-abc").is_dir()


# 2. input.json에 tool명과 args를 저장 (컨테이너 실행 전에 파일이 존재해야 함)
@pytest.mark.asyncio
async def test_execute_writes_input_json(sandbox, workspace):
    """컨테이너 communicate 시점에 input.json에 올바른 데이터가 기록되어 있어야 한다."""
    captured: dict = {}

    async def fake_communicate():
        input_file = workspace / "sess-1" / ".sandbox_input.json"
        if input_file.exists():
            captured["data"] = json.loads(input_file.read_text())
        return (b"result", b"")

    proc = MagicMock()
    proc.communicate = fake_communicate
    proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        await sandbox.execute("sess-1", "memory", {"action": "write", "content": "hello"})

    assert "data" in captured, "input.json이 컨테이너 실행 전에 작성되지 않았습니다"
    assert captured["data"]["tool"] == "memory"
    assert captured["data"]["args"] == {"action": "write", "content": "hello"}


# 3. --rm, --network none, 메모리/CPU 제한 플래그 포함
@pytest.mark.asyncio
async def test_execute_runs_docker_with_isolation_flags(sandbox, workspace):
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("result")) as mock_exec:
        await sandbox.execute("sess-2", "memory", {"action": "read"})

    args = mock_exec.call_args[0]
    cmd = list(args)
    assert "docker" in cmd[0]
    assert "--rm" in cmd
    assert "--network" in cmd
    assert "none" in cmd
    assert "--memory" in cmd
    assert "--cpus" in cmd


# 4. 볼륨 마운트: {workspace}/{session_id}:/workspace
@pytest.mark.asyncio
async def test_execute_mounts_session_volume(sandbox, workspace):
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("result")) as mock_exec:
        await sandbox.execute("sess-3", "memory", {"action": "read"})

    args = mock_exec.call_args[0]
    cmd = list(args)
    expected_volume = f"{workspace}/sess-3:/workspace"
    assert "-v" in cmd
    vol_idx = cmd.index("-v")
    assert cmd[vol_idx + 1] == expected_volume


# 5. 컨테이너 stdout을 결과로 반환
@pytest.mark.asyncio
async def test_execute_returns_stdout(sandbox):
    expected = "저장된 기억이 없습니다."
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc(expected)):
        result = await sandbox.execute("sess-4", "memory", {"action": "read"})
    assert result == expected


# 6. 컨테이너 비정상 종료 시 예외 발생
@pytest.mark.asyncio
async def test_execute_raises_on_nonzero_exit(sandbox):
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("err", returncode=1)):
        with pytest.raises(RuntimeError, match="샌드박스"):
            await sandbox.execute("sess-5", "memory", {"action": "read"})


# 7. 실행 후 input.json 삭제 (정리)
@pytest.mark.asyncio
async def test_execute_removes_input_json_after_run(sandbox, workspace):
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("ok")):
        await sandbox.execute("sess-6", "memory", {"action": "read"})

    input_file = workspace / "sess-6" / ".sandbox_input.json"
    assert not input_file.exists()


# host_workspace_root 가 주어지면 volume 마운트에 host 경로를 사용해야 함
@pytest.mark.asyncio
async def test_execute_uses_host_workspace_root_for_volume(sandbox_with_host_path, tmp_path):
    workspace = tmp_path / "workspace"
    host_root = tmp_path / "host_workspace"
    sandbox = SandboxManager(workspace_root=workspace, image="koclaw-sandbox", host_workspace_root=host_root)

    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("result")) as mock_exec:
        await sandbox.execute("sess-h", "file", {"action": "read"})

    cmd = list(mock_exec.call_args[0])
    vol_idx = cmd.index("-v")
    assert cmd[vol_idx + 1].startswith(str(host_root))


# ── 보안: Path Traversal 방어 ──────────────────────────────────────────────────

# 8. session_id에 경로 탈출 시도 시 ValueError 발생
@pytest.mark.asyncio
async def test_execute_rejects_path_traversal_session_id(sandbox):
    with pytest.raises(ValueError, match="session_id"):
        await sandbox.execute("../../etc", "memory", {"action": "read"})


@pytest.mark.asyncio
async def test_execute_rejects_absolute_session_id(sandbox):
    with pytest.raises(ValueError, match="session_id"):
        await sandbox.execute("/etc/passwd", "memory", {"action": "read"})


# ── 보안: 타임아웃 ──────────────────────────────────────────────────────────────

# 9. 타임아웃 초과 시 RuntimeError 발생 + 프로세스 kill
@pytest.mark.asyncio
async def test_execute_raises_on_timeout(sandbox):
    import asyncio as _asyncio

    import koclaw.core.sandbox as sandbox_module

    async def slow_communicate():
        await _asyncio.sleep(9999)
        return (b"", b"")

    proc = MagicMock()
    proc.communicate = slow_communicate
    proc.kill = MagicMock()

    with patch("asyncio.create_subprocess_exec", return_value=proc):
        with patch.object(sandbox_module, "_TIMEOUT_SEC", 0.05):
            with pytest.raises(RuntimeError, match="타임아웃"):
                await sandbox.execute("sess-t", "memory", {"action": "read"})

    proc.kill.assert_called_once()


# ── 보안: --memory-swap ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_includes_memory_swap(sandbox):
    """docker run 명령에 --memory-swap이 포함되어 swap 사용이 차단되어야 한다."""
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("ok")) as mock_exec:
        await sandbox.execute("sess-ms", "memory", {"action": "read"})

    cmd = list(mock_exec.call_args[0])
    assert "--memory-swap" in cmd
    # --memory와 동일한 값이어야 swap이 비활성화됨
    mem_idx = cmd.index("--memory")
    swap_idx = cmd.index("--memory-swap")
    assert cmd[mem_idx + 1] == cmd[swap_idx + 1]


# ── 보안: --pids-limit ─────────────────────────────────────────────────────────

# 10. docker run 명령에 --pids-limit 포함
@pytest.mark.asyncio
async def test_execute_includes_pids_limit(sandbox):
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("ok")) as mock_exec:
        await sandbox.execute("sess-p", "memory", {"action": "read"})

    cmd = list(mock_exec.call_args[0])
    assert "--pids-limit" in cmd


# ── 원자적 쓰기 ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_writes_input_json_atomically(sandbox, workspace):
    """input.json은 tempfile → rename으로 원자적으로 쓰여야 한다 (중간 상태 노출 없음)."""
    seen_temp = []

    original_rename = Path.rename

    def tracking_rename(self, target):
        seen_temp.append(str(self))
        return original_rename(self, target)

    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("ok")):
        with patch.object(Path, "rename", tracking_rename):
            await sandbox.execute("sess-atomic", "memory", {"action": "read"})

    assert any("sess-atomic" in p or workspace.name in p for p in seen_temp), \
        "rename이 호출되지 않아 원자적 쓰기가 이뤄지지 않았습니다"


# ── 계층형 파일 접근: parent_session_id 볼륨 마운트 ──────────────────────────────

@pytest.mark.asyncio
async def test_execute_mounts_parent_workspace_readonly(sandbox, workspace):
    """parent_session_id가 주어지면 parent 디렉토리를 /parent_workspace:ro로 마운트한다."""
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("ok")) as mock_exec:
        await sandbox.execute("sess-child", "file", {"action": "read"}, parent_session_id="sess-parent")

    cmd = list(mock_exec.call_args[0])
    volumes = [cmd[i + 1] for i, v in enumerate(cmd) if v == "-v"]
    assert any("parent_workspace:ro" in v for v in volumes)
    assert any(str(workspace / "sess-parent") in v for v in volumes)


@pytest.mark.asyncio
async def test_execute_no_parent_mount_when_no_parent_session_id(sandbox, workspace):
    """parent_session_id가 없으면 parent_workspace 볼륨을 마운트하지 않는다."""
    with patch("asyncio.create_subprocess_exec", return_value=make_mock_proc("ok")) as mock_exec:
        await sandbox.execute("sess-solo", "file", {"action": "read"})

    cmd = list(mock_exec.call_args[0])
    assert "parent_workspace" not in " ".join(cmd)
