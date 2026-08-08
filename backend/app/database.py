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
                "This mock backend supports SQLite only. "
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
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS inspections (
                id TEXT PRIMARY KEY,
                vin TEXT NOT NULL,
                model TEXT NOT NULL,
                station TEXT NOT NULL,
                source_image_url TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS defects (
                id TEXT PRIMARY KEY,
                inspection_id TEXT NOT NULL,
                defect_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                camera_id TEXT NOT NULL,
                class_id INTEGER NOT NULL DEFAULT 0,
                bbox TEXT,
                image_width INTEGER NOT NULL DEFAULT 1920,
                image_height INTEGER NOT NULL DEFAULT 1080,
                model_name TEXT NOT NULL DEFAULT 'mock-yolo-qc',
                model_version TEXT NOT NULL DEFAULT 'mock-1.0',
                location TEXT,
                severity_rank TEXT,
                FOREIGN KEY (inspection_id) REFERENCES inspections(id)
            );
            CREATE TABLE IF NOT EXISTS classifications (
                id TEXT PRIMARY KEY,
                inspection_id TEXT NOT NULL,
                defect_id TEXT NOT NULL,
                panel TEXT NOT NULL,
                material TEXT NOT NULL,
                gdt_group INTEGER NOT NULL,
                tolerance_mm REAL NOT NULL,
                measurement_mm REAL NOT NULL,
                severity_rank TEXT NOT NULL,
                classification_confidence REAL NOT NULL,
                source TEXT NOT NULL,
                is_mock INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (inspection_id) REFERENCES inspections(id),
                FOREIGN KEY (defect_id) REFERENCES defects(id)
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                inspection_id TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                action_code TEXT NOT NULL DEFAULT 'LEGACY_ACTION',
                action TEXT NOT NULL,
                route TEXT NOT NULL,
                reason_codes TEXT NOT NULL,
                policy_refs TEXT NOT NULL DEFAULT '[]',
                method_steps TEXT NOT NULL DEFAULT '[]',
                explanation TEXT NOT NULL,
                test_drive_allowed INTEGER NOT NULL,
                is_mock INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY (inspection_id) REFERENCES inspections(id)
            );
            CREATE TABLE IF NOT EXISTS hitl_reviews (
                id TEXT PRIMARY KEY,
                inspection_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                action TEXT NOT NULL,
                original_recommendation TEXT NOT NULL,
                final_recommendation TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (inspection_id) REFERENCES inspections(id),
                FOREIGN KEY (decision_id) REFERENCES decisions(id)
            );
            CREATE TABLE IF NOT EXISTS workflow_runs (
                id TEXT PRIMARY KEY,
                inspection_id TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (inspection_id) REFERENCES inspections(id)
            );
            CREATE TABLE IF NOT EXISTS agent_graph_runs (
                thread_id TEXT PRIMARY KEY,
                inspection_id TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                status TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        inspection_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(inspections)")}
        if "source_image_url" not in inspection_columns:
            self.connection.execute("ALTER TABLE inspections ADD COLUMN source_image_url TEXT")

        # Keep the local mock database usable when the schema gains YOLO fields.
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(defects)")}
        additions = {
            "class_id": "INTEGER NOT NULL DEFAULT 0",
            "bbox": "TEXT",
            "image_width": "INTEGER NOT NULL DEFAULT 1920",
            "image_height": "INTEGER NOT NULL DEFAULT 1080",
            "model_name": "TEXT NOT NULL DEFAULT 'mock-yolo-qc'",
            "model_version": "TEXT NOT NULL DEFAULT 'mock-1.0'",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.connection.execute(f"ALTER TABLE defects ADD COLUMN {name} {definition}")
        decision_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(decisions)")}
        decision_additions = {
            "action_code": "TEXT NOT NULL DEFAULT 'LEGACY_ACTION'",
            "policy_refs": "TEXT NOT NULL DEFAULT '[]'",
            "method_steps": "TEXT NOT NULL DEFAULT '[]'",
        }
        for name, definition in decision_additions.items():
            if name not in decision_columns:
                self.connection.execute(f"ALTER TABLE decisions ADD COLUMN {name} {definition}")
        self.connection.commit()

    def execute(self, query: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        cursor = self.connection.execute(query, parameters)
        self.connection.commit()
        return cursor

    def close(self) -> None:
        self.connection.close()
