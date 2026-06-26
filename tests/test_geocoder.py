from __future__ import annotations

from pathlib import Path
from typing import Any

from src.geocoder import NominatimGeocoder


class FakeResponse:
    def __init__(self, payload: list[dict[str, Any]]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict[str, Any]]:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
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
            ]
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
    assert cache_path.exists()
