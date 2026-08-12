from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Protocol

from agent.graph.state import QCState
from agent.services.audit_export import JsonAuditExporter


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
        self.records[state["thread_id"]] = dict(state)

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
    """Persistence adapter for final graph results; checkpoints remain separate."""

    def __init__(self, database: Any, audit_exporter: JsonAuditExporter | None = None) -> None:
        self.database = database
        self.audit_exporter = audit_exporter

    def save(self, state: QCState) -> None:
        # The workstation presents the latest disposition per vehicle.
        # Re-running the same case replaces its previous graph audit instead of
        # growing the dashboard indefinitely.
        with self.database.connection:
            self.database.connection.execute(
                "DELETE FROM agent_graph_runs WHERE vehicle_id = ? AND thread_id <> ?",
                (state["vehicle_id"], state["thread_id"]),
            )
            self.database.connection.execute(
                """INSERT INTO agent_graph_runs
            (thread_id, inspection_id, vehicle_id, status, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                inspection_id = excluded.inspection_id,
                vehicle_id = excluded.vehicle_id,
                status = excluded.status,
                state_json = excluded.state_json,
                updated_at = excluded.updated_at""",
                (
                    state["thread_id"],
                    state["inspection_id"],
                    state["vehicle_id"],
                    state.get("final_status", "UNKNOWN"),
                    json.dumps(state),
                    datetime.now(UTC).isoformat(),
                ),
            )
        if self.audit_exporter is not None:
            self.audit_exporter.export(dict(state))

    def get(self, thread_id: str) -> dict[str, Any] | None:
        row = self.database.connection.execute(
            "SELECT state_json FROM agent_graph_runs WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return json.loads(row["state_json"]) if row else None

    def list(self) -> list[dict[str, Any]]:
        rows = self.database.connection.execute(
            """SELECT current.state_json
            FROM agent_graph_runs AS current
            WHERE current.updated_at = (
                SELECT MAX(candidate.updated_at)
                FROM agent_graph_runs AS candidate
                WHERE candidate.vehicle_id = current.vehicle_id
            )
            ORDER BY current.updated_at DESC"""
        ).fetchall()
        return [json.loads(row["state_json"]) for row in rows]

    def list_with_metadata(self) -> list[dict[str, Any]]:
        """Return latest-per-vehicle states with persistence timestamps for trend analysis."""
        rows = self.database.connection.execute(
            """SELECT current.state_json, current.updated_at
            FROM agent_graph_runs AS current
            WHERE current.updated_at = (
                SELECT MAX(candidate.updated_at)
                FROM agent_graph_runs AS candidate
                WHERE candidate.vehicle_id = current.vehicle_id
            )
            ORDER BY current.updated_at DESC"""
        ).fetchall()
        return [
            {**json.loads(row["state_json"]), "_persisted_at": row["updated_at"]}
            for row in rows
        ]

    def clear(self) -> int:
        count = self.database.connection.execute("SELECT COUNT(*) FROM agent_graph_runs").fetchone()[0]
        self.database.execute("DELETE FROM agent_graph_runs")
        return count
