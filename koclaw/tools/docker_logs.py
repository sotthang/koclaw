from __future__ import annotations

import asyncio
import logging

import docker.errors

import docker
from koclaw.core.tool import Tool

logger = logging.getLogger(__name__)

_DEFAULT_CONTAINER = "koclaw"
_DEFAULT_TAIL = 100


class DockerLogsTool(Tool):
    name = "docker_logs"
    description = (
        "Docker 컨테이너 로그를 조회하거나 실행 중인 컨테이너 목록을 확인합니다. "
        "봇 자신의 로그를 확인하거나 관련 컨테이너 상태를 점검할 때 사용하세요."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["logs", "list"],
                "description": "logs: 컨테이너 로그 조회 | list: 실행 중인 컨테이너 목록",
            },
            "container": {
                "type": "string",
                "description": f"컨테이너 이름 (기본값: {_DEFAULT_CONTAINER})",
            },
            "tail": {
                "type": "integer",
                "description": f"마지막 N줄 (기본값: {_DEFAULT_TAIL})",
            },
            "since": {
                "type": "string",
                "description": "이 시간 이후 로그만 조회 (예: '1h', '30m', '2024-01-01T00:00:00')",
            },
        },
        "required": ["action"],
    }
    is_sandboxed = False

    async def execute(self, action: str, **kwargs) -> str:
        try:
            client = await asyncio.to_thread(docker.from_env)
        except Exception as e:
            logger.error("[docker_logs] Docker 연결 오류: %s", e)
            return f"오류: Docker에 연결할 수 없습니다. Docker socket이 마운트되어 있는지 확인하세요. ({e})"

        try:
            if action == "logs":
                return await self._logs(client, **kwargs)
            if action == "list":
                return await self._list(client)
            return f"오류: 알 수 없는 action: {action}"
        except Exception as e:
            logger.error("[docker_logs] 오류: %s", e)
            return f"오류: {e}"

    async def _logs(self, client: docker.DockerClient, **kwargs) -> str:
        container_name = kwargs.get("container", _DEFAULT_CONTAINER)
        tail = int(kwargs.get("tail", _DEFAULT_TAIL))
        since = kwargs.get("since", None)

        try:
            container = await asyncio.to_thread(client.containers.get, container_name)
        except docker.errors.NotFound:
            return f"'{container_name}' 컨테이너를 찾을 수 없습니다. `docker_logs(action='list')`로 컨테이너 목록을 확인하세요."

        raw = await asyncio.to_thread(container.logs, tail=tail, timestamps=True, since=since)
        logs = raw.decode("utf-8", errors="replace").strip()
        if not logs:
            return f"[{container_name}] 로그가 없습니다."
        return f"[{container_name}] 최근 {tail}줄:\n```\n{logs}\n```"

    async def _list(self, client: docker.DockerClient) -> str:
        containers = await asyncio.to_thread(client.containers.list)
        if not containers:
            return "실행 중인 컨테이너가 없습니다."

        lines = ["실행 중인 컨테이너:"]
        for c in containers:
            image = c.image.tags[0] if c.image.tags else "(no tag)"
            lines.append(f"• {c.name} — {image} ({c.status})")
        return "\n".join(lines)
