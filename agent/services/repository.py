from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import text

from agent.graph.state import QCState

REMOVED_CONTEXT_FIELDS = {"vin_code", "panel", "material"}


def _sanitize_state(value: Any) -> Any:
    """Hide removed legacy context fields when old audit rows are read."""
    if isinstance(value, dict):
        return {
            key: _sanitize_state(item)
            for key, item in value.items()
            if key not in REMOVED_CONTEXT_FIELDS
        }
    if isinstance(value, list):
        return [_sanitize_state(item) for item in value]
    return value


class QCRepository(Protocol):
    def save(self, state: QCState) -> None: ...

    def get(self, thread_id: str) -> dict[str, Any] | None: ...

    def list(self, *, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]: ...

    def list_with_metadata(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]: ...

    def clear(self) -> int: ...


class PostgresQCRepository:
    """Persists QC graph runs to the shared Supabase PostgreSQL database."""

    def __init__(self, database: Any) -> None:
        self.database = database

    def save(self, state: QCState) -> None:
        with self.database.begin() as connection:
            connection.execute(
                text("DELETE FROM agent_graph_runs WHERE vehicle_id = :vehicle_id AND thread_id <> :thread_id"),
                {"vehicle_id": state["vehicle_id"], "thread_id": state["thread_id"]},
            )
            connection.execute(
                text(
                    """INSERT INTO agent_graph_runs
                    (thread_id, inspection_id, vehicle_id, status, lot_id, shift_id,
                     station_id, production_date, defect_type, assessment_route,
                     state_json, updated_at)
                    VALUES (:thread_id, :inspection_id, :vehicle_id, :status, :lot_id, :shift_id,
                            :station_id, :production_date, :defect_type, :assessment_route,
                            :state_json, :updated_at)
                    ON CONFLICT(thread_id) DO UPDATE SET
                        inspection_id = excluded.inspection_id,
                        vehicle_id = excluded.vehicle_id,
                        status = excluded.status,
                        lot_id = excluded.lot_id,
                        shift_id = excluded.shift_id,
                        station_id = excluded.station_id,
                        production_date = excluded.production_date,
                        defect_type = excluded.defect_type,
                        assessment_route = excluded.assessment_route,
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at"""
                ),
                {
                    "thread_id": state["thread_id"],
                    "inspection_id": state["inspection_id"],
                    "vehicle_id": state["vehicle_id"],
                    "status": state.get("final_status", "UNKNOWN"),
                    "lot_id": state.get("lot_id"),
                    "shift_id": state.get("shift_id"),
                    "station_id": state.get("station_id"),
                    "production_date": state.get("production_date"),
                    "defect_type": state.get("defect_type"),
                    # Dedicated column so HitlRateAlertService can read this one field
                    # without loading/parsing the full state_json blob on every submission
                    # (backend/app/database.py's get_recent_outcomes_by_station).
                    "assessment_route": state.get("assessment_route"),
                    "state_json": json.dumps(state),
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )

    def get(self, thread_id: str) -> dict[str, Any] | None:
        row = self.database.fetch_one(
            "SELECT state_json FROM agent_graph_runs WHERE thread_id = :thread_id",
            {"thread_id": thread_id},
        )
        return _sanitize_state(json.loads(row["state_json"])) if row else None

    def list(self, *, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        query = """SELECT current.state_json
            FROM agent_graph_runs AS current
            WHERE current.updated_at = (
                SELECT MAX(candidate.updated_at)
                FROM agent_graph_runs AS candidate
                WHERE candidate.vehicle_id = current.vehicle_id
            )
            ORDER BY current.updated_at DESC"""
        params: dict[str, Any] = {}
        if limit is not None:
            query += " LIMIT :limit OFFSET :offset"
            params = {"limit": limit, "offset": offset}
        rows = self.database.fetch_all(query, params)
        return [_sanitize_state(json.loads(row["state_json"])) for row in rows]

    def list_with_metadata(
        self, *, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        query = """SELECT current.state_json, current.updated_at
            FROM agent_graph_runs AS current
            WHERE current.updated_at = (
                SELECT MAX(candidate.updated_at)
                FROM agent_graph_runs AS candidate
                WHERE candidate.vehicle_id = current.vehicle_id
            )
            ORDER BY current.updated_at DESC"""
        params: dict[str, Any] = {}
        if limit is not None:
            query += " LIMIT :limit OFFSET :offset"
            params = {"limit": limit, "offset": offset}
        rows = self.database.fetch_all(query, params)
        return [
            {**_sanitize_state(json.loads(row["state_json"])), "_persisted_at": row["updated_at"]}
            for row in rows
        ]

    def clear(self) -> int:
        row = self.database.fetch_one("SELECT COUNT(*) AS count FROM agent_graph_runs")
        self.database.execute("DELETE FROM agent_graph_runs")
        return int(row["count"]) if row else 0
