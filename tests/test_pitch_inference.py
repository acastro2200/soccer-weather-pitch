from __future__ import annotations

from datetime import datetime, timezone

from src.models import WeatherSummary
from src.pitch_inference import infer_pitch_condition, infer_pitch_from_weather_summary


def _weather(**overrides: float | int | None) -> WeatherSummary:
    values = {
        "latitude": 38.752,
        "longitude": -9.184,
        "start_at": datetime(2024, 1, 1, 20, tzinfo=timezone.utc),
        "end_at": datetime(2024, 1, 1, 22, tzinfo=timezone.utc),
        "precipitation_total_mm": 0.0,
        "rain_total_mm": 0.0,
        "soil_moisture_avg": 0.2,
        "humidity_avg": 65.0,
        "wind_speed_avg_kmh": 8.0,
        "wind_gust_max_kmh": 15.0,
        "sample_count": 3,
    }
    values.update(overrides)
    return WeatherSummary(**values)


def test_official_condition_is_preserved() -> None:
    condition = infer_pitch_condition(_weather(), official_condition="Good")

    assert condition.condition == "Good"
    assert condition.label == "official"


def test_heavy_precipitation_is_inferred_as_waterlogged() -> None:
    condition = infer_pitch_condition(
        _weather(precipitation_total_mm=14.5, rain_total_mm=11.0),
        surface="natural grass",
    )

    assert condition.label == "inferred"
    assert "waterlogged" in condition.condition


def test_dry_low_soil_moisture_is_inferred_as_firm() -> None:
    condition = infer_pitch_condition(
        _weather(precipitation_total_mm=0.0, rain_total_mm=0.0, soil_moisture_avg=0.1)
    )

    assert condition.label == "inferred"
    assert condition.condition == "firm"


def test_strong_wind_affects_condition() -> None:
    condition = infer_pitch_condition(_weather(wind_speed_avg_kmh=38.0, wind_gust_max_kmh=60.0))

    assert "wind-affected" in condition.condition


def test_high_humidity_can_make_surface_slick() -> None:
    condition = infer_pitch_condition(_weather(humidity_avg=92.0))

    assert condition.condition == "slick"
    assert "humidity" in condition.reason


def test_summary_pitch_inference_returns_main_pipeline_columns() -> None:
    pitch = infer_pitch_from_weather_summary(
        _weather(precipitation_total_mm=6.0, rain_total_mm=4.0, wind_gust_max_kmh=36.0)
    )

    assert pitch["inferred_pitch_condition"] == "wet/slippery"
    assert pitch["pitch_condition_confidence"] == "high"
    assert "Wind may affect ball flight" in pitch["pitch_notes"]


def test_summary_pitch_inference_soft_heavy_from_soil_moisture() -> None:
    pitch = infer_pitch_from_weather_summary(
        _weather(precipitation_total_mm=0.0, rain_total_mm=0.0, soil_moisture_avg=0.36)
    )

    assert pitch["inferred_pitch_condition"] == "soft/heavy"
    assert pitch["pitch_condition_confidence"] == "medium"


def test_summary_pitch_inference_missing_weather_is_unknown() -> None:
    pitch = infer_pitch_from_weather_summary(_weather(sample_count=0))

    assert pitch["inferred_pitch_condition"] == "unknown"
    assert pitch["pitch_condition_confidence"] == "low"
