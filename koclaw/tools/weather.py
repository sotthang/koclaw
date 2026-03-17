import logging

import httpx

from koclaw.core.tool import Tool

logger = logging.getLogger(__name__)

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

_WMO_CODES: dict[int, str] = {
    0: "맑음",
    1: "대체로 맑음",
    2: "부분 흐림",
    3: "흐림",
    45: "안개",
    48: "안개",
    51: "이슬비",
    53: "이슬비",
    55: "이슬비",
    61: "비",
    63: "비",
    65: "강한 비",
    71: "눈",
    73: "눈",
    75: "강한 눈",
    77: "진눈깨비",
    80: "소나기",
    81: "소나기",
    82: "강한 소나기",
    85: "눈 소나기",
    86: "강한 눈 소나기",
    95: "뇌우",
    96: "우박 동반 뇌우",
    99: "강한 우박 동반 뇌우",
}


def _wmo_description(code: int) -> str:
    return _WMO_CODES.get(code, f"날씨 코드 {code}")


class WeatherTool(Tool):
    name = "weather"
    description = "도시의 현재 날씨와 오늘 최저·최고 기온을 조회합니다"
    parameters = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name in English (e.g. Seoul, Busan, Tokyo, New York)",
            },
        },
        "required": ["city"],
    }
    is_sandboxed = False

    async def execute(self, city: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # 1. 도시 좌표 조회
                geo_resp = await client.get(
                    _GEOCODING_URL,
                    params={"name": city, "language": "ko", "count": 1},
                )
                geo_resp.raise_for_status()
                geo = geo_resp.json()

                if not geo.get("results"):
                    return f"'{city}' 도시를 찾을 수 없습니다. 영어 도시명으로 다시 입력해주세요."

                loc = geo["results"][0]
                lat = loc["latitude"]
                lon = loc["longitude"]
                city_name = loc.get("name", city)
                country = loc.get("country", "")

                # 2. 날씨 조회
                forecast_resp = await client.get(
                    _FORECAST_URL,
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,weather_code",
                        "daily": "temperature_2m_max,temperature_2m_min,weathercode",
                        "timezone": "Asia/Seoul",
                    },
                )
                forecast_resp.raise_for_status()
                data = forecast_resp.json()

            current = data["current"]
            daily = data["daily"]

            temp_now = current["temperature_2m"]
            weather_code = current["weather_code"]
            temp_max = daily["temperature_2m_max"][0]
            temp_min = daily["temperature_2m_min"][0]
            description = _wmo_description(weather_code)

            location_label = f"{city_name}" + (f", {country}" if country else "")
            return (
                f"📍 {location_label}\n"
                f"🌡️ 현재 {temp_now}°C  {description}\n"
                f"📈 최고 {temp_max}°C  📉 최저 {temp_min}°C"
            )

        except httpx.HTTPError as e:
            logger.error("[weather] HTTP 오류: %s", e)
            return "날씨 정보를 가져오는 중 오류가 발생했습니다."
        except Exception as e:
            logger.error("[weather] 오류: %s", e)
            return f"날씨 조회 중 오류가 발생했습니다: {type(e).__name__}"
