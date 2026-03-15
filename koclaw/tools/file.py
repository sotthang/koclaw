import shutil
from pathlib import Path

from koclaw.core.file_parser import FileParser
from koclaw.core.tool import Tool

PARSER_EXTENSIONS = {".pdf", ".docx", ".hwpx"}
INSTANT_DIR = ".instant"


def cleanup_instant(workspace: str | Path, session_id: str) -> None:
    """agent.run() 완료 후 instant 파일 정리"""
    instant_dir = Path(workspace) / session_id.replace(":", "_") / INSTANT_DIR
    if instant_dir.exists():
        shutil.rmtree(instant_dir)


class FileTool(Tool):
    name = "file"
    description = (
        "파일 읽기/쓰기/목록/삭제. "
        "scope=instant: 이번 답변 생성에만 쓰는 임시 파일 (답변 완료 후 자동 삭제). "
        "scope=session: 같은 채널에서 계속 꺼내 쓸 파일 (채널 내 유지, 기본값)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "list", "delete"],
                "description": "read: 읽기, write: 쓰기, list: 목록, delete: 삭제",
            },
            "path": {
                "type": "string",
                "description": "파일 경로 (list 제외 필수)",
            },
            "scope": {
                "type": "string",
                "enum": ["session", "instant"],
                "description": "session: 채널 내 유지 (기본값), instant: 이번 답변 후 자동 삭제",
            },
            "content": {
                "type": "string",
                "description": "저장할 내용 (write 시 필수)",
            },
        },
        "required": ["action"],
    }
    is_sandboxed = True

    def __init__(
        self,
        workspace: str | Path,
        session_id: str,
        parent_session_id: str | None = None,
    ):
        safe_id = session_id.replace(":", "_")
        self._session_base = Path(workspace) / safe_id
        self._instant_base = Path(workspace) / safe_id / INSTANT_DIR
        self._parent_base: Path | None = (
            Path(workspace) / parent_session_id.replace(":", "_") if parent_session_id else None
        )

    def _base(self, scope: str) -> Path:
        return self._instant_base if scope == "instant" else self._session_base

    def _resolve(self, base: Path, path: str) -> Path | None:
        """path traversal 방지: base 밖을 가리키면 None 반환"""
        target = (base / path).resolve()
        try:
            target.relative_to(base.resolve())
        except ValueError:
            return None
        return target

    async def execute(
        self,
        action: str,
        path: str = "",
        scope: str = "session",
        content: str = "",
    ) -> str:
        base = self._base(scope)

        if action == "list":
            if not base.exists():
                return "저장된 파일이 없습니다."
            files = [f.name for f in base.iterdir() if f.is_file()]
            if not files:
                return "저장된 파일이 없습니다."
            return "\n".join(files)

        if not path:
            return "오류: path를 지정해 주세요."

        target = self._resolve(base, path)
        if target is None:
            return "오류: 허용되지 않는 경로입니다."

        if action == "read":
            if not target.exists():
                # parent 채널에서 fallback 읽기
                if self._parent_base is not None:
                    parent_target = self._resolve(self._parent_base, path)
                    if parent_target is not None and parent_target.exists():
                        target = parent_target
                    else:
                        return f"오류: '{path}' 파일이 없습니다."
                else:
                    return f"오류: '{path}' 파일이 없습니다."
            if target.suffix.lower() in PARSER_EXTENSIONS:
                parsed = await FileParser().parse(target)
                return parsed.content
            return target.read_text(encoding="utf-8", errors="replace")

        if action == "write":
            from koclaw.core import config as _cfg

            if len(content.encode("utf-8")) > _cfg.MAX_FILE_WRITE_BYTES:
                max_mb = _cfg.MAX_FILE_WRITE_BYTES // 1024 // 1024
                return f"오류: 파일 크기 제한({max_mb}MB) 초과입니다."
            if not target.exists():
                existing = sum(1 for f in base.rglob("*") if f.is_file()) if base.exists() else 0
                if existing >= _cfg.MAX_FILE_COUNT:
                    return f"오류: 파일 개수 제한({_cfg.MAX_FILE_COUNT}개) 초과입니다."
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"✅ '{path}' 저장 완료."

        if action == "delete":
            if not target.exists():
                return f"오류: '{path}' 파일이 없습니다."
            target.unlink()
            return f"🗑️ '{path}' 삭제 완료."

        return f"알 수 없는 action: {action}"
