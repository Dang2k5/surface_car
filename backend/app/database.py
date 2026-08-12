from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DATABASE_URL = "sqlite:///./data/visual_qc.db"


def _database_path(database_url: str) -> str:
    if database_url == ":memory:":
        return database_url
    if database_url.startswith("sqlite:///"):
        path = database_url.removeprefix("sqlite:///")
    else:
        if "://" in database_url:
            raise ValueError(
                "This baseline backend supports SQLite only. "
                "Use a sqlite:/// URL until the PostgreSQL checkpoint is implemented."
            )
        path = database_url
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return str(database_path)


class SQLiteDatabase:
    def __init__(self, database_url: str = DEFAULT_DATABASE_URL) -> None:
        self.database_path = _database_path(database_url)
        self.connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.initialize()

    def initialize(self) -> None:
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS agent_graph_runs (
                thread_id TEXT PRIMARY KEY,
                inspection_id TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                status TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_graph_runs_vehicle_updated "
            "ON agent_graph_runs(vehicle_id, updated_at DESC)"
        )
        self.connection.commit()

    def execute(self, query: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        cursor = self.connection.execute(query, parameters)
        self.connection.commit()
        return cursor

    def close(self) -> None:
        self.connection.close()
