from __future__ import annotations

import os
from pathlib import Path
from datetime import time

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator

from src.match_source import RESULTS_CSV_URL


class Settings(BaseModel):
    results_csv_url: str = RESULTS_CSV_URL
    open_meteo_base_url: str = "https://archive-api.open-meteo.com/v1/archive"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org/search"
    user_agent: str = Field(default="soccer-weather-pitch/1.0 your_email@example.com", min_length=1)
    default_kickoff_local: time = time(hour=18)
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    default_output_path: Path = Path("data/output/match_conditions.csv")
    default_skipped_path: Path = Path("data/output/skipped_matches.csv")
    default_geocode_cache_path: Path = Path("data/output/geocoded_locations.csv")

    @field_validator("user_agent")
    @classmethod
    def strip_user_agent(cls, value: str) -> str:
        user_agent = value.strip()
        if not user_agent:
            raise ValueError("USER_AGENT must not be empty")
        return user_agent

    @field_validator("default_kickoff_local", mode="before")
    @classmethod
    def parse_default_kickoff(cls, value: str | time) -> time:
        if isinstance(value, time):
            return value
        hour_minute = value.strip().split(":")
        if len(hour_minute) != 2:
            raise ValueError("DEFAULT_KICKOFF_LOCAL must use HH:MM format")
        return time(hour=int(hour_minute[0]), minute=int(hour_minute[1]))

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        try:
            return cls(
                results_csv_url=os.getenv("RESULTS_CSV_URL", RESULTS_CSV_URL),
                open_meteo_base_url=os.getenv(
                    "OPEN_METEO_BASE_URL",
                    "https://archive-api.open-meteo.com/v1/archive",
                ),
                nominatim_base_url=os.getenv(
                    "NOMINATIM_BASE_URL",
                    "https://nominatim.openstreetmap.org/search",
                ),
                user_agent=os.getenv("USER_AGENT", "soccer-weather-pitch/1.0 your_email@example.com"),
                default_kickoff_local=os.getenv("DEFAULT_KICKOFF_LOCAL", "18:00"),
                request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
            )
        except (ValidationError, ValueError) as exc:
            raise RuntimeError(
                "Invalid configuration. Check RESULTS_CSV_URL, OPEN_METEO_BASE_URL, "
                "NOMINATIM_BASE_URL, USER_AGENT, DEFAULT_KICKOFF_LOCAL, and "
                "REQUEST_TIMEOUT_SECONDS."
            ) from exc
