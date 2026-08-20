from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import text

from agent.graph.state import QCState
from agent.services.audit_export import JsonAuditExporter

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

    def list(self) -> list[dict[str, Any]]: ...

    def list_with_metadata(self) -> list[dict[str, Any]]: ...

    def clear(self) -> int: ...


class MockQCRepository:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def save(self, state: QCState) -> None:
        vehicle_id = state["vehicle_id"]
        self.records = {
            thread_id: record
            for thread_id, record in self.records.items()
            if record.get("vehicle_id") != vehicle_id or thread_id == state["thread_id"]
        }
        self.records[state["thread_id"]] = _sanitize_state(dict(state))

    def get(self, thread_id: str) -> dict[str, Any] | None:
        return self.records.get(thread_id)

    def list(self) -> list[dict[str, Any]]:
        return list(self.records.values())

    def list_with_metadata(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC).isoformat()
        return [{**record, "_persisted_at": now} for record in self.records.values()]

    def clear(self) -> int:
        count = len(self.records)
        self.records.clear()
        return count


class SQLiteQCRepository:
    """Provider-neutral SQL repository retained under its legacy class name."""

    def __init__(self, database: Any, audit_exporter: JsonAuditExporter | None = None) -> None:
        self.database = database
        self.audit_exporter = audit_exporter

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
                     station_id, production_date, defect_type, state_json, updated_at)
                    VALUES (:thread_id, :inspection_id, :vehicle_id, :status, :lot_id, :shift_id,
                            :station_id, :production_date, :defect_type, :state_json, :updated_at)
                    ON CONFLICT(thread_id) DO UPDATE SET
                        inspection_id = excluded.inspection_id,
                        vehicle_id = excluded.vehicle_id,
                        status = excluded.status,
                        lot_id = excluded.lot_id,
                        shift_id = excluded.shift_id,
                        station_id = excluded.station_id,
                        production_date = excluded.production_date,
                        defect_type = excluded.defect_type,
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
                    "state_json": json.dumps(state),
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
        if self.audit_exporter is not None:
            self.audit_exporter.export(dict(state))

    def get(self, thread_id: str) -> dict[str, Any] | None:
        row = self.database.fetch_one(
            "SELECT state_json FROM agent_graph_runs WHERE thread_id = :thread_id",
            {"thread_id": thread_id},
        )
        return _sanitize_state(json.loads(row["state_json"])) if row else None

    def list(self) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            """SELECT current.state_json
            FROM agent_graph_runs AS current
            WHERE current.updated_at = (
                SELECT MAX(candidate.updated_at)
                FROM agent_graph_runs AS candidate
                WHERE candidate.vehicle_id = current.vehicle_id
            )
            ORDER BY current.updated_at DESC"""
        )
        return [_sanitize_state(json.loads(row["state_json"])) for row in rows]

    def list_with_metadata(self) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            """SELECT current.state_json, current.updated_at
            FROM agent_graph_runs AS current
            WHERE current.updated_at = (
                SELECT MAX(candidate.updated_at)
                FROM agent_graph_runs AS candidate
                WHERE candidate.vehicle_id = current.vehicle_id
            )
            ORDER BY current.updated_at DESC"""
        )
        return [
            {**_sanitize_state(json.loads(row["state_json"])), "_persisted_at": row["updated_at"]}
            for row in rows
        ]

    def clear(self) -> int:
        row = self.database.fetch_one("SELECT COUNT(*) AS count FROM agent_graph_runs")
        self.database.execute("DELETE FROM agent_graph_runs")
        return int(row["count"]) if row else 0
