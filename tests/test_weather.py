from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from koclaw.tools.weather import WeatherTool


@pytest.fixture
def tool():
    return WeatherTool()


# ── 기본 속성 ──────────────────────────────────────────────────────────────────

def test_tool_name(tool):
    assert tool.name == "weather"


def test_tool_is_not_sandboxed(tool):
    assert tool.is_sandboxed is False


# ── 정상 조회 ──────────────────────────────────────────────────────────────────

async def test_returns_weather_info(tool):
    geo_data = {
        "results": [
            {
                "name": "서울특별시",
                "latitude": 37.566,
                "longitude": 126.9784,
                "country": "대한민국",
                "admin1": "서울특별시",
            }
        ]
    }
    forecast_data = {
        "current": {
            "temperature_2m": 12.1,
            "weather_code": 0,
        },
        "daily": {
            "time": ["2026-03-17"],
            "temperature_2m_max": [15.0],
            "temperature_2m_min": [3.0],
            "weathercode": [0],
        },
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()

        def make_response(data):
            r = MagicMock()
            r.json.return_value = data
            r.raise_for_status = MagicMock()
            return r

        mock_client.get = AsyncMock(
            side_effect=[make_response(geo_data), make_response(forecast_data)]
        )
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute(city="Seoul")

    assert "서울특별시" in result
    assert "12.1" in result
    assert "15.0" in result
    assert "3.0" in result


async def test_returns_weather_description(tool):
    """날씨 코드가 한국어 설명으로 변환되는지 확인"""
    geo_data = {
        "results": [{"name": "Seoul", "latitude": 37.566, "longitude": 126.9784, "country": "KR", "admin1": "Seoul"}]
    }
    forecast_data = {
        "current": {"temperature_2m": 10.0, "weather_code": 61},
        "daily": {
            "time": ["2026-03-17"],
            "temperature_2m_max": [12.0],
            "temperature_2m_min": [5.0],
            "weathercode": [61],
        },
    }

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()

        def make_response(data):
            r = MagicMock()
            r.json.return_value = data
            r.raise_for_status = MagicMock()
            return r

        mock_client.get = AsyncMock(
            side_effect=[make_response(geo_data), make_response(forecast_data)]
        )
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute(city="Seoul")

    assert "비" in result


# ── 도시 없음 ──────────────────────────────────────────────────────────────────

async def test_returns_error_when_city_not_found(tool):
    geo_data = {}  # results 없음

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        r = MagicMock()
        r.json.return_value = geo_data
        r.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=r)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute(city="UnknownXYZ")

    assert "찾을 수 없" in result


# ── 네트워크 오류 ──────────────────────────────────────────────────────────────

async def test_returns_error_on_network_failure(tool):
    import httpx

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("연결 실패"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute(city="Seoul")

    assert "오류" in result
