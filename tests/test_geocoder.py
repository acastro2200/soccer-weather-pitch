from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import requests

from src.geocoder import DEFAULT_USER_AGENT, GeocodingError, NominatimGeocoder


class FakeResponse:
    def __init__(self, payload: list[dict[str, Any]], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")

    def json(self) -> list[dict[str, Any]]:
        return self.payload


class FakeSession:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        params: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return FakeResponse(
            [
                {
                    "lat": "38.7223",
                    "lon": "-9.1393",
                    "display_name": "Lisbon, Portugal",
                }
            ],
            status_code=self.status_code,
        )


def test_nominatim_geocoder_uses_user_agent_and_cache(tmp_path: Path) -> None:
    session = FakeSession()
    cache_path = tmp_path / "geocoded_locations.csv"
    geocoder = NominatimGeocoder(
        cache_path=cache_path,
        user_agent="soccer-weather-pitch-tests",
        session=session,
        sleep=lambda seconds: None,
    )

    first = geocoder.geocode("Lisbon", "Portugal")
    second = geocoder.geocode("Lisbon", "Portugal")

    assert first.latitude == 38.7223
    assert second.longitude == -9.1393
    assert len(session.calls) == 1
    assert session.calls[0]["headers"]["User-Agent"] == "soccer-weather-pitch-tests"
    assert session.calls[0]["headers"]["Accept"] == "application/json"
    assert cache_path.exists()


def test_nominatim_geocoder_defaults_generic_user_agent(tmp_path: Path) -> None:
    session = FakeSession()
    geocoder = NominatimGeocoder(
        cache_path=tmp_path / "geocoded_locations.csv",
        user_agent="python-requests",
        session=session,
        sleep=lambda seconds: None,
    )

    geocoder.geocode("Lisbon", "Portugal")

    assert session.calls[0]["headers"]["User-Agent"] == DEFAULT_USER_AGENT


def test_nominatim_geocoder_does_not_retry_failed_lookup(tmp_path: Path) -> None:
    session = FakeSession(status_code=403)
    sleeps: list[float] = []
    geocoder = NominatimGeocoder(
        cache_path=tmp_path / "geocoded_locations.csv",
        user_agent="soccer-weather-pitch-tests",
        session=session,
        sleep=sleeps.append,
    )

    with pytest.raises(GeocodingError):
        geocoder.geocode("Miami", "United States")
    with pytest.raises(GeocodingError):
        geocoder.geocode("Miami", "United States")

    assert len(session.calls) == 1
    assert sleeps == []


def test_nominatim_geocoder_waits_at_least_one_second_between_requests(tmp_path: Path) -> None:
    session = FakeSession()
    sleeps: list[float] = []
    geocoder = NominatimGeocoder(
        cache_path=tmp_path / "geocoded_locations.csv",
        user_agent="soccer-weather-pitch-tests",
        session=session,
        sleep=sleeps.append,
    )

    geocoder.geocode("Lisbon", "Portugal")
    geocoder.geocode("Porto", "Portugal")

    assert len(session.calls) == 2
    assert sleeps
    assert sleeps[0] >= 1.0
