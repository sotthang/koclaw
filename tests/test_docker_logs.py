from unittest.mock import MagicMock, patch

import pytest

from koclaw.tools.docker_logs import DockerLogsTool


@pytest.fixture
def tool():
    return DockerLogsTool()


def test_schema(tool):
    assert tool.name == "docker_logs"
    assert "action" in tool.parameters["properties"]
    assert "container" in tool.parameters["properties"]
    assert "tail" in tool.parameters["properties"]
    assert tool.parameters["required"] == ["action"]


@pytest.mark.asyncio
async def test_logs_action(tool):
    mock_container = MagicMock()
    mock_container.logs.return_value = b"2024-01-01 INFO koclaw started\n2024-01-01 INFO ready\n"

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    with patch("docker.from_env", return_value=mock_client):
        result = await tool.execute(action="logs", container="koclaw", tail=50)

    assert "koclaw started" in result
    assert "ready" in result
    mock_client.containers.get.assert_called_once_with("koclaw")
    mock_container.logs.assert_called_once_with(tail=50, timestamps=True, since=None)


@pytest.mark.asyncio
async def test_logs_default_container(tool):
    mock_container = MagicMock()
    mock_container.logs.return_value = b"log line\n"

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_container

    with patch("docker.from_env", return_value=mock_client):
        result = await tool.execute(action="logs")

    mock_client.containers.get.assert_called_once_with("koclaw")
    assert "log line" in result


@pytest.mark.asyncio
async def test_list_action(tool):
    mock_c1 = MagicMock()
    mock_c1.name = "koclaw"
    mock_c1.status = "running"
    mock_c1.image.tags = ["koclaw:latest"]

    mock_c2 = MagicMock()
    mock_c2.name = "redis"
    mock_c2.status = "running"
    mock_c2.image.tags = ["redis:7"]

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [mock_c1, mock_c2]

    with patch("docker.from_env", return_value=mock_client):
        result = await tool.execute(action="list")

    assert "koclaw" in result
    assert "redis" in result
    assert "running" in result


@pytest.mark.asyncio
async def test_logs_container_not_found(tool):
    import docker

    mock_client = MagicMock()
    mock_client.containers.get.side_effect = docker.errors.NotFound("not found")

    with patch("docker.from_env", return_value=mock_client):
        result = await tool.execute(action="logs", container="nonexistent")

    assert "찾을 수 없습니다" in result


@pytest.mark.asyncio
async def test_docker_not_available(tool):
    with patch("docker.from_env", side_effect=Exception("socket not found")):
        result = await tool.execute(action="logs")

    assert "오류" in result


@pytest.mark.asyncio
async def test_unknown_action(tool):
    mock_client = MagicMock()
    with patch("docker.from_env", return_value=mock_client):
        result = await tool.execute(action="unknown")
    assert "알 수 없는" in result
