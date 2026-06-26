from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Venue(BaseModel):
    name: str | None = None
    city: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    surface: str | None = None


class Match(BaseModel):
    match_id: str
    match_date: date | None
    home_team: str | None = None
    away_team: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    tournament: str | None = None
    city: str | None = None
    country: str | None = None
    neutral: bool | None = None
    kickoff_at: datetime | None = None
    kickoff_time_estimated: bool = True
    venue: Venue = Field(default_factory=Venue)
    tracked_teams: list[str] = Field(default_factory=list)
    provider: str = "martj42/international_results"

    @property
    def name(self) -> str:
        if self.home_team and self.away_team:
            return f"{self.home_team} vs {self.away_team}"
        return self.match_id


class WeatherSummary(BaseModel):
    latitude: float
    longitude: float
    start_at: datetime
    end_at: datetime
    temperature_avg_c: float | None = None
    apparent_temperature_avg_c: float | None = None
    precipitation_total_mm: float = 0.0
    rain_total_mm: float = 0.0
    weather_code: int | None = None
    soil_temperature_avg_c: float | None = None
    soil_moisture_avg: float | None = None
    humidity_avg: float | None = None
    wind_speed_avg_kmh: float | None = None
    wind_gust_max_kmh: float | None = None
    sample_count: int = 0

    @field_validator("start_at", "end_at")
    @classmethod
    def remove_microseconds(cls, value: datetime) -> datetime:
        return value.replace(microsecond=0)


class PitchCondition(BaseModel):
    condition: str
    label: Literal["inferred", "official"]
    reason: str


class PipelineResult(BaseModel):
    processed_matches: int
    skipped_matches: int
    output_rows: int
    skipped_rows: int
    output_path: Path
    skipped_path: Path
