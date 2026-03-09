"""
컨테이너 내부에서 실행되는 sandbox runner.

/workspace/.sandbox_input.json 을 읽어 tool을 실행하고 결과를 stdout으로 출력한다.
/workspace/ 만 접근 가능 (network none).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader

_CODE_TIMEOUT_SEC = 10.0
_MAX_OUTPUT_BYTES = 10 * 1024  # 10KB

WORKSPACE = Path("/workspace")
PARENT_WORKSPACE: Path | None = (
    Path("/parent_workspace") if Path("/parent_workspace").exists() else None
)
INPUT_FILE = WORKSPACE / ".sandbox_input.json"
INSTANT_DIR = ".instant"

_MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1MB
_MAX_FILE_COUNT = 100


def run_memory(args: dict) -> str:
    memory_file = WORKSPACE / "MEMORY.md"
    action = args.get("action")

    if action == "read":
        if not memory_file.exists():
            return "저장된 기억이 없습니다."
        text = memory_file.read_text(encoding="utf-8")
        return text if text.strip() else "저장된 기억이 비어 있습니다."

    if action == "write":
        content = args.get("content", "")
        memory_file.write_text(content, encoding="utf-8")
        return "✅ 기억이 저장되었습니다."

    return f"알 수 없는 action: {action}"


def _safe_path_in(base: Path, path_str: str) -> Path | None:
    """path_str이 base 하위인지 검증 후 Path 반환."""
    if not path_str:
        return None
    try:
        candidate = (base / path_str).resolve()
        candidate.relative_to(base.resolve())
        return candidate
    except (ValueError, Exception):
        return None


def _safe_path(path_str: str) -> Path | None:
    """path_str이 WORKSPACE 하위인지 검증 후 Path 반환. 탈출 시도면 None."""
    if not path_str:
        return None
    try:
        candidate = (WORKSPACE / path_str).resolve()
        candidate.relative_to(WORKSPACE.resolve())
        return candidate
    except (ValueError, Exception):
        return None


def _base_for_scope(scope: str) -> Path:
    return WORKSPACE / INSTANT_DIR if scope == "instant" else WORKSPACE


def run_file(args: dict) -> str:
    action = args.get("action")
    path_str = args.get("path", "")
    scope = args.get("scope", "session")
    base = _base_for_scope(scope)

    if action == "list":
        if not base.exists():
            return "저장된 파일이 없습니다."
        files = [f.name for f in base.iterdir() if f.is_file() and not f.name.startswith(".")]
        return "\n".join(files) if files else "저장된 파일이 없습니다."

    target = _safe_path(path_str) if path_str else None

    if action == "read":
        if target is None:
            return "허용되지 않은 경로입니다."
        if not target.exists():
            # parent workspace fallback
            if PARENT_WORKSPACE is not None:
                parent_target = _safe_path_in(PARENT_WORKSPACE, path_str)
                if parent_target is not None and parent_target.exists():
                    target = parent_target
                else:
                    return f"파일을 찾을 수 없습니다: {path_str}"
            else:
                return f"파일을 찾을 수 없습니다: {path_str}"
        ext = target.suffix.lower()
        if ext == ".hwp":
            result = subprocess.run(
                ["hwp5txt", str(target)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if result.returncode != 0:
                return "HWP 파싱 오류: 파일을 처리할 수 없습니다"
            return result.stdout.strip()
        if ext == ".hwpx":
            try:
                from hwpx import TextExtractor
                with TextExtractor(str(target)) as extractor:
                    return extractor.extract_text(skip_empty=True)
            except ImportError:
                return "HWPX 파싱 불가: python-hwpx 패키지가 설치되지 않았습니다."
            except Exception as e:
                return f"HWPX 파싱 오류: {e}"
        if ext == ".pdf":
            try:
                reader = PdfReader(str(target))
                pages = [page.extract_text() or "" for page in reader.pages]
                return "\n\n".join(pages).strip()
            except Exception as e:
                return f"PDF 파싱 오류: {e}"
        if ext == ".docx":
            try:
                from docx import Document
                doc = Document(str(target))
                return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
            except ImportError:
                return "DOCX 파싱 불가: python-docx 패키지가 설치되지 않았습니다."
            except Exception as e:
                return f"DOCX 파싱 오류: {e}"
        return target.read_text(encoding="utf-8", errors="replace")

    if action == "write":
        content = args.get("content", "")
        if target is None:
            return "허용되지 않은 경로입니다."
        if len(content.encode("utf-8")) > _MAX_FILE_SIZE_BYTES:
            return "오류: 파일 크기 제한(1MB) 초과입니다."
        if not target.exists():
            existing = sum(1 for f in base.rglob("*") if f.is_file()) if base.exists() else 0
            if existing >= _MAX_FILE_COUNT:
                return f"오류: 파일 개수 제한({_MAX_FILE_COUNT}개) 초과입니다."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"✅ {path_str} 저장 완료"

    if action == "delete":
        if target is None:
            return "허용되지 않은 경로입니다."
        if not target.exists():
            return f"파일이 없습니다: {path_str}"
        target.unlink()
        return f"🗑️ {path_str} 삭제 완료"

    return f"알 수 없는 action: {action}"


def run_execute_code(args: dict) -> str:
    code = args.get("code", "")
    language = args.get("language", "python").lower()

    if not code.strip():
        return "오류: 실행할 코드가 없습니다."

    if language != "python":
        return f"오류: 지원하지 않는 언어입니다: {language}. 현재 지원: python"

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8", delete=False, dir=WORKSPACE
        ) as f:
            f.write(code)
            tmp_path = Path(f.name)

        result = subprocess.run(
            [sys.executable, str(tmp_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_CODE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return f"오류: 코드 실행 타임아웃 ({_CODE_TIMEOUT_SEC:.0f}초)"
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()

    parts = []
    if result.stdout:
        stdout = result.stdout
        if len(stdout.encode("utf-8")) > _MAX_OUTPUT_BYTES:
            stdout = stdout.encode("utf-8")[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            stdout += "\n... (출력이 너무 길어 잘렸습니다)"
        parts.append(stdout.rstrip())
    if result.stderr:
        parts.append(f"[오류]\n{result.stderr.rstrip()}")

    return "\n".join(parts) if parts else "(출력 없음)"


DISPATCH: dict[str, callable] = {
    "memory": run_memory,
    "file": run_file,
    "execute_code": run_execute_code,
}


def main() -> None:
    if not INPUT_FILE.exists():
        print("오류: .sandbox_input.json 파일이 없습니다.", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
        tool_name: str = data["tool"]
        tool_args: dict = data.get("args", {})
    except (json.JSONDecodeError, KeyError) as e:
        print(f"오류: 입력 파싱 실패 - {e}", file=sys.stderr)
        sys.exit(1)

    handler = DISPATCH.get(tool_name)
    if handler is None:
        print(f"오류: 알 수 없는 tool '{tool_name}'", file=sys.stderr)
        sys.exit(1)

    result = handler(tool_args)
    print(result)


if __name__ == "__main__":
    main()
