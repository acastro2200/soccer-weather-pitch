from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

import pandas as pd
import requests

from src.models import Venue


LOGGER = logging.getLogger(__name__)

GEOCODE_COLUMNS = [
    "city",
    "country",
    "latitude",
    "longitude",
    "display_name",
    "geocoded_at",
]


class GeocodingError(RuntimeError):
    pass


class Geocoder(Protocol):
    def geocode(self, city: str, country: str) -> Venue:
        pass


class NominatimGeocoder:
    def __init__(
        self,
        cache_path: Path = Path("data/output/geocoded_locations.csv"),
        base_url: str = "https://nominatim.openstreetmap.org/search",
        user_agent: str = "soccer-weather-pitch/0.1",
        session: requests.Session | None = None,
        timeout_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cache_path = cache_path
        self.base_url = base_url
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.sleep = sleep
        self._last_request_at: float | None = None
        self._cache = self._load_cache()

    def geocode(self, city: str, country: str) -> Venue:
        city = city.strip()
        country = country.strip()
        if not city or not country:
            raise GeocodingError("City and country are required for geocoding.")

        cache_key = _location_key(city, country)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        self._respect_rate_limit()
        params = {
            "q": f"{city}, {country}",
            "format": "jsonv2",
            "limit": 1,
        }
        headers = {"User-Agent": self.user_agent}
        try:
            response = self.session.get(
                self.base_url,
                params=params,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise GeocodingError(f"Nominatim request failed: {exc}") from exc
        except ValueError as exc:
            raise GeocodingError("Nominatim returned invalid JSON.") from exc
        finally:
            self._last_request_at = time.monotonic()

        venue = _venue_from_nominatim_payload(payload, city, country)
        self._cache[cache_key] = venue
        self._write_cache()
        LOGGER.info("Geocoded %s, %s", city, country)
        return venue

    def _respect_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < 1.0:
            self.sleep(1.0 - elapsed)

    def _load_cache(self) -> dict[str, Venue]:
        if not self.cache_path.exists():
            return {}
        try:
            dataframe = pd.read_csv(self.cache_path)
        except pd.errors.EmptyDataError:
            return {}

        cache: dict[str, Venue] = {}
        for _, row in dataframe.reindex(columns=GEOCODE_COLUMNS).iterrows():
            city = _clean_string(row.get("city"))
            country = _clean_string(row.get("country"))
            latitude = _parse_float(row.get("latitude"))
            longitude = _parse_float(row.get("longitude"))
            if city is None or country is None or latitude is None or longitude is None:
                continue
            cache[_location_key(city, country)] = Venue(
                name=city,
                city=city,
                country=country,
                latitude=latitude,
                longitude=longitude,
            )
        return cache

    def _write_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "city": venue.city,
                "country": venue.country,
                "latitude": venue.latitude,
                "longitude": venue.longitude,
                "display_name": venue.name,
                "geocoded_at": datetime.now(timezone.utc).isoformat(),
            }
            for venue in sorted(
                self._cache.values(),
                key=lambda item: ((item.country or "").casefold(), (item.city or "").casefold()),
            )
        ]
        pd.DataFrame(rows, columns=GEOCODE_COLUMNS).to_csv(self.cache_path, index=False)


def _venue_from_nominatim_payload(payload: Any, city: str, country: str) -> Venue:
    if not isinstance(payload, list) or not payload:
        raise GeocodingError(f"No geocoding result for {city}, {country}.")

    first_result = payload[0]
    if not isinstance(first_result, dict):
        raise GeocodingError(f"Invalid geocoding result for {city}, {country}.")

    latitude = _parse_float(first_result.get("lat"))
    longitude = _parse_float(first_result.get("lon"))
    if latitude is None or longitude is None:
        raise GeocodingError(f"Geocoding result is missing coordinates for {city}, {country}.")

    return Venue(
        name=_clean_string(first_result.get("display_name")) or city,
        city=city,
        country=country,
        latitude=latitude,
        longitude=longitude,
    )


def _location_key(city: str, country: str) -> str:
    return f"{city.strip().casefold()}|{country.strip().casefold()}"


def _parse_float(value: Any) -> float | None:
    if value is None or bool(pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_string(value: Any) -> str | None:
    if value is None or bool(pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None
