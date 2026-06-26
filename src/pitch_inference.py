from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

try:
    from src.models import PitchCondition, WeatherSummary
except ModuleNotFoundError as exc:
    if exc.name != "src":
        raise
    from models import PitchCondition, WeatherSummary


def infer_pitch_from_weather_columns(weather: Mapping[str, Any]) -> dict[str, str]:
    if _is_truthy(weather.get("weather_missing")):
        return {
            "inferred_pitch_condition": "unknown",
            "pitch_condition_confidence": "low",
            "pitch_notes": "Weather data was not available.",
        }

    precipitation = _to_float(weather.get("precipitation_mm"))
    wind_gusts = _to_float(weather.get("wind_gusts_kmh"))
    wind_speed = _to_float(weather.get("wind_speed_kmh"))
    notes: list[str] = []

    if precipitation is None:
        condition = "unknown"
        confidence = "low"
        notes.append("Precipitation data was not available.")
    rain = _to_float(weather.get("rain_mm"))

    if precipitation is None and rain is None:
        condition = "unknown"
        confidence = "low"
        notes.append("Precipitation and rain data were not available.")
    elif (precipitation is not None and precipitation >= 5) or (rain is not None and rain >= 5):
        condition = "wet/slippery"
        confidence = "high"
        notes.append("Precipitation or rain was at least 5 mm near kickoff.")
    elif (precipitation is not None and precipitation >= 1) or (rain is not None and rain >= 1):
        condition = "damp"
        confidence = "medium"
        notes.append("Precipitation or rain was between 1 and 5 mm near kickoff.")
    else:
        condition = "normal/dry"
        confidence = "medium"
        notes.append("Little or no precipitation near kickoff.")

    if (wind_gusts is not None and wind_gusts >= 35) or (wind_gusts is None and wind_speed is not None and wind_speed >= 35):
        notes.append("Wind may affect ball flight.")

    return {
        "inferred_pitch_condition": condition,
        "pitch_condition_confidence": confidence,
        "pitch_notes": " ".join(notes),
    }


def infer_pitch_from_weather_summary(weather: WeatherSummary) -> dict[str, str]:
    if weather.sample_count <= 0:
        return {
            "inferred_pitch_condition": "unknown",
            "pitch_condition_confidence": "low",
            "pitch_notes": "Weather data was not available.",
        }

    precipitation = weather.precipitation_total_mm
    rain = weather.rain_total_mm
    soil = weather.soil_moisture_avg
    humidity = weather.humidity_avg
    wind_speed = weather.wind_speed_avg_kmh
    wind_gust = weather.wind_gust_max_kmh
    notes: list[str] = []

    if precipitation >= 5 or rain >= 5:
        condition = "wet/slippery"
        confidence = "high"
        notes.append("Precipitation or rain was at least 5 mm near kickoff.")
    elif precipitation >= 1 or rain >= 1:
        condition = "damp"
        confidence = "medium"
        notes.append("Precipitation or rain was between 1 and 5 mm near kickoff.")
    elif soil is not None and soil >= 0.35:
        condition = "soft/heavy"
        confidence = "medium"
        notes.append("Soil moisture at 0-7 cm suggests a soft or heavy surface.")
    elif humidity is not None and humidity >= 90:
        condition = "damp"
        confidence = "medium"
        notes.append("High humidity may keep the surface slightly damp.")
    else:
        condition = "normal/dry"
        confidence = "medium"
        notes.append("Weather indicators suggest a normal or dry pitch.")

    if wind_gust is not None and wind_gust >= 35:
        notes.append("Wind may affect ball flight.")

    return {
        "inferred_pitch_condition": condition,
        "pitch_condition_confidence": confidence,
        "pitch_notes": " ".join(notes),
    }


def infer_pitch_condition(
    weather: WeatherSummary,
    surface: str | None = None,
    official_condition: str | None = None,
) -> PitchCondition:
    if official_condition and official_condition.strip():
        return PitchCondition(
            condition=official_condition.strip(),
            label="official",
            reason="Provider supplied an official pitch condition.",
        )

    surface_text = (surface or "").lower()
    is_artificial = any(term in surface_text for term in ("artificial", "synthetic", "turf"))
    precipitation = weather.precipitation_total_mm
    rain = weather.rain_total_mm
    soil = weather.soil_moisture_avg
    humidity = weather.humidity_avg
    wind_speed = weather.wind_speed_avg_kmh or 0.0
    wind_gust = weather.wind_gust_max_kmh or 0.0

    reasons: list[str] = []

    if precipitation >= 12.0 or rain >= 10.0 or (soil is not None and soil >= 0.42):
        condition = "waterlogged"
        reasons.append("heavy precipitation or high soil moisture")
    elif (
        precipitation >= 4.0
        or rain >= 3.0
        or (soil is not None and soil >= 0.34)
        or (humidity is not None and humidity >= 95.0 and soil is not None and soil >= 0.3)
    ):
        condition = "wet"
        reasons.append("meaningful rain, elevated soil moisture, or saturated air")
    elif (
        precipitation >= 1.0
        or rain >= 0.5
        or (soil is not None and soil >= 0.27)
        or (humidity is not None and humidity >= 90.0)
    ):
        condition = "slick"
        reasons.append("light rain, moisture, or high humidity")
    elif soil is not None and soil <= 0.14 and precipitation < 0.5:
        condition = "firm"
        reasons.append("low soil moisture and little precipitation")
    else:
        condition = "normal"
        reasons.append("weather indicators are within normal ranges")

    if is_artificial and condition in {"slick", "wet"}:
        condition = f"{condition} artificial surface"
        reasons.append("synthetic surfaces can play faster when damp")
    elif is_artificial and condition == "firm":
        condition = "firm artificial surface"
        reasons.append("surface is listed as artificial or synthetic")

    if wind_gust >= 55.0 or wind_speed >= 35.0:
        if condition == "normal":
            condition = "wind-affected"
        else:
            condition = f"{condition}, wind-affected"
        reasons.append("strong winds may affect play")

    return PitchCondition(
        condition=condition,
        label="inferred",
        reason="; ".join(reasons),
    )


def _to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_truthy(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
