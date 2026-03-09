

class TestFileTool:
    def _make_tool(self, tmp_path, session_id="ch_001"):
        from koclaw.tools.file import FileTool
        workspace = tmp_path / "workspace"
        return FileTool(workspace=workspace, session_id=session_id)

    def test_is_sandboxed(self):
        from koclaw.tools.file import FileTool
        assert FileTool.is_sandboxed is True

    # ── session scope ──────────────────────────────────────────────────────────

    async def test_writes_file_to_session_scope(self, tmp_path):
        tool = self._make_tool(tmp_path)
        result = await tool.execute(action="write", path="result.txt", content="안녕하세요")

        expected = tmp_path / "workspace" / "ch_001" / "result.txt"
        assert expected.exists()
        assert expected.read_text(encoding="utf-8") == "안녕하세요"
        assert "저장" in result or "완료" in result

    async def test_reads_file_from_session_scope(self, tmp_path):
        tool = self._make_tool(tmp_path)
        file = tmp_path / "workspace" / "ch_001" / "note.txt"
        file.parent.mkdir(parents=True)
        file.write_text("세션 파일 내용", encoding="utf-8")

        result = await tool.execute(action="read", path="note.txt")
        assert "세션 파일 내용" in result

    async def test_lists_session_files(self, tmp_path):
        tool = self._make_tool(tmp_path)
        base = tmp_path / "workspace" / "ch_001"
        base.mkdir(parents=True)
        (base / "a.txt").write_text("a")
        (base / "b.md").write_text("b")

        result = await tool.execute(action="list")
        assert "a.txt" in result
        assert "b.md" in result

    async def test_deletes_file_from_session_scope(self, tmp_path):
        tool = self._make_tool(tmp_path)
        file = tmp_path / "workspace" / "ch_001" / "temp.txt"
        file.parent.mkdir(parents=True)
        file.write_text("삭제될 파일")

        result = await tool.execute(action="delete", path="temp.txt")
        assert not file.exists()
        assert "삭제" in result

    # ── instant scope ──────────────────────────────────────────────────────────

    async def test_writes_file_to_instant_scope(self, tmp_path):
        tool = self._make_tool(tmp_path)
        result = await tool.execute(action="write", path="tmp.txt", content="임시 내용", scope="instant")

        expected = tmp_path / "workspace" / "ch_001" / ".instant" / "tmp.txt"
        assert expected.exists()
        assert expected.read_text(encoding="utf-8") == "임시 내용"
        assert "저장" in result or "완료" in result

    async def test_reads_file_from_instant_scope(self, tmp_path):
        tool = self._make_tool(tmp_path)
        file = tmp_path / "workspace" / "ch_001" / ".instant" / "calc.txt"
        file.parent.mkdir(parents=True)
        file.write_text("계산 결과", encoding="utf-8")

        result = await tool.execute(action="read", path="calc.txt", scope="instant")
        assert "계산 결과" in result

    async def test_lists_instant_files(self, tmp_path):
        tool = self._make_tool(tmp_path)
        base = tmp_path / "workspace" / "ch_001" / ".instant"
        base.mkdir(parents=True)
        (base / "x.txt").write_text("x")
        (base / "y.csv").write_text("y")

        result = await tool.execute(action="list", scope="instant")
        assert "x.txt" in result
        assert "y.csv" in result

    async def test_deletes_file_from_instant_scope(self, tmp_path):
        tool = self._make_tool(tmp_path)
        file = tmp_path / "workspace" / "ch_001" / ".instant" / "old.txt"
        file.parent.mkdir(parents=True)
        file.write_text("삭제될 임시 파일")

        result = await tool.execute(action="delete", path="old.txt", scope="instant")
        assert not file.exists()
        assert "삭제" in result

    async def test_instant_files_not_visible_in_session_list(self, tmp_path):
        """instant 파일은 session list에 노출되지 않아야 함"""
        tool = self._make_tool(tmp_path)
        await tool.execute(action="write", path="keep.txt", content="세션 파일", scope="session")
        await tool.execute(action="write", path="tmp.txt", content="임시 파일", scope="instant")

        result = await tool.execute(action="list", scope="session")
        assert "keep.txt" in result
        assert "tmp.txt" not in result

    # ── cleanup_instant ────────────────────────────────────────────────────────

    async def test_cleanup_instant_removes_instant_dir(self, tmp_path):
        from koclaw.tools.file import cleanup_instant
        tool = self._make_tool(tmp_path)
        await tool.execute(action="write", path="tmp.txt", content="임시", scope="instant")

        instant_dir = tmp_path / "workspace" / "ch_001" / ".instant"
        assert instant_dir.exists()

        cleanup_instant(tmp_path / "workspace", "ch_001")
        assert not instant_dir.exists()

    async def test_cleanup_instant_does_not_touch_session_files(self, tmp_path):
        from koclaw.tools.file import cleanup_instant
        tool = self._make_tool(tmp_path)
        await tool.execute(action="write", path="keep.txt", content="세션 파일", scope="session")
        await tool.execute(action="write", path="tmp.txt", content="임시", scope="instant")

        cleanup_instant(tmp_path / "workspace", "ch_001")

        session_file = tmp_path / "workspace" / "ch_001" / "keep.txt"
        assert session_file.exists()

    def test_cleanup_instant_is_noop_when_no_instant_dir(self, tmp_path):
        from koclaw.tools.file import cleanup_instant
        cleanup_instant(tmp_path / "workspace", "ch_001")

    # ── 크기/개수 제한 ────────────────────────────────────────────────────────

    async def test_write_rejects_oversized_content(self, tmp_path):
        """1MB 초과 content는 거부한다."""
        tool = self._make_tool(tmp_path)
        big_content = "x" * (1024 * 1024 + 1)
        result = await tool.execute(action="write", path="big.txt", content=big_content)
        assert "크기" in result or "초과" in result or "제한" in result
        assert not (tmp_path / "workspace" / "ch_001" / "big.txt").exists()

    async def test_write_rejects_when_file_count_exceeded(self, tmp_path):
        """파일 100개 초과 시 쓰기를 거부한다."""
        tool = self._make_tool(tmp_path)
        base = tmp_path / "workspace" / "ch_001"
        base.mkdir(parents=True)
        for i in range(100):
            (base / f"file_{i:03d}.txt").write_text("data")
        result = await tool.execute(action="write", path="overflow.txt", content="new")
        assert "개수" in result or "초과" in result or "제한" in result
        assert not (base / "overflow.txt").exists()

    async def test_write_allows_overwrite_existing_file(self, tmp_path):
        """이미 있는 파일 덮어쓰기는 개수 제한에 걸리지 않는다."""
        tool = self._make_tool(tmp_path)
        base = tmp_path / "workspace" / "ch_001"
        base.mkdir(parents=True)
        for i in range(100):
            (base / f"file_{i:03d}.txt").write_text("data")
        result = await tool.execute(action="write", path="file_000.txt", content="updated")
        assert "저장" in result or "완료" in result

    # ── 보안 ──────────────────────────────────────────────────────────────────

    async def test_prevents_path_traversal_in_session(self, tmp_path):
        tool = self._make_tool(tmp_path)
        result = await tool.execute(action="read", path="../secret.txt")
        assert "오류" in result or "허용" in result or "잘못" in result

    async def test_prevents_path_traversal_in_instant(self, tmp_path):
        tool = self._make_tool(tmp_path)
        result = await tool.execute(action="read", path="../../etc/passwd", scope="instant")
        assert "오류" in result or "허용" in result or "잘못" in result

    # ── 엣지 케이스 ────────────────────────────────────────────────────────────

    async def test_read_nonexistent_file_returns_error(self, tmp_path):
        tool = self._make_tool(tmp_path)
        result = await tool.execute(action="read", path="없는파일.txt")
        assert "없" in result or "오류" in result

    async def test_list_returns_empty_message_when_no_files(self, tmp_path):
        tool = self._make_tool(tmp_path)
        result = await tool.execute(action="list")
        assert "없" in result or "비어" in result

    async def test_delete_nonexistent_file_returns_error(self, tmp_path):
        tool = self._make_tool(tmp_path)
        result = await tool.execute(action="delete", path="없는파일.txt")
        assert "없" in result or "오류" in result

    # ── 계층형 파일 접근 ───────────────────────────────────────────────────────

    async def test_thread_reads_parent_channel_file(self, tmp_path):
        """스레드 tool은 parent 채널에 있는 파일을 읽을 수 있다."""
        from koclaw.tools.file import FileTool
        workspace = tmp_path / "workspace"
        # 채널 파일 미리 생성
        parent_dir = workspace / "slack_C001"
        parent_dir.mkdir(parents=True)
        (parent_dir / "shared.txt").write_text("채널 공유 파일", encoding="utf-8")

        thread_tool = FileTool(
            workspace=workspace,
            session_id="slack:C001:9999.0",
            parent_session_id="slack:C001",
        )
        result = await thread_tool.execute(action="read", path="shared.txt")
        assert "채널 공유 파일" in result

    async def test_thread_write_goes_to_thread_scope(self, tmp_path):
        """스레드에서 쓴 파일은 채널이 아닌 스레드 디렉토리에 저장된다."""
        from koclaw.tools.file import FileTool
        workspace = tmp_path / "workspace"
        thread_tool = FileTool(
            workspace=workspace,
            session_id="slack:C001:9999.0",
            parent_session_id="slack:C001",
        )
        await thread_tool.execute(action="write", path="thread_file.txt", content="스레드 파일")

        thread_dir = workspace / "slack_C001_9999.0"
        parent_dir = workspace / "slack_C001"
        assert (thread_dir / "thread_file.txt").exists()
        assert not (parent_dir / "thread_file.txt").exists()

    async def test_thread_own_file_shadows_parent_file(self, tmp_path):
        """스레드에 같은 이름 파일이 있으면 parent 파일보다 우선한다."""
        from koclaw.tools.file import FileTool
        workspace = tmp_path / "workspace"
        parent_dir = workspace / "slack_C001"
        parent_dir.mkdir(parents=True)
        (parent_dir / "data.txt").write_text("채널 버전", encoding="utf-8")

        thread_dir = workspace / "slack_C001_9999.0"
        thread_dir.mkdir(parents=True)
        (thread_dir / "data.txt").write_text("스레드 버전", encoding="utf-8")

        thread_tool = FileTool(
            workspace=workspace,
            session_id="slack:C001:9999.0",
            parent_session_id="slack:C001",
        )
        result = await thread_tool.execute(action="read", path="data.txt")
        assert "스레드 버전" in result

    async def test_reads_pdf_file(self, tmp_path):
        from unittest.mock import AsyncMock, MagicMock, patch
        tool = self._make_tool(tmp_path)
        pdf_file = tmp_path / "workspace" / "ch_001" / "doc.pdf"
        pdf_file.parent.mkdir(parents=True)
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        mock_parsed = MagicMock()
        mock_parsed.content = "PDF에서 추출한 텍스트"

        with patch("koclaw.tools.file.FileParser") as MockParser:
            MockParser.return_value.parse = AsyncMock(return_value=mock_parsed)
            result = await tool.execute(action="read", path="doc.pdf")

        assert "PDF에서 추출한 텍스트" in result

    async def test_reads_docx_file_via_file_parser(self, tmp_path):
        from unittest.mock import AsyncMock, MagicMock, patch
        tool = self._make_tool(tmp_path)
        docx_file = tmp_path / "workspace" / "ch_001" / "report.docx"
        docx_file.parent.mkdir(parents=True)
        docx_file.write_bytes(b"PK\x03\x04fake docx content")

        mock_parsed = MagicMock()
        mock_parsed.content = "DOCX에서 추출한 텍스트"

        with patch("koclaw.tools.file.FileParser") as MockParser:
            MockParser.return_value.parse = AsyncMock(return_value=mock_parsed)
            result = await tool.execute(action="read", path="report.docx")

        assert "DOCX에서 추출한 텍스트" in result

    async def test_reads_hwpx_file_via_file_parser(self, tmp_path):
        from unittest.mock import AsyncMock, MagicMock, patch
        tool = self._make_tool(tmp_path)
        hwpx_file = tmp_path / "workspace" / "ch_001" / "doc.hwpx"
        hwpx_file.parent.mkdir(parents=True)
        hwpx_file.write_bytes(b"PK\x03\x04fake hwpx content")

        mock_parsed = MagicMock()
        mock_parsed.content = "HWPX에서 추출한 텍스트"

        with patch("koclaw.tools.file.FileParser") as MockParser:
            MockParser.return_value.parse = AsyncMock(return_value=mock_parsed)
            result = await tool.execute(action="read", path="doc.hwpx")

        assert "HWPX에서 추출한 텍스트" in result
