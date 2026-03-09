"""sandbox_runner.py 단위 테스트"""
from unittest.mock import patch

import pytest

import koclaw.sandbox_runner as runner


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """WORKSPACE 경로를 tmp_path로 치환"""
    monkeypatch.setattr(runner, "WORKSPACE", tmp_path)
    monkeypatch.setattr(runner, "INPUT_FILE", tmp_path / ".sandbox_input.json")
    return tmp_path


# ── memory tool ──────────────────────────────────────────────────────────────

def test_memory_read_returns_content(workspace):
    (workspace / "MEMORY.md").write_text("기억 내용", encoding="utf-8")
    result = runner.run_memory({"action": "read"})
    assert result == "기억 내용"


def test_memory_read_empty(workspace):
    result = runner.run_memory({"action": "read"})
    assert "없습니다" in result


def test_memory_write(workspace):
    result = runner.run_memory({"action": "write", "content": "새 기억"})
    assert "저장" in result
    assert (workspace / "MEMORY.md").read_text(encoding="utf-8") == "새 기억"


# ── file tool — 정상 경로 ─────────────────────────────────────────────────────

def test_file_read(workspace):
    (workspace / "doc.txt").write_text("내용", encoding="utf-8")
    result = runner.run_file({"action": "read", "path": "doc.txt"})
    assert result == "내용"


def test_file_write(workspace):
    result = runner.run_file({"action": "write", "path": "out.txt", "content": "데이터"})
    assert "저장" in result
    assert (workspace / "out.txt").read_text(encoding="utf-8") == "데이터"


# ── file tool — Path Traversal 방어 ──────────────────────────────────────────

def test_file_read_blocks_path_traversal(workspace):
    """../를 이용한 workspace 탈출 시도를 차단한다."""
    result = runner.run_file({"action": "read", "path": "../../etc/passwd"})
    assert "허용되지 않은 경로" in result


def test_file_write_blocks_path_traversal(workspace):
    """쓰기 시도도 workspace 바깥 경로를 차단한다."""
    result = runner.run_file({"action": "write", "path": "../escape.txt", "content": "x"})
    assert "허용되지 않은 경로" in result
    assert not (workspace.parent / "escape.txt").exists()


def test_file_read_blocks_absolute_path(workspace):
    """절대 경로로 workspace 밖에 접근하는 것을 차단한다."""
    result = runner.run_file({"action": "read", "path": "/etc/passwd"})
    assert "허용되지 않은 경로" in result


# ── file tool — list / delete ─────────────────────────────────────────────────

def test_file_list(workspace):
    (workspace / "a.txt").write_text("a")
    (workspace / "b.md").write_text("b")
    result = runner.run_file({"action": "list"})
    assert "a.txt" in result
    assert "b.md" in result


def test_file_list_hides_dot_files(workspace):
    """내부 파일(.으로 시작)은 list 결과에서 숨긴다."""
    (workspace / "doc.txt").write_text("내용")
    (workspace / ".sandbox_input.json").write_text("{}")
    (workspace / ".hidden").write_text("숨김")
    result = runner.run_file({"action": "list"})
    assert "doc.txt" in result
    assert ".sandbox_input.json" not in result
    assert ".hidden" not in result


def test_file_list_empty(workspace):
    result = runner.run_file({"action": "list"})
    assert "없습니다" in result


def test_file_list_instant_scope(workspace):
    instant_dir = workspace / ".instant"
    instant_dir.mkdir()
    (instant_dir / "tmp.txt").write_text("임시")
    result = runner.run_file({"action": "list", "scope": "instant"})
    assert "tmp.txt" in result


def test_file_delete(workspace):
    f = workspace / "del.txt"
    f.write_text("삭제될 파일")
    result = runner.run_file({"action": "delete", "path": "del.txt"})
    assert not f.exists()
    assert "삭제" in result


def test_file_delete_nonexistent(workspace):
    result = runner.run_file({"action": "delete", "path": "없는파일.txt"})
    assert "없습니다" in result or "오류" in result


# ── file tool — 계층형 파일 접근 ─────────────────────────────────────────────

