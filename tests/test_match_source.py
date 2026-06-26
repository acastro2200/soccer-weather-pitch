from __future__ import annotations

from datetime import date

from src.match_source import build_stable_match_id, load_matches_from_csv_text


def test_csv_source_filters_portugal_and_colombia_matches() -> None:
    csv_text = """date,home_team,away_team,home_score,away_score,tournament,city,country,neutral
2020-01-01,Portugal,Spain,1,0,Friendly,Lisbon,Portugal,FALSE
2020-01-02,France,Germany,2,1,Friendly,Paris,France,FALSE
2020-01-03,Brazil,Colombia,0,1,Friendly,Rio de Janeiro,Brazil,TRUE
"""

    matches = load_matches_from_csv_text(
        csv_text,
        teams=["Portugal", "Colombia"],
        start_date=date(2020, 1, 1),
        end_date=date(2020, 1, 3),
    )

    assert [match.home_team for match in matches] == ["Portugal", "Brazil"]
    assert [match.away_team for match in matches] == ["Spain", "Colombia"]
    assert all(match.kickoff_time_estimated for match in matches)
    assert matches[0].kickoff_at.hour == 18


def test_match_id_ignores_score_and_neutral_fields() -> None:
    first = build_stable_match_id(
        match_date="2024-06-08",
        home_team="Portugal",
        away_team="Croatia",
        tournament="Friendly",
        city="Lisbon",
        country="Portugal",
    )
    second = build_stable_match_id(
        match_date="2024-06-08",
        home_team="Portugal",
        away_team="Croatia",
        tournament="Friendly",
        city="Lisbon",
        country="Portugal",
    )

    assert first == second
    assert len(first) == 16
