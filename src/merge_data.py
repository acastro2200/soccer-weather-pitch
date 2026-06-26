from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from src.collect_weather import collect_weather
    from src.pitch_inference import infer_pitch_from_weather_columns
except ModuleNotFoundError as exc:
    if exc.name != "src":
        raise
    from collect_weather import collect_weather
    from pitch_inference import infer_pitch_from_weather_columns


INPUT_PATH = Path("data/matches.csv")
OUTPUT_PATH = Path("data/output/match_weather.csv")


def build_match_weather(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> pd.DataFrame:
    matches = pd.read_csv(input_path)
    rows: list[dict[str, Any]] = []

    for _, match in matches.iterrows():
        row = match.to_dict()
        weather = _weather_for_match(row)
        pitch = infer_pitch_from_weather_columns(weather)
        rows.append({**row, **weather, **pitch})

    output = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False)
    return output


def _weather_for_match(match: dict[str, Any]) -> dict[str, Any]:
    city = _clean_text(match.get("city"))
    country = _clean_text(match.get("country"))
    kickoff_at = _parse_kickoff(match.get("date"), match.get("kickoff_time"))

    if city is None or country is None or kickoff_at is None:
        return {
            "latitude": None,
            "longitude": None,
            "temp_c": None,
            "precipitation_mm": None,
            "wind_speed_kmh": None,
            "humidity": None,
            "weather_missing": True,
        }

    return collect_weather(city, country, kickoff_at)


def _parse_kickoff(date_value: Any, kickoff_time_value: Any) -> datetime | None:
    date_text = _clean_text(date_value)
    kickoff_text = _clean_text(kickoff_time_value) or "18:00"
    if date_text is None:
        return None

    try:
        return datetime.fromisoformat(f"{date_text} {kickoff_text}")
    except ValueError:
        return None


def _clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def main() -> int:
    build_match_weather()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