def test_file_read_falls_back_to_parent_workspace(workspace, monkeypatch):
    """자체 workspace에 없는 파일을 PARENT_WORKSPACE에서 fallback으로 읽는다."""
    parent_dir = workspace.parent / "parent_ws"
    parent_dir.mkdir()
    (parent_dir / "shared.txt").write_text("부모 파일", encoding="utf-8")
    monkeypatch.setattr(runner, "PARENT_WORKSPACE", parent_dir)

    result = runner.run_file({"action": "read", "path": "shared.txt"})
    assert "부모 파일" in result


def test_file_read_own_file_takes_priority_over_parent(workspace, monkeypatch):
    """자체 workspace와 parent 모두에 파일이 있으면 자체 파일을 우선한다."""
    parent_dir = workspace.parent / "parent_ws2"
    parent_dir.mkdir()
    (parent_dir / "data.txt").write_text("부모 버전", encoding="utf-8")
    (workspace / "data.txt").write_text("자체 버전", encoding="utf-8")
    monkeypatch.setattr(runner, "PARENT_WORKSPACE", parent_dir)

    result = runner.run_file({"action": "read", "path": "data.txt"})
    assert "자체 버전" in result


# ── file tool — 크기/개수 제한 ────────────────────────────────────────────────

def test_file_write_rejects_oversized_content(workspace):
    """1MB 초과 content는 거부한다."""
    big_content = "x" * (1024 * 1024 + 1)
    result = runner.run_file({"action": "write", "path": "big.txt", "content": big_content})
    assert "크기" in result or "초과" in result or "제한" in result
    assert not (workspace / "big.txt").exists()


def test_file_write_accepts_content_at_size_limit(workspace):
    """정확히 1MB인 content는 허용한다."""
    exact_content = "x" * (1024 * 1024)
    result = runner.run_file({"action": "write", "path": "limit.txt", "content": exact_content})
    assert "저장" in result
    assert (workspace / "limit.txt").exists()


def test_file_write_rejects_when_file_count_exceeded(workspace):
    """파일 100개 초과 시 쓰기를 거부한다."""
    for i in range(100):
        (workspace / f"file_{i:03d}.txt").write_text("data")
    result = runner.run_file({"action": "write", "path": "overflow.txt", "content": "new"})
    assert "개수" in result or "초과" in result or "제한" in result
    assert not (workspace / "overflow.txt").exists()


def test_file_write_allows_overwrite_existing(workspace):
    """이미 있는 파일 덮어쓰기는 개수 제한에 걸리지 않는다."""
    for i in range(100):
        (workspace / f"file_{i:03d}.txt").write_text("data")
    result = runner.run_file({"action": "write", "path": "file_000.txt", "content": "updated"})
    assert "저장" in result


# ── file tool — binary / hwpx / pdf ──────────────────────────────────────────

def test_file_read_binary_with_replace(workspace):
    """UTF-8 디코딩 불가 파일은 오류 없이 읽힌다."""
    (workspace / "bin.dat").write_bytes(b"\x9f\x9f\x9f")
    result = runner.run_file({"action": "read", "path": "bin.dat"})
    assert result is not None  # 에러 없이 반환


def test_file_read_hwp(workspace):
    """HWP 파일은 hwp5txt CLI로 파싱한다."""
    from unittest.mock import MagicMock
    hwp_file = workspace / "doc.hwp"
    hwp_file.write_bytes(b"fake hwp binary")

    with patch("koclaw.sandbox_runner.subprocess") as mock_subprocess:
        mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="한글 문서 내용\n")
        result = runner.run_file({"action": "read", "path": "doc.hwp"})

    assert "한글 문서 내용" in result


def test_file_read_hwp_error(workspace):
    """HWP 파싱 실패 시 에러 메시지를 반환한다."""
    from unittest.mock import MagicMock
    hwp_file = workspace / "doc.hwp"
    hwp_file.write_bytes(b"fake hwp binary")

    with patch("koclaw.sandbox_runner.subprocess") as mock_subprocess:
        mock_subprocess.run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        result = runner.run_file({"action": "read", "path": "doc.hwp"})

    assert "HWP" in result or "오류" in result


