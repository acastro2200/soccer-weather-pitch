from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from src.models import Match, Venue, WeatherSummary
from src.pipeline import run_pipeline
from src.match_source import build_stable_match_id


class FakeMatchSource:
    def __init__(self, matches: list[Match]) -> None:
        self.matches = matches

    def get_matches(
        self,
        teams: list[str],
        start_date: date,
        end_date: date,
    ) -> list[Match]:
        return self.matches


class FailingMatchSource:
    def get_matches(
        self,
        teams: list[str],
        start_date: date,
        end_date: date,
    ) -> list[Match]:
        raise RuntimeError("source unavailable")


class FakeGeocoder:
    def geocode(self, city: str, country: str) -> Venue:
        return Venue(
            name=city,
            city=city,
            country=country,
            latitude=38.752,
            longitude=-9.184,
        )


class FakeWeatherClient:
    def get_match_weather(self, venue: Venue, kickoff_at: datetime) -> WeatherSummary:
        return WeatherSummary(
            latitude=venue.latitude or 0.0,
            longitude=venue.longitude or 0.0,
            start_at=kickoff_at,
            end_at=kickoff_at,
            temperature_avg_c=21.0,
            precipitation_total_mm=0.0,
            rain_total_mm=0.0,
            soil_moisture_avg=0.2,
            humidity_avg=65.0,
            wind_speed_avg_kmh=8.0,
            wind_gust_max_kmh=14.0,
            sample_count=3,
        )


def _match(match_id: str, match_date: date, city: str | None = "Lisbon") -> Match:
    kickoff_at = datetime.combine(match_date, datetime.min.time()).replace(hour=18)
    return Match(
        match_id=match_id,
        match_date=match_date,
        home_team="Portugal",
        away_team="Colombia",
        home_score=1,
        away_score=0,
        tournament="Friendly",
        city=city,
        country="Portugal",
        neutral=False,
        kickoff_at=kickoff_at,
        kickoff_time_estimated=True,
        tracked_teams=["Portugal", "Colombia"],
    )


def test_pipeline_output_is_idempotent_by_match_id(tmp_path: Path) -> None:
    output_path = tmp_path / "match_conditions.csv"
    skipped_path = tmp_path / "skipped_matches.csv"
    existing_match_id = build_stable_match_id(
        match_date="2020-01-01",
        home_team="Portugal",
        away_team="Colombia",
        tournament="Friendly",
        city="Lisbon",
        country="Portugal",
    )
    new_match_id = build_stable_match_id(
        match_date="2020-01-02",
        home_team="Portugal",
        away_team="Colombia",
        tournament="Friendly",
        city="Lisbon",
        country="Portugal",
    )
    pd.DataFrame(
        [
            {
                "match_id": "legacy-id",
                "date": "2020-01-01",
                "home_team": "Portugal",
                "away_team": "Colombia",
                "tournament": "Friendly",
                "city": "Lisbon",
                "country": "Portugal",
                "inferred_pitch_condition": "normal/dry",
            }
        ]
    ).to_csv(output_path, index=False)

    result = run_pipeline(
        match_source=FakeMatchSource(
            [
                _match("existing", date(2020, 1, 1)),
                _match("new", date(2020, 1, 2)),
            ]
        ),
        geocoder=FakeGeocoder(),
        weather_client=FakeWeatherClient(),
        teams=["Portugal", "Colombia"],
        start_date=date(2020, 1, 1),
        end_date=date(2020, 1, 3),
        output_path=output_path,
        skipped_path=skipped_path,
    )

    output = pd.read_csv(output_path)
    assert result.output_rows == 2
    assert output["match_id"].tolist() == [existing_match_id, new_match_id]
    assert output["match_id"].is_unique
    assert output.loc[output["match_id"] == new_match_id, "date"].item() == "2020-01-02"
    assert output.loc[output["match_id"] == new_match_id, "temp_c"].item() == 21.0
    assert output.loc[output["match_id"] == new_match_id, "soil_moisture_0_to_7cm"].item() == 0.2
    assert output.loc[output["match_id"] == new_match_id, "inferred_pitch_condition"].item() == "normal/dry"
    assert output.loc[output["match_id"] == new_match_id, "pitch_condition_confidence"].item() == "medium"
    assert output.loc[output["match_id"] == new_match_id, "kickoff_time_estimated"].item()
    assert output.loc[output["match_id"] == new_match_id, "kickoff_time"].item() == "18:00"

    skipped = pd.read_csv(skipped_path)
    assert skipped.empty


def test_pipeline_writes_rows_missing_city_to_skipped_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "match_conditions.csv"
    skipped_path = tmp_path / "skipped_matches.csv"

    run_pipeline(
        match_source=FakeMatchSource([_match("missing-city", date(2020, 1, 2), city=None)]),
        geocoder=FakeGeocoder(),
        weather_client=FakeWeatherClient(),
        teams=["Portugal", "Colombia"],
        start_date=date(2020, 1, 1),
        end_date=date(2020, 1, 3),
        output_path=output_path,
        skipped_path=skipped_path,
    )

    skipped = pd.read_csv(skipped_path)
    assert skipped["match_id"].tolist() == ["missing-city"]
    assert skipped["reason"].tolist() == ["missing_city"]


def test_pipeline_writes_match_source_errors_to_skipped_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "match_conditions.csv"
    skipped_path = tmp_path / "skipped_matches.csv"

    result = run_pipeline(
        match_source=FailingMatchSource(),
        geocoder=FakeGeocoder(),
        weather_client=FakeWeatherClient(),
        teams=["Portugal", "Colombia"],
        start_date=date(2020, 1, 1),
        end_date=date(2020, 1, 3),
        output_path=output_path,
        skipped_path=skipped_path,
    )

    skipped = pd.read_csv(skipped_path)
    assert result.skipped_rows == 1
    assert skipped["reason"].tolist() == ["match_source_error"]


def test_pipeline_writes_weather_errors_to_skipped_csv(tmp_path: Path) -> None:
    class FailingWeatherClient:
        def get_match_weather(self, venue: Venue, kickoff_at: datetime) -> WeatherSummary:
            raise RuntimeError("weather unavailable")

    output_path = tmp_path / "match_conditions.csv"
    skipped_path = tmp_path / "skipped_matches.csv"

    run_pipeline(
        match_source=FakeMatchSource([_match("weather-fail", date(2020, 1, 2))]),
        geocoder=FakeGeocoder(),
        weather_client=FailingWeatherClient(),
        teams=["Portugal", "Colombia"],
        start_date=date(2020, 1, 1),
        end_date=date(2020, 1, 3),
        output_path=output_path,
        skipped_path=skipped_path,
    )

    skipped = pd.read_csv(skipped_path)
    assert skipped["match_id"].tolist() == ["weather-fail"]
    assert skipped["reason"].tolist() == ["weather_unavailable"]
