from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from src.models import Venue
from src.weather_client import OpenMeteoClient, WeatherDataUnavailable


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: float) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self.payload)


def test_open_meteo_client_aggregates_match_window() -> None:
    payload = {
        "hourly": {
            "time": [
                "2024-03-01T17:00",
                "2024-03-01T18:00",
                "2024-03-01T19:00",
                "2024-03-01T20:00",
                "2024-03-01T21:00",
            ],
            "temperature_2m": [1.0, 10.0, 11.0, 12.0, 13.0],
            "apparent_temperature": [1.0, 8.0, 9.0, 10.0, 11.0],
            "precipitation": [99.0, 0.0, 1.5, 2.0, 0.5],
            "rain": [99.0, 0.0, 1.0, 1.5, 0.25],
            "weather_code": [0, 1, 2, 2, 3],
            "soil_temperature_0_to_7cm": [20.0, 21.0, 22.0, 23.0, 24.0],
            "soil_moisture_0_to_7cm": [0.1, 0.2, 0.25, 0.3, 0.35],
            "relative_humidity_2m": [40.0, 60.0, 80.0, 90.0, 99.0],
            "wind_speed_10m": [1.0, 10.0, 12.0, 14.0, 16.0],
            "wind_gusts_10m": [2.0, 20.0, 24.0, 28.0, 30.0],
        }
    }
    session = FakeSession(payload)
    client = OpenMeteoClient(session=session, timeout_seconds=9.0)
    venue = Venue(latitude=38.752, longitude=-9.184)

    summary = client.get_match_weather(
        venue,
        datetime(2024, 3, 1, 18, 30, tzinfo=timezone.utc),
    )

    assert summary.temperature_avg_c == 11.5
    assert summary.apparent_temperature_avg_c == 9.5
    assert summary.precipitation_total_mm == 3.5
    assert summary.rain_total_mm == 2.5
    assert summary.weather_code == 2
    assert summary.soil_temperature_avg_c == 22.5
    assert summary.soil_moisture_avg == 0.275
    assert summary.humidity_avg == 85.0
    assert summary.wind_speed_avg_kmh == 13.0
    assert summary.wind_gust_max_kmh == 28.0
    assert summary.sample_count == 2

    call = session.calls[0]
    assert call["params"]["latitude"] == 38.752
    assert call["params"]["longitude"] == -9.184
    assert call["params"]["start_date"] == "2024-03-01"
    assert call["params"]["end_date"] == "2024-03-01"
    assert call["params"]["timezone"] == "auto"
    assert "temperature_2m" in call["params"]["hourly"]
    assert "apparent_temperature" in call["params"]["hourly"]
    assert "weather_code" in call["params"]["hourly"]
    assert "soil_temperature_0_to_7cm" in call["params"]["hourly"]
    assert "soil_moisture_0_to_7cm" in call["params"]["hourly"]
    assert "relative_humidity_2m" in call["params"]["hourly"]
    assert call["timeout"] == 9.0


def test_open_meteo_client_rejects_missing_hourly_data() -> None:
    client = OpenMeteoClient(session=FakeSession({}))

    with pytest.raises(WeatherDataUnavailable):
        client.get_match_weather(
            Venue(latitude=4.711, longitude=-74.072),
            datetime(2024, 1, 1, 20, tzinfo=timezone.utc),
        )


def test_open_meteo_client_requires_coordinates() -> None:
    client = OpenMeteoClient(session=FakeSession({}))

    with pytest.raises(WeatherDataUnavailable):
        client.get_match_weather(Venue(), datetime(2024, 1, 1, 20, tzinfo=timezone.utc))
