import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

try:
    from docx import Document
except ImportError:
    Document = None  # type: ignore[assignment,misc]

from koclaw.core.prompt_guard import wrap_external_content

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".log"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
PDF_EXTENSIONS = {".pdf"}
HWPX_EXTENSIONS = {".hwpx"}
DOCX_EXTENSIONS = {".docx"}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class ParsedFile:
    name: str
    content: str
    mime_type: str

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")

    def to_image_part(self) -> dict:
        return {"type": "image", "data": self.content, "mime_type": self.mime_type}

    def to_llm_context(self) -> str:
        return wrap_external_content(f"첨부파일: {self.name}", self.content)


class FileParser:
    async def parse(self, path: str | Path) -> ParsedFile:
        path = Path(path)
        ext = path.suffix.lower()

        if ext in TEXT_EXTENSIONS:
            return self._parse_text(path)
        if ext in PDF_EXTENSIONS:
            return self._parse_pdf(path)
        if ext in HWPX_EXTENSIONS:
            return self._parse_hwpx(path)
        if ext in DOCX_EXTENSIONS:
            return self._parse_docx(path)
        if ext in IMAGE_EXTENSIONS:
            return self._parse_image(path)
        return ParsedFile(
            name=path.name,
            content=f"지원하지 않는 파일 형식입니다: {ext}",
            mime_type="application/octet-stream",
        )

    def _parse_text(self, path: Path) -> ParsedFile:
        content = path.read_text(encoding="utf-8", errors="replace")
        mime = mimetypes.guess_type(path.name)[0] or "text/plain"
        return ParsedFile(name=path.name, content=content, mime_type=mime)

    def _parse_pdf(self, path: Path) -> ParsedFile:
        try:
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            content = "\n\n".join(pages).strip()
        except Exception as e:
            content = f"PDF 파싱 오류: {e}"
        return ParsedFile(name=path.name, content=content, mime_type="application/pdf")

    def _parse_hwpx(self, path: Path) -> ParsedFile:
        try:
            from hwpx import TextExtractor
            with TextExtractor(str(path)) as extractor:
                content = extractor.extract_text(skip_empty=True)
        except ImportError:
            content = "HWPX 파싱 불가: python-hwpx 패키지가 설치되지 않았습니다."
        except Exception as e:
            content = f"HWPX 파싱 오류: {e}"
        return ParsedFile(name=path.name, content=content, mime_type="application/x-hwpx")

    def _parse_docx(self, path: Path) -> ParsedFile:
        try:
            doc = Document(str(path))
            content = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            content = "DOCX 파싱 불가: python-docx 패키지가 설치되지 않았습니다."
        except Exception as e:
            content = f"DOCX 파싱 오류: {e}"
        return ParsedFile(name=path.name, content=content, mime_type=DOCX_MIME)

    def _parse_image(self, path: Path) -> ParsedFile:
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        data = base64.b64encode(path.read_bytes()).decode("utf-8")
        return ParsedFile(name=path.name, content=data, mime_type=mime)
