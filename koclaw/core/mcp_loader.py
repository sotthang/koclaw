"""MCP(Model Context Protocol) 서버 연결 및 Tool 래핑 모듈.

mcp_servers.json 에 정의된 서버들에 연결해 tool을 동적으로 ToolRegistry에 등록한다.

지원 transport:
- stdio: 로컬 프로세스 실행 (npx, uvx, python 등)
- sse:   HTTP SSE 엔드포인트

설정 예시 (mcp_servers.json):
[
  {
    "name": "filesystem",
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  },
  {
    "name": "my-server",
    "transport": "sse",
    "url": "http://localhost:8080/sse"
  }
]
"""

import json
import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from koclaw.core.tool import Tool, ToolRegistry

logger = logging.getLogger(__name__)


class MCPToolWrapper(Tool):
    """MCP tool 하나를 koclaw Tool로 래핑한다."""

    is_sandboxed = False
    needs_session_context = False

    def __init__(self, session: Any, mcp_tool: Any, server_name: str) -> None:
        self.name = mcp_tool.name
        self.description = mcp_tool.description or f"{server_name} MCP tool"
        self.parameters = mcp_tool.inputSchema
        self._session = session
        self._server_name = server_name

    async def execute(self, **kwargs) -> str:
        try:
            result = await self._session.call_tool(self.name, kwargs)
        except Exception as e:
            logger.error("[mcp] %s/%s 호출 실패: %s", self._server_name, self.name, e)
            return f"MCP tool 호출 실패 ({self._server_name}/{self.name}): {e}"

        if result.isError:
            texts = [c.text for c in result.content if hasattr(c, "text")]
            return "MCP 오류: " + " ".join(texts)

        parts: list[str] = []
        for content in result.content:
            if hasattr(content, "text"):
                parts.append(content.text)
            elif hasattr(content, "data"):
                # 이미지 등 바이너리 — 타입만 안내
                mime = getattr(content, "mimeType", "binary")
                parts.append(f"[{mime} 데이터]")
            else:
                parts.append(str(content))
        return "\n".join(parts) if parts else "(빈 응답)"


class MCPServerManager:
    """여러 MCP 서버에 대한 연결을 관리하고 Tool 목록을 노출한다."""

    def __init__(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._tools: list[MCPToolWrapper] = []

    async def connect(self, server_config: dict) -> None:
        """단일 MCP 서버에 연결하고 tool을 등록한다."""
        try:
            import mcp
            import mcp.client.sse
            import mcp.client.stdio
        except ImportError:
            raise ImportError("MCP를 사용하려면 'uv add mcp' 또는 pip install mcp 를 실행하세요.")

        name = server_config.get("name", "unknown")
        transport = server_config.get("transport", "stdio")

        try:
            if transport == "stdio":
                params = mcp.client.stdio.StdioServerParameters(
                    command=server_config["command"],
                    args=server_config.get("args", []),
                    env=server_config.get("env"),
                )
                read, write = await self._exit_stack.enter_async_context(
                    mcp.client.stdio.stdio_client(params)
                )
            elif transport == "sse":
                read, write = await self._exit_stack.enter_async_context(
                    mcp.client.sse.sse_client(
                        url=server_config["url"],
                        headers=server_config.get("headers"),
                    )
                )
            else:
                logger.error("[mcp] 지원하지 않는 transport: %s (server=%s)", transport, name)
                return

            session = await self._exit_stack.enter_async_context(mcp.ClientSession(read, write))
            await session.initialize()

            result = await session.list_tools()
            for mcp_tool in result.tools:
                self._tools.append(MCPToolWrapper(session, mcp_tool, name))

            logger.info(
                "[mcp] 서버 연결됨: %s (%s), tool %d개 등록",
                name,
                transport,
                len(result.tools),
            )
        except Exception as e:
            logger.error("[mcp] 서버 연결 실패: %s — %s", name, e)

    def register_all(self, registry: ToolRegistry) -> None:
        """등록된 모든 MCP tool을 ToolRegistry에 추가한다."""
        for tool in self._tools:
            existing = registry.get(tool.name)
            if existing is not None:
                logger.warning(
                    "[mcp] tool 이름 충돌 '%s' — 기존 tool을 MCP tool로 덮어씁니다", tool.name
                )
            registry.register(tool)

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    async def close(self) -> None:
        await self._exit_stack.aclose()


async def load_mcp_servers(
    config_path: str | Path,
    registry: ToolRegistry,
) -> MCPServerManager | None:
    """설정 파일을 읽어 MCP 서버들에 연결하고 ToolRegistry에 tool을 등록한다.

    설정 파일이 없으면 None을 반환한다.
    """
    path = Path(config_path)
    if not path.exists():
        return None

    try:
        configs: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("[mcp] 설정 파일 파싱 실패 (%s): %s", path, e)
        return None

    if not configs:
        return None

    manager = MCPServerManager()
    for config in configs:
        await manager.connect(config)

    manager.register_all(registry)
    logger.info("[mcp] 총 %d개 MCP tool 등록 완료", manager.tool_count)
    return manager
