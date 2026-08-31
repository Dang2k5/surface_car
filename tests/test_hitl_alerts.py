"""HitlRateAlertService must read the dedicated `assessment_route` column returned by
get_recent_outcomes_by_station directly, not parse a `state_json` blob (backend/app/
database.py's get_recent_outcomes_by_station no longer selects state_json at all)."""
from __future__ import annotations

from backend.app.hitl_alerts import HitlRateAlertService


class _FakeDatabase:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def get_recent_outcomes_by_station(self, station_id: str, limit: int = 100):
        return self._rows[:limit]


def _row(route: str) -> dict[str, str]:
    return {"assessment_route": route, "updated_at": "2026-01-01T00:00:00"}


def test_analyze_reads_assessment_route_column_not_state_json():
    rows = [_row("HITL")] * 8 + [_row("CONFIRMED")] * 12
    service = HitlRateAlertService(_FakeDatabase(rows))

    alert = service.analyze(station_id="ST-01")

    assert alert is not None
    assert alert.consecutive_count == 8
    assert alert.severity == "CRITICAL"
    assert alert.recommend_stop_line is True


def test_analyze_returns_none_when_no_recent_outcomes():
    service = HitlRateAlertService(_FakeDatabase([]))

    assert service.analyze(station_id="ST-01") is None


def test_analyze_ignores_rows_missing_assessment_route():
    """A row saved before this column existed (or a race with an in-flight save) must not
    be miscounted as HITL just because the field is absent."""
    rows = [{"updated_at": "2026-01-01T00:00:00"}] * 5
    service = HitlRateAlertService(_FakeDatabase(rows))

    assert service.analyze(station_id="ST-01") is None
