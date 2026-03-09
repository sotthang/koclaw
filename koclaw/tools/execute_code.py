from koclaw.core.tool import Tool


class ExecuteCodeTool(Tool):
    name = "execute_code"
    description = (
        "Python 코드를 Docker 샌드박스 안에서 안전하게 실행하고 출력 결과를 반환합니다. "
        "인터넷 접근은 불가하며 실행 시간은 최대 10초입니다."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "실행할 Python 코드"},
            "language": {
                "type": "string",
                "description": "프로그래밍 언어 (현재 'python'만 지원)",
                "enum": ["python"],
                "default": "python",
            },
        },
        "required": ["code"],
    }
    is_sandboxed = True

    async def execute(self, code: str, language: str = "python") -> str:
        # is_sandboxed=True 이므로 Agent가 sandbox.execute()를 직접 호출한다.
        # 이 메서드는 sandbox 없이 직접 호출되는 경우의 fallback이다.
        return "오류: 이 도구는 샌드박스 환경이 필요합니다."
