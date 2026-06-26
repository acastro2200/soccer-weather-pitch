# soccer-weather-pitch

Zero-paid Python pipeline for joining Portugal and Colombia international match results with historical weather and inferred pitch conditions.

## Main Pipeline

The main project uses:

- Public match data from `martj42/international_results` on GitHub
- OpenStreetMap Nominatim for `city + country` geocoding
- Open-Meteo Historical Weather API for weather

No paid APIs are required. No API keys are required.
Pitch condition is inferred from weather and is not an official provider condition.

Run the real pipeline with:

```bash
python -m src.pipeline \
  --teams Portugal Colombia \
  --start-date 2020-01-01 \
  --end-date 2026-06-25 \
  --output data/output/match_conditions.csv
```

The public match CSV does not include kickoff times, so the pipeline uses local `18:00` and writes `kickoff_time_estimated=True`.

Main outputs:

- `data/output/match_conditions.csv`
- `data/output/skipped_matches.csv`
- `data/output/geocoded_locations.csv`

`geocoded_locations.csv` caches geocoding results so repeated runs do not repeatedly call Nominatim.

## Output Columns

The main CSV includes match fields, coordinates, weather fields, and inferred pitch fields:

- `date`, `home_team`, `away_team`, `home_score`, `away_score`
- `tournament`, `city`, `country`, `neutral`
- `latitude`, `longitude`, `kickoff_time`, `kickoff_time_estimated`
- `temp_c`, `humidity`, `precipitation_mm`, `rain_mm`
- `wind_speed_kmh`, `wind_gusts_kmh`, `soil_moisture_0_to_7cm`
- `inferred_pitch_condition`, `pitch_condition_confidence`, `pitch_notes`

## Optional Demo

The fake-data MVP scripts are kept only as a small demo path:

```bash
python src/merge_data.py
```

That demo reads `data/matches.csv`, uses Meteostat, and writes `data/output/match_weather.csv`. It does not control the main project.

Install the optional demo dependencies before running it in a fresh environment:

```bash
python -m pip install -e ".[demo]"
```

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Optional environment settings:

```bash
USER_AGENT=soccer-weather-pitch/1.0 your_email@example.com
DEFAULT_KICKOFF_LOCAL=18:00
```

## Test

```bash
pytest
```

Tests use mocked clients/responses and do not call live APIs.
