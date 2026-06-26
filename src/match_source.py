from __future__ import annotations

import hashlib
from datetime import date, datetime, time
from io import StringIO
from typing import Any, Protocol

import pandas as pd
import requests

from src.models import Match, Venue


RESULTS_CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SOURCE_COLUMNS = [
    "date",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "tournament",
    "city",
    "country",
    "neutral",
]
MATCH_ID_COLUMNS = [
    "date",
    "home_team",
    "away_team",
    "tournament",
    "city",
    "country",
]


class MatchSourceError(RuntimeError):
    pass


class MatchSource(Protocol):
    def get_matches(
        self,
        teams: list[str],
        start_date: date,
        end_date: date,
    ) -> list[Match]:
        pass


class GithubCsvMatchSource:
    def __init__(
        self,
        url: str = RESULTS_CSV_URL,
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
        default_kickoff_local: time = time(hour=18),
    ) -> None:
        self.url = url
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.default_kickoff_local = default_kickoff_local
        self.last_total_matches_loaded = 0
        self.last_matches_after_filtering = 0

    def get_matches(
        self,
        teams: list[str],
        start_date: date,
        end_date: date,
    ) -> list[Match]:
        csv_text = self._download_csv()
        self.last_total_matches_loaded = count_rows_in_csv_text(csv_text)
        matches = load_matches_from_csv_text(
            csv_text=csv_text,
            teams=teams,
            start_date=start_date,
            end_date=end_date,
            default_kickoff_local=self.default_kickoff_local,
        )
        self.last_matches_after_filtering = len(matches)
        return matches

    def _download_csv(self) -> str:
        try:
            response = self.session.get(self.url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise MatchSourceError(f"Could not download results.csv: {exc}") from exc
        return response.text


def load_matches_from_csv_text(
    csv_text: str,
    teams: list[str],
    start_date: date,
    end_date: date,
    default_kickoff_local: time = time(hour=18),
) -> list[Match]:
    try:
        dataframe = pd.read_csv(StringIO(csv_text), usecols=lambda column: column in SOURCE_COLUMNS)
    except ValueError as exc:
        raise MatchSourceError("results.csv is missing required columns.") from exc

    missing_columns = [column for column in SOURCE_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        raise MatchSourceError(f"results.csv is missing required columns: {missing_columns}")

    team_names = {team.casefold() for team in teams}
    matches: list[Match] = []
    for _, row in dataframe.iterrows():
        home_team = _clean_string(row.get("home_team"))
        away_team = _clean_string(row.get("away_team"))
        tracked_teams = [
            team
            for team in (home_team, away_team)
            if team is not None and team.casefold() in team_names
        ]
        if not tracked_teams:
            continue

        match_date = _parse_date(row.get("date"))
        if match_date is not None and not start_date <= match_date <= end_date:
            continue

        city = _clean_string(row.get("city"))
        country = _clean_string(row.get("country"))
        kickoff_at = (
            datetime.combine(match_date, default_kickoff_local)
            if match_date is not None
            else None
        )

        matches.append(
            Match(
                match_id=_build_match_id(row),
                match_date=match_date,
                home_team=home_team,
                away_team=away_team,
                home_score=_parse_int(row.get("home_score")),
                away_score=_parse_int(row.get("away_score")),
                tournament=_clean_string(row.get("tournament")),
                city=city,
                country=country,
                neutral=_parse_bool(row.get("neutral")),
                kickoff_at=kickoff_at,
                kickoff_time_estimated=True,
                venue=Venue(name=city, city=city, country=country),
                tracked_teams=tracked_teams,
            )
        )

    return matches


def count_rows_in_csv_text(csv_text: str) -> int:
    try:
        return len(pd.read_csv(StringIO(csv_text), usecols=["date"]))
    except ValueError as exc:
        raise MatchSourceError("results.csv is missing required columns.") from exc


def _build_match_id(row: pd.Series) -> str:
    return build_stable_match_id(
        match_date=row.get("date"),
        home_team=row.get("home_team"),
        away_team=row.get("away_team"),
        tournament=row.get("tournament"),
        city=row.get("city"),
        country=row.get("country"),
    )


def build_stable_match_id(
    match_date: Any,
    home_team: Any,
    away_team: Any,
    tournament: Any,
    city: Any,
    country: Any,
) -> str:
    parts = [
        _clean_string(match_date) or "",
        _clean_string(home_team) or "",
        _clean_string(away_team) or "",
        _clean_string(tournament) or "",
        _clean_string(city) or "",
        _clean_string(country) or "",
    ]
    raw_key = "|".join(parts)
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]


def _parse_date(value: Any) -> date | None:
    text = _clean_string(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    if _is_missing(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_bool(value: Any) -> bool | None:
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _clean_string(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def _is_missing(value: Any) -> bool:
    return value is None or bool(pd.isna(value))