def test_file_read_hwp_error_does_not_expose_stderr(workspace):
    """HWP 파싱 실패 시 내부 stderr 내용을 사용자에게 노출하지 않는다."""
    from unittest.mock import MagicMock
    hwp_file = workspace / "doc.hwp"
    hwp_file.write_bytes(b"fake hwp binary")

    with patch("koclaw.sandbox_runner.subprocess") as mock_subprocess:
        mock_subprocess.run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="내부 시스템 경로: /usr/local/bin/hwp5txt crashed at 0x00ff",
        )
        result = runner.run_file({"action": "read", "path": "doc.hwp"})

    assert "내부 시스템 경로" not in result
    assert "/usr/local/bin" not in result
    assert "오류" in result


def test_file_read_hwpx(workspace):
    """HWPX 파일은 python-hwpx로 파싱한다."""
    from unittest.mock import MagicMock
    hwpx_file = workspace / "doc.hwpx"
    hwpx_file.write_bytes(b"fake hwpx")

    mock_extractor = MagicMock()
    mock_extractor.__enter__.return_value.extract_text.return_value = "한글 문서 내용"
    mock_extractor.__exit__.return_value = False
    mock_hwpx = MagicMock()
    mock_hwpx.TextExtractor.return_value = mock_extractor

    import sys
    orig = sys.modules.get("hwpx")
    sys.modules["hwpx"] = mock_hwpx
    try:
        result = runner.run_file({"action": "read", "path": "doc.hwpx"})
    finally:
        if orig is None:
            sys.modules.pop("hwpx", None)
        else:
            sys.modules["hwpx"] = orig

    assert "한글 문서 내용" in result


def test_file_read_pdf(workspace):
    """PDF 파일은 pypdf로 파싱한다."""
    from unittest.mock import MagicMock
    pdf_file = workspace / "doc.pdf"
    pdf_file.write_bytes(b"%PDF-fake")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "PDF 텍스트 내용"

    with patch("koclaw.sandbox_runner.PdfReader") as MockReader:
        MockReader.return_value.pages = [mock_page]
        result = runner.run_file({"action": "read", "path": "doc.pdf"})

    assert "PDF 텍스트 내용" in result


def test_file_read_docx(workspace):
    """DOCX 파일은 python-docx로 파싱한다."""
    from unittest.mock import MagicMock, patch
    docx_file = workspace / "report.docx"
    docx_file.write_bytes(b"PK\x03\x04fake docx")

    mock_doc = MagicMock()
    mock_doc.paragraphs = [
        MagicMock(text="첫 번째 단락"),
        MagicMock(text="두 번째 단락"),
    ]

    with patch.dict("sys.modules", {"docx": MagicMock(Document=MagicMock(return_value=mock_doc))}):
        result = runner.run_file({"action": "read", "path": "report.docx"})

    assert "첫 번째 단락" in result
    assert "두 번째 단락" in result


# ── execute_code tool ─────────────────────────────────────────────────────────

def test_execute_code_simple_print(workspace):
    result = runner.run_execute_code({"code": "print('hello')"})
    assert "hello" in result


def test_execute_code_multiline_output(workspace):
    code = "for i in range(3):\n    print(i)"
    result = runner.run_execute_code({"code": code})
    assert "0" in result
    assert "1" in result
    assert "2" in result


def test_execute_code_empty_code_returns_error(workspace):
    result = runner.run_execute_code({"code": "   "})
    assert "오류" in result


def test_execute_code_unsupported_language_returns_error(workspace):
    result = runner.run_execute_code({"code": "print(1)", "language": "ruby"})
    assert "오류" in result or "지원" in result


def test_execute_code_stderr_included_in_result(workspace):
    result = runner.run_execute_code({"code": "raise ValueError('테스트 오류')"})
    assert "ValueError" in result or "오류" in result


def test_execute_code_timeout_returns_error(workspace, monkeypatch):
    import koclaw.sandbox_runner as r
    monkeypatch.setattr(r, "_CODE_TIMEOUT_SEC", 0.01)
    result = runner.run_execute_code({"code": "import time; time.sleep(9999)"})
    assert "타임아웃" in result


def test_execute_code_no_output_returns_message(workspace):
    result = runner.run_execute_code({"code": "x = 1 + 1"})
    assert "출력 없음" in result


def test_execute_code_output_truncated_when_too_long(workspace, monkeypatch):
    import koclaw.sandbox_runner as r
    monkeypatch.setattr(r, "_MAX_OUTPUT_BYTES", 10)
    result = runner.run_execute_code({"code": "print('a' * 100)"})
    assert "잘렸습니다" in result
