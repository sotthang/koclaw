from unittest.mock import MagicMock, patch

from koclaw.core.file_parser import FileParser, ParsedFile


class TestParsedFile:
    def test_has_name_and_content(self):
        f = ParsedFile(name="report.txt", content="내용입니다", mime_type="text/plain")
        assert f.name == "report.txt"
        assert f.content == "내용입니다"

    def test_to_llm_context(self):
        f = ParsedFile(name="report.txt", content="내용입니다", mime_type="text/plain")
        ctx = f.to_llm_context()
        assert "report.txt" in ctx
        assert "내용입니다" in ctx

    def test_to_llm_context_wraps_with_external_data_delimiters(self):
        f = ParsedFile(name="report.txt", content="내용입니다", mime_type="text/plain")
        ctx = f.to_llm_context()
        assert "[외부 데이터 시작:" in ctx
        assert "[외부 데이터 끝:" in ctx

    def test_to_llm_context_truncates_large_content(self):
        large_content = "x" * 20000
        f = ParsedFile(name="big.txt", content=large_content, mime_type="text/plain")
        ctx = f.to_llm_context()
        assert large_content not in ctx
        assert "잘림" in ctx


class TestFileParserText:
    async def test_parses_txt_file(self, tmp_path):
        txt_file = tmp_path / "hello.txt"
        txt_file.write_text("안녕하세요 텍스트 파일입니다", encoding="utf-8")

        parser = FileParser()
        result = await parser.parse(path=txt_file)

        assert result.name == "hello.txt"
        assert "텍스트 파일입니다" in result.content

    async def test_parses_md_file(self, tmp_path):
        md_file = tmp_path / "README.md"
        md_file.write_text("# 제목\n내용입니다", encoding="utf-8")

        parser = FileParser()
        result = await parser.parse(path=md_file)

        assert "제목" in result.content

    async def test_parses_csv_file(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("이름,나이\n홍길동,30\n김철수,25", encoding="utf-8")

        parser = FileParser()
        result = await parser.parse(path=csv_file)

        assert "홍길동" in result.content
        assert "김철수" in result.content


class TestFileParserPDF:
    async def test_parses_pdf_file(self, tmp_path):
        pdf_file = tmp_path / "document.pdf"
        pdf_file.write_bytes(b"%PDF-fake")

        with patch("koclaw.core.file_parser.PdfReader") as mock_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "PDF에서 추출된 텍스트"
            mock_reader.return_value.pages = [mock_page]

            parser = FileParser()
            result = await parser.parse(path=pdf_file)

        assert "PDF에서 추출된 텍스트" in result.content

    async def test_pdf_read_error_returns_error_message(self, tmp_path):
        pdf_file = tmp_path / "broken.pdf"
        pdf_file.write_bytes(b"not a pdf")

        with patch("koclaw.core.file_parser.PdfReader", side_effect=Exception("파싱 오류")):
            parser = FileParser()
            result = await parser.parse(path=pdf_file)

        assert "오류" in result.content or "실패" in result.content


class TestParsedFileImage:
    def test_is_image_true_for_image_png(self):
        f = ParsedFile(name="photo.png", content="base64data", mime_type="image/png")
        assert f.is_image is True

    def test_is_image_true_for_image_jpeg(self):
        f = ParsedFile(name="photo.jpg", content="base64data", mime_type="image/jpeg")
        assert f.is_image is True

    def test_is_image_false_for_text_plain(self):
        f = ParsedFile(name="doc.txt", content="hello", mime_type="text/plain")
        assert f.is_image is False

    def test_is_image_false_for_pdf(self):
        f = ParsedFile(name="doc.pdf", content="data", mime_type="application/pdf")
        assert f.is_image is False

    def test_to_image_part_returns_multimodal_dict(self):
        f = ParsedFile(name="photo.png", content="abc123==", mime_type="image/png")
        part = f.to_image_part()
        assert part == {"type": "image", "data": "abc123==", "mime_type": "image/png"}


class TestFileParserImage:
    async def test_parses_image_as_base64(self, tmp_path):
        img_file = tmp_path / "photo.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        parser = FileParser()
        result = await parser.parse(path=img_file)

        assert result.mime_type == "image/png"
        assert result.content != ""  # base64 인코딩된 데이터

    async def test_jpg_image_detected(self, tmp_path):
        jpg_file = tmp_path / "photo.jpg"
        jpg_file.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        parser = FileParser()
        result = await parser.parse(path=jpg_file)

        assert result.mime_type == "image/jpeg"


class TestFileParserHWPX:
    async def test_parses_hwpx_file(self, tmp_path):
        hwpx_file = tmp_path / "doc.hwpx"
        hwpx_file.write_bytes(b"PK\x03\x04fake hwpx content")

        mock_extractor = MagicMock()
        mock_extractor.__enter__.return_value.extract_text.return_value = "한글 문서 내용입니다"
        mock_extractor.__exit__.return_value = False
        mock_hwpx = MagicMock()
        mock_hwpx.TextExtractor.return_value = mock_extractor

        with patch.dict("sys.modules", {"hwpx": mock_hwpx}):
            parser = FileParser()
            result = await parser.parse(path=hwpx_file)

        assert "한글 문서 내용입니다" in result.content
        assert result.name == "doc.hwpx"
        assert result.mime_type == "application/x-hwpx"

    async def test_hwpx_parse_error_returns_error_message(self, tmp_path):
        hwpx_file = tmp_path / "broken.hwpx"
        hwpx_file.write_bytes(b"not a zip")

        mock_extractor = MagicMock()
        mock_extractor.__enter__.side_effect = Exception("파싱 실패")
        mock_hwpx = MagicMock()
        mock_hwpx.TextExtractor.return_value = mock_extractor

        with patch.dict("sys.modules", {"hwpx": mock_hwpx}):
            parser = FileParser()
            result = await parser.parse(path=hwpx_file)

        assert "오류" in result.content or "실패" in result.content

    async def test_hwpx_returns_error_when_package_not_installed(self, tmp_path):
        hwpx_file = tmp_path / "doc.hwpx"
        hwpx_file.write_bytes(b"PK\x03\x04fake")

        with patch.dict("sys.modules", {"hwpx": None}):
            parser = FileParser()
            result = await parser.parse(path=hwpx_file)

        assert "설치" in result.content or "python-hwpx" in result.content


class TestFileParserDOCX:
    async def test_parses_docx_file(self, tmp_path):
        docx_file = tmp_path / "report.docx"
        docx_file.write_bytes(b"PK\x03\x04fake docx content")

        mock_doc = MagicMock()
        mock_doc.paragraphs = [
            MagicMock(text="첫 번째 단락"),
            MagicMock(text="두 번째 단락"),
        ]
        with patch("koclaw.core.file_parser.Document", return_value=mock_doc):
            parser = FileParser()
            result = await parser.parse(path=docx_file)

        assert "첫 번째 단락" in result.content
        assert "두 번째 단락" in result.content
        assert result.name == "report.docx"
        assert result.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    async def test_docx_parse_error_returns_error_message(self, tmp_path):
        docx_file = tmp_path / "broken.docx"
        docx_file.write_bytes(b"not a docx")

        with patch("koclaw.core.file_parser.Document", side_effect=Exception("파싱 오류")):
            parser = FileParser()
            result = await parser.parse(path=docx_file)

        assert "오류" in result.content or "실패" in result.content

    async def test_docx_returns_error_when_package_not_installed(self, tmp_path):
        docx_file = tmp_path / "report.docx"
        docx_file.write_bytes(b"PK\x03\x04fake")

        with patch("koclaw.core.file_parser.Document", side_effect=ImportError):
            parser = FileParser()
            result = await parser.parse(path=docx_file)

        assert "설치" in result.content or "python-docx" in result.content


class TestFileParserUnsupported:
    async def test_unsupported_format_returns_message(self, tmp_path):
        exe_file = tmp_path / "program.exe"
        exe_file.write_bytes(b"MZ" + b"\x00" * 100)

        parser = FileParser()
        result = await parser.parse(path=exe_file)

        assert "지원하지 않" in result.content or "미지원" in result.content
