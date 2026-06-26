from __future__ import annotations

import argparse
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings
from src.geocoder import Geocoder, NominatimGeocoder
from src.match_source import GithubCsvMatchSource, MatchSource, build_stable_match_id
from src.models import Match, PipelineResult, WeatherSummary
from src.pitch_inference import infer_pitch_from_weather_summary
from src.weather_client import OpenMeteoClient, WeatherClient


LOGGER = logging.getLogger(__name__)

MATCH_COLUMNS = [
    "match_id",
    "date",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "tournament",
    "city",
    "country",
    "neutral",
    "latitude",
    "longitude",
    "kickoff_time",
    "kickoff_time_estimated",
    "temp_c",
    "humidity",
    "precipitation_mm",
    "rain_mm",
    "wind_speed_kmh",
    "wind_gusts_kmh",
    "soil_moisture_0_to_7cm",
    "inferred_pitch_condition",
    "pitch_condition_confidence",
    "pitch_notes",
]

SKIPPED_COLUMNS = [
    "match_id",
    "match_date",
    "home_team",
    "away_team",
    "tournament",
    "city",
    "country",
    "reason",
    "detail",
]


def run_pipeline(
    match_source: MatchSource,
    geocoder: Geocoder,
    weather_client: WeatherClient,
    teams: list[str],
    start_date: date,
    end_date: date,
    output_path: Path,
    skipped_path: Path | None = None,
) -> PipelineResult:
    skipped_path = skipped_path or output_path.with_name("skipped_matches.csv")

    existing_output = _read_csv(output_path, MATCH_COLUMNS)
    existing_output = _dedupe_match_rows(existing_output, MATCH_COLUMNS)
    existing_match_ids = _match_id_set(existing_output)

    new_rows: list[dict[str, Any]] = []
    new_skipped: list[dict[str, Any]] = []
    seen_match_ids: set[str] = set()

    LOGGER.info("Downloading public results CSV for %s", ", ".join(teams))
    try:
        matches = match_source.get_matches(teams, start_date, end_date)
    except Exception as exc:
        LOGGER.exception("Could not load match source")
        new_skipped.append(_skipped_row(None, "match_source_error", str(exc)))
        output_df = _combine_and_write_output(output_path, existing_output, new_rows)
        skipped_df = _combine_and_write_skipped(skipped_path, new_skipped, _match_id_set(output_df))
        LOGGER.info("Matches written=%s", len(new_rows))
        LOGGER.info("Matches skipped=%s", len(new_skipped))
        return _result(new_rows, new_skipped, output_df, skipped_df, output_path, skipped_path)

    LOGGER.info("Total matches loaded=%s", getattr(match_source, "last_total_matches_loaded", "unknown"))
    LOGGER.info("Matches after filtering=%s", getattr(match_source, "last_matches_after_filtering", len(matches)))

    for match in matches:
        if match.match_id in seen_match_ids:
            LOGGER.warning("Duplicate match %s encountered during this run.", match.match_id)
            new_skipped.append(
                _skipped_row(
                    match,
                    "duplicate_match",
                    "Match id was returned more than once in this run.",
                )
            )
            continue

        seen_match_ids.add(match.match_id)
        missing_reason = _missing_match_reason(match)
        if missing_reason is not None:
            new_skipped.append(_skipped_row(match, missing_reason, "Required source field is missing."))
            continue

        try:
            venue = geocoder.geocode(match.city or "", match.country or "")
            match = match.model_copy(update={"venue": venue})
        except Exception as exc:
            LOGGER.exception("Could not geocode match %s", match.match_id)
            new_skipped.append(_skipped_row(match, "missing_location", str(exc)))
            continue

        try:
            weather = weather_client.get_match_weather(match.venue, match.kickoff_at or datetime.min)
            pitch = infer_pitch_from_weather_summary(weather)
        except Exception as exc:
            LOGGER.exception("Could not fetch weather for match %s", match.match_id)
            new_skipped.append(_skipped_row(match, "weather_unavailable", str(exc)))
            continue

        new_rows.append(_match_condition_row(match, weather, pitch))

    output_df = _combine_and_write_output(output_path, existing_output, new_rows)
    skipped_df = _combine_and_write_skipped(skipped_path, new_skipped, _match_id_set(output_df))
    LOGGER.info("Matches written=%s", len(new_rows))
    LOGGER.info("Matches skipped=%s", len(new_skipped))
    return _result(new_rows, new_skipped, output_df, skipped_df, output_path, skipped_path)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build match weather and pitch condition CSVs.")
    parser.add_argument("--start-date", required=True, type=_parse_date)
    parser.add_argument("--end-date", required=True, type=_parse_date)
    parser.add_argument("--teams", nargs="+", default=["Portugal", "Colombia"])
    parser.add_argument("--output", type=Path, default=Path("data/output/match_conditions.csv"))
    parser.add_argument("--skipped-output", type=Path, default=None)
    parser.add_argument("--geocode-cache", type=Path, default=Path("data/output/geocoded_locations.csv"))
    parser.add_argument("--source-url", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_arg_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    match_source = GithubCsvMatchSource(
        url=args.source_url or settings.results_csv_url,
        timeout_seconds=settings.request_timeout_seconds,
        default_kickoff_local=settings.default_kickoff_local,
    )
    geocoder = NominatimGeocoder(
        cache_path=args.geocode_cache,
        base_url=settings.nominatim_base_url,
        user_agent=settings.user_agent,
        timeout_seconds=settings.request_timeout_seconds,
    )
    weather_client = OpenMeteoClient(
        base_url=settings.open_meteo_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )

    result = run_pipeline(
        match_source=match_source,
        geocoder=geocoder,
        weather_client=weather_client,
        teams=args.teams,
        start_date=args.start_date,
        end_date=args.end_date,
        output_path=args.output,
        skipped_path=args.skipped_output,
    )
    LOGGER.info(
        "Finished. Output rows=%s, skipped rows=%s",
        result.output_rows,
        result.skipped_rows,
    )
    return 0


def _result(
    new_rows: list[dict[str, Any]],
    new_skipped: list[dict[str, Any]],
    output_df: pd.DataFrame,
    skipped_df: pd.DataFrame,
    output_path: Path,
    skipped_path: Path,
) -> PipelineResult:
    return PipelineResult(
        processed_matches=len(new_rows),
        skipped_matches=len(new_skipped),
        output_rows=len(output_df),
        skipped_rows=len(skipped_df),
        output_path=output_path,
        skipped_path=skipped_path,
    )


def _combine_and_write_output(
    output_path: Path,
    existing_output: pd.DataFrame,
    new_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    new_df = pd.DataFrame(new_rows, columns=MATCH_COLUMNS)
    combined = pd.concat([existing_output, new_df], ignore_index=True)
    combined = _dedupe_match_rows(combined, MATCH_COLUMNS)
    if not combined.empty:
        combined = combined.sort_values(["date", "home_team", "away_team"], na_position="last")
    _write_csv(output_path, combined, MATCH_COLUMNS)
    return combined


def _combine_and_write_skipped(
    skipped_path: Path,
    new_skipped: list[dict[str, Any]],
    resolved_match_ids: set[str],
) -> pd.DataFrame:
    existing_skipped = _read_csv(skipped_path, SKIPPED_COLUMNS)
    new_df = pd.DataFrame(new_skipped, columns=SKIPPED_COLUMNS)
    combined = pd.concat([existing_skipped, new_df], ignore_index=True)
    combined = _remove_resolved_skips(combined, resolved_match_ids)
    combined = _dedupe_skipped_rows(combined)
    _write_csv(skipped_path, combined, SKIPPED_COLUMNS)
    return combined


def _match_condition_row(
    match: Match,
    weather: WeatherSummary,
    pitch: dict[str, str],
) -> dict[str, Any]:
    venue = match.venue
    return {
        "match_id": match.match_id,
        "date": match.match_date.isoformat() if match.match_date else None,
        "home_team": match.home_team,
        "away_team": match.away_team,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "tournament": match.tournament,
        "city": match.city,
        "country": match.country,
        "neutral": match.neutral,
        "latitude": venue.latitude,
        "longitude": venue.longitude,
        "kickoff_time": match.kickoff_at.strftime("%H:%M") if match.kickoff_at else None,
        "kickoff_time_estimated": match.kickoff_time_estimated,
        "temp_c": weather.temperature_avg_c,
        "humidity": weather.humidity_avg,
        "precipitation_mm": weather.precipitation_total_mm,
        "rain_mm": weather.rain_total_mm,
        "wind_speed_kmh": weather.wind_speed_avg_kmh,
        "wind_gusts_kmh": weather.wind_gust_max_kmh,
        "soil_moisture_0_to_7cm": weather.soil_moisture_avg,
        **pitch,
    }


def _skipped_row(match: Match | None, reason: str, detail: str) -> dict[str, Any]:
    return {
        "match_id": match.match_id if match else None,
        "match_date": match.match_date.isoformat() if match and match.match_date else None,
        "home_team": match.home_team if match else None,
        "away_team": match.away_team if match else None,
        "tournament": match.tournament if match else None,
        "city": match.city if match else None,
        "country": match.country if match else None,
        "reason": reason,
        "detail": detail,
    }


def _missing_match_reason(match: Match) -> str | None:
    if match.match_date is None or match.kickoff_at is None:
        return "missing_date"
    if not match.city:
        return "missing_city"
    if not match.country:
        return "missing_country"
    return None


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        dataframe = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)
    if "date" in columns:
        dataframe = dataframe.rename(
            columns={
                "match_date": "date",
                "soil_moisture": "soil_moisture_0_to_7cm",
            }
        )
    return dataframe.reindex(columns=columns)


def _write_csv(path: Path, dataframe: pd.DataFrame, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.reindex(columns=columns).to_csv(path, index=False)


def _dedupe_match_rows(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.reindex(columns=columns)
    deduped = dataframe.copy()
    deduped["match_id"] = deduped.apply(_canonical_match_id, axis=1)
    deduped["__match_key"] = deduped["match_id"].map(_match_key)
    deduped = deduped[deduped["__match_key"] != ""]
    deduped = deduped.drop_duplicates(subset=["__match_key"], keep="last")
    return deduped.drop(columns=["__match_key"]).reindex(columns=columns).reset_index(drop=True)


def _canonical_match_id(row: pd.Series) -> str:
    if all(_has_value(row.get(column)) for column in ("date", "home_team", "away_team", "tournament", "city", "country")):
        return build_stable_match_id(
            match_date=row.get("date"),
            home_team=row.get("home_team"),
            away_team=row.get("away_team"),
            tournament=row.get("tournament"),
            city=row.get("city"),
            country=row.get("country"),
        )
    return _match_key(row.get("match_id"))


def _dedupe_skipped_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.reindex(columns=SKIPPED_COLUMNS)
    deduped = dataframe.copy()
    deduped["__skip_key"] = (
        deduped["match_id"].map(_match_key)
        + "|"
        + deduped["home_team"].fillna("").astype(str)
        + "|"
        + deduped["away_team"].fillna("").astype(str)
        + "|"
        + deduped["reason"].fillna("").astype(str)
    )
    deduped = deduped.drop_duplicates(subset=["__skip_key"], keep="last")
    return deduped.drop(columns=["__skip_key"]).reindex(columns=SKIPPED_COLUMNS).reset_index(drop=True)


def _remove_resolved_skips(dataframe: pd.DataFrame, resolved_match_ids: set[str]) -> pd.DataFrame:
    if dataframe.empty or not resolved_match_ids:
        return dataframe.reindex(columns=SKIPPED_COLUMNS)
    filtered = dataframe.copy()
    filtered["__match_key"] = filtered["match_id"].map(_match_key)
    filtered = filtered[
        (filtered["__match_key"] == "")
        | (~filtered["__match_key"].isin(resolved_match_ids))
    ]
    return filtered.drop(columns=["__match_key"]).reindex(columns=SKIPPED_COLUMNS).reset_index(drop=True)


def _match_id_set(dataframe: pd.DataFrame) -> set[str]:
    if dataframe.empty:
        return set()
    return {key for key in dataframe["match_id"].map(_match_key) if key}


def _match_key(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _has_value(value: Any) -> bool:
    return not pd.isna(value) and str(value).strip() != ""


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date: {value}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
