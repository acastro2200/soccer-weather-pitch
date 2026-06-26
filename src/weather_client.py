from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Protocol

import requests

from src.models import Venue, WeatherSummary


HOURLY_VARIABLES = (
    "temperature_2m",
    "precipitation",
    "rain",
    "apparent_temperature",
    "weather_code",
    "soil_temperature_0_to_7cm",
    "soil_moisture_0_to_7cm",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_gusts_10m",
)


class WeatherDataUnavailable(RuntimeError):
    pass


class WeatherClient(Protocol):
    def get_match_weather(self, venue: Venue, kickoff_at: datetime) -> WeatherSummary:
        pass


class OpenMeteoClient:
    def __init__(
        self,
        base_url: str = "https://archive-api.open-meteo.com/v1/archive",
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds

    def get_match_weather(self, venue: Venue, kickoff_at: datetime) -> WeatherSummary:
        if venue.latitude is None or venue.longitude is None:
            raise WeatherDataUnavailable("Venue is missing latitude or longitude.")

        start_at, end_at = match_weather_window(kickoff_at)
        params = {
            "latitude": venue.latitude,
            "longitude": venue.longitude,
            "start_date": start_at.date().isoformat(),
            "end_date": end_at.date().isoformat(),
            "hourly": ",".join(HOURLY_VARIABLES),
            "timezone": "auto",
            "timeformat": "iso8601",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        }

        try:
            response = self.session.get(
                self.base_url,
                params=params,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise WeatherDataUnavailable(f"Open-Meteo request failed: {exc}") from exc
        except ValueError as exc:
            raise WeatherDataUnavailable("Open-Meteo returned invalid JSON.") from exc

        return aggregate_open_meteo_payload(
            payload=payload,
            latitude=float(venue.latitude),
            longitude=float(venue.longitude),
            kickoff_at=kickoff_at,
        )


def match_weather_window(kickoff_at: datetime) -> tuple[datetime, datetime]:
    kickoff = kickoff_at.replace(microsecond=0)
    return kickoff, kickoff + timedelta(hours=2)


def aggregate_open_meteo_payload(
    payload: dict[str, Any],
    latitude: float,
    longitude: float,
    kickoff_at: datetime,
) -> WeatherSummary:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise WeatherDataUnavailable("Open-Meteo response is missing hourly weather data.")

    raw_times = hourly.get("time")
    if not isinstance(raw_times, list):
        raise WeatherDataUnavailable("Open-Meteo response is missing hourly timestamps.")

    start_at, end_at = match_weather_window(kickoff_at)
    selected_indices: list[int] = []
    for index, raw_time in enumerate(raw_times):
        sample_at = _align_time_for_comparison(_parse_open_meteo_time(raw_time), start_at)
        if start_at <= sample_at <= end_at:
            selected_indices.append(index)

    if not selected_indices:
        raise WeatherDataUnavailable("Open-Meteo returned no samples for the match window.")

    temperature_values = _numeric_values(hourly, "temperature_2m", selected_indices)
    apparent_temperature_values = _numeric_values(hourly, "apparent_temperature", selected_indices)
    precipitation_values = _numeric_values(hourly, "precipitation", selected_indices)
    rain_values = _numeric_values(hourly, "rain", selected_indices)
    weather_code_values = _numeric_values(hourly, "weather_code", selected_indices)
    soil_temperature_values = _numeric_values(hourly, "soil_temperature_0_to_7cm", selected_indices)
    soil_values = _numeric_values(hourly, "soil_moisture_0_to_7cm", selected_indices)
    humidity_values = _numeric_values(hourly, "relative_humidity_2m", selected_indices)
    wind_values = _numeric_values(hourly, "wind_speed_10m", selected_indices)
    gust_values = _numeric_values(hourly, "wind_gusts_10m", selected_indices)

    return WeatherSummary(
        latitude=latitude,
        longitude=longitude,
        start_at=start_at,
        end_at=end_at,
        temperature_avg_c=_rounded_mean(temperature_values),
        apparent_temperature_avg_c=_rounded_mean(apparent_temperature_values),
        precipitation_total_mm=round(sum(precipitation_values), 3),
        rain_total_mm=round(sum(rain_values), 3),
        weather_code=_most_common_int(weather_code_values),
        soil_temperature_avg_c=_rounded_mean(soil_temperature_values),
        soil_moisture_avg=_rounded_mean(soil_values),
        humidity_avg=_rounded_mean(humidity_values),
        wind_speed_avg_kmh=_rounded_mean(wind_values),
        wind_gust_max_kmh=round(max(gust_values), 3) if gust_values else None,
        sample_count=len(selected_indices),
    )


def _parse_open_meteo_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise WeatherDataUnavailable(f"Invalid Open-Meteo timestamp: {value!r}")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _align_time_for_comparison(value: datetime, reference: datetime) -> datetime:
    if value.tzinfo is None and reference.tzinfo is not None:
        return value.replace(tzinfo=reference.tzinfo)
    if value.tzinfo is not None and reference.tzinfo is None:
        return value.replace(tzinfo=None)
    return value


def _numeric_values(hourly: dict[str, Any], variable: str, indices: list[int]) -> list[float]:
    values = hourly.get(variable)
    if not isinstance(values, list):
        return []

    numeric: list[float] = []
    for index in indices:
        if index >= len(values):
            continue
        value = values[index]
        if isinstance(value, (int, float)):
            numeric.append(float(value))
    return numeric


def _rounded_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(mean(values), 3)


def _most_common_int(values: list[float]) -> int | None:
    if not values:
        return None
    rounded = [int(value) for value in values]
    return max(set(rounded), key=rounded.count)
