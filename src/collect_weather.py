from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim
from meteostat import Parameter, Point, hourly, stations


USER_AGENT = "soccer-weather-pitch-mvp"
_GEOCODER = Nominatim(user_agent=USER_AGENT)
_GEOCODE = RateLimiter(_GEOCODER.geocode, min_delay_seconds=1)


def geocode_location(city: str, country: str) -> tuple[float, float] | None:
    try:
        location = _GEOCODE(f"{city}, {country}", exactly_one=True)
    except Exception:
        return None
    if location is None:
        return None
    return float(location.latitude), float(location.longitude)


def get_hourly_weather(latitude: float, longitude: float, kickoff_at: datetime) -> dict[str, Any] | None:
    start = kickoff_at - timedelta(hours=1)
    end = kickoff_at + timedelta(hours=1)
    point = Point(latitude, longitude)
    try:
        weather = hourly(point, start, end, parameters=_WEATHER_PARAMETERS).fetch()
    except Exception:
        weather = None
    if weather is None or weather.empty:
        weather = _nearby_station_weather(point, start, end)
    if weather is None or weather.empty:
        return None

    closest_index = min(weather.index, key=lambda value: abs(value.to_pydatetime() - kickoff_at))
    row = weather.loc[closest_index]
    return {
        "temp_c": _clean_number(row.get("temp")),
        "precipitation_mm": _clean_number(row.get("prcp")),
        "wind_speed_kmh": _clean_number(row.get("wspd")),
        "humidity": _clean_number(row.get("rhum")),
    }


def collect_weather(city: str, country: str, kickoff_at: datetime) -> dict[str, Any]:
    coordinates = geocode_location(city, country)
    if coordinates is None:
        return _missing_weather()

    weather = get_hourly_weather(coordinates[0], coordinates[1], kickoff_at)
    if weather is None:
        return _missing_weather(latitude=coordinates[0], longitude=coordinates[1])

    return {
        "latitude": coordinates[0],
        "longitude": coordinates[1],
        **weather,
        "weather_missing": False,
    }


_WEATHER_PARAMETERS = [Parameter.TEMP, Parameter.PRCP, Parameter.WSPD, Parameter.RHUM]


def _nearby_station_weather(point: Point, start: datetime, end: datetime) -> pd.DataFrame | None:
    try:
        nearby_stations = stations.nearby(point, radius=100000, limit=10)
    except Exception:
        return None

    for station_id in nearby_stations.index:
        try:
            weather = hourly(station_id, start, end, parameters=_WEATHER_PARAMETERS).fetch()
        except Exception:
            continue
        if weather is not None and not weather.empty:
            return weather
    return None


def _missing_weather(latitude: float | None = None, longitude: float | None = None) -> dict[str, Any]:
    return {
        "latitude": latitude,
        "longitude": longitude,
        "temp_c": None,
        "precipitation_mm": None,
        "wind_speed_kmh": None,
        "humidity": None,
        "weather_missing": True,
    }


def _clean_number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
