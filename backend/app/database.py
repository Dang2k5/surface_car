from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote
from uuid import uuid4

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import Connection

DEFAULT_DATABASE_URL = "sqlite:///./data/visual_qc.db"


def normalize_database_url(database_url: str) -> str:
    """Normalize cloud URLs while preserving the local SQLite default."""
    value = database_url.strip()
    if value == ":memory:":
        return "sqlite+pysqlite:///:memory:"
    if value.startswith("sqlite:///"):
        path = Path(value.removeprefix("sqlite:///"))
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+pysqlite:///{path.as_posix()}"
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
    if value.startswith("postgresql+psycopg://"):
        return _encode_connection_password(value)
    return value


def _encode_connection_password(url: str) -> str:
    """Safely encode reserved characters in a raw DATABASE_URL password.

    Supabase connection strings contain one separator `@`, while passwords may
    also contain `@`, `:`, `/`, `#` or `?`. Splitting at the final `@` preserves
    the real pooler host and prevents psycopg from treating password fragments
    as part of the hostname. Existing percent escapes are preserved.
    """
    scheme, remainder = url.split("://", 1)
    if "@" not in remainder:
        return url
    user_info, server = remainder.rsplit("@", 1)
    if ":" not in user_info:
        return url
    username, password = user_info.split(":", 1)
    # Decode valid existing escapes first, then encode the complete raw value.
    # This preserves `%40` while correctly converting a literal `%` to `%25`.
    encoded_password = quote(unquote(password), safe="")
    return f"{scheme}://{username}:{encoded_password}@{server}"


class Database:
    """Small SQLAlchemy Core adapter shared by SQLite and Supabase PostgreSQL."""

    def __init__(self, database_url: str = DEFAULT_DATABASE_URL) -> None:
        self.database_url = normalize_database_url(database_url)
        connect_args: dict[str, Any] = {}
        if self.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine: Engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.initialize()

    @property
    def dialect(self) -> str:
        return self.engine.dialect.name

    @contextmanager
    def begin(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def initialize(self) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS agent_graph_runs (
                thread_id TEXT PRIMARY KEY,
                inspection_id TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                status TEXT NOT NULL,
                lot_id TEXT,
                shift_id TEXT,
                station_id TEXT,
                production_date TEXT,
                defect_type TEXT,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS defect_catalog (
                defect_code TEXT PRIMARY KEY,
                defect_type TEXT NOT NULL,
                cv_label TEXT NOT NULL,
                defect_family TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                classification_rule TEXT NOT NULL DEFAULT '',
                default_severity TEXT NOT NULL DEFAULT 'UNASSESSED',
                measurement_required INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS qc_decisions (
                decision_id TEXT PRIMARY KEY,
                thread_id TEXT,
                inspection_id TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                defect_code TEXT NOT NULL,
                defect_type TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                length_mm REAL,
                severity TEXT NOT NULL,
                action TEXT NOT NULL,
                disposition TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                reason TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(defect_code) REFERENCES defect_catalog(defect_code)
            )""",
            """CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY,
                email TEXT,
                role TEXT NOT NULL DEFAULT 'QC_OPERATOR',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS shifts (
                shift_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                start_time TEXT NOT NULL DEFAULT '',
                end_time TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS production_lots (
                lot_id TEXT PRIMARY KEY,
                note TEXT NOT NULL DEFAULT '',
                station_id TEXT,
                shift_id TEXT,
                vehicle_type TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS lot_products (
                product_code TEXT PRIMARY KEY,
                lot_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                vehicle_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS stations (
                station_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_lot_products_lot ON lot_products(lot_id, seq)",
        "CREATE INDEX IF NOT EXISTS idx_agent_graph_runs_vehicle_updated ON agent_graph_runs(vehicle_id, updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_qc_decisions_vehicle_created ON qc_decisions(vehicle_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_qc_decisions_inspection ON qc_decisions(inspection_id)",
        )
        with self.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
        self._ensure_columns()
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_defect_catalog_cv_label ON defect_catalog(cv_label, active)"
        )
        self.execute(
            """CREATE INDEX IF NOT EXISTS idx_agent_graph_runs_trend
            ON agent_graph_runs(station_id, shift_id, lot_id, production_date)"""
        )
        self._seed_defect_catalog()
        self._seed_shifts()
        self._seed_stations()

    def _ensure_columns(self) -> None:
        """Apply additive baseline migrations to databases created by older MVPs."""
        existing = {column["name"] for column in inspect(self.engine).get_columns("defect_catalog")}
        defect_columns = {
            "cv_label": "TEXT NOT NULL DEFAULT 'unknown'",
            "measurement_required": "INTEGER NOT NULL DEFAULT 0",
            "defect_family": "TEXT NOT NULL DEFAULT ''",
            "classification_rule": "TEXT NOT NULL DEFAULT ''",
        }
        decision_existing = {
            column["name"] for column in inspect(self.engine).get_columns("qc_decisions")
        }
        decision_columns = {
            "location": "TEXT NOT NULL DEFAULT ''",
            "length_mm": "REAL",
        }
        run_existing = {
            column["name"] for column in inspect(self.engine).get_columns("agent_graph_runs")
        }
        run_columns = {
            "lot_id": "TEXT",
            "shift_id": "TEXT",
            "station_id": "TEXT",
            "production_date": "TEXT",
            "defect_type": "TEXT",
        }
        lot_existing = {
            column["name"] for column in inspect(self.engine).get_columns("production_lots")
        }
        lot_columns = {
            "station_id": "TEXT",
            "shift_id": "TEXT",
            "vehicle_type": "TEXT NOT NULL DEFAULT ''",
            "quantity": "INTEGER NOT NULL DEFAULT 0",
        }
        station_existing = {
            column["name"] for column in inspect(self.engine).get_columns("stations")
        }
        with self.begin() as connection:
            for name, ddl in defect_columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE defect_catalog ADD COLUMN {name} {ddl}"))
            for name, ddl in decision_columns.items():
                if name not in decision_existing:
                    connection.execute(text(f"ALTER TABLE qc_decisions ADD COLUMN {name} {ddl}"))
            for obsolete in ("panel", "material"):
                if obsolete in decision_existing:
                    connection.execute(text(f"ALTER TABLE qc_decisions DROP COLUMN {obsolete}"))
            for name, ddl in run_columns.items():
                if name not in run_existing:
                    connection.execute(text(f"ALTER TABLE agent_graph_runs ADD COLUMN {name} {ddl}"))
            for name, ddl in lot_columns.items():
                if name not in lot_existing:
                    connection.execute(text(f"ALTER TABLE production_lots ADD COLUMN {name} {ddl}"))
            if "zone_name" in station_existing:
                connection.execute(text("ALTER TABLE stations DROP COLUMN zone_name"))

    def _seed_defect_catalog(self) -> None:
        now = datetime.now(UTC).isoformat()
        defaults = (
            ("SCRATCH01", "scratch", "scratch", "SURFACE_SCRATCH", "Vết xước nhỏ", "Vết xước đơn, chiều dài ước lượng đến 50 mm", "Chọn khi estimated_width_mm <= 50 và chỉ có một vùng xước", "C", 1),
            ("SCRATCH02", "scratch", "scratch", "SURFACE_SCRATCH", "Vết xước trung bình", "Vết xước đơn dài trên 50 đến 150 mm", "Chọn khi 50 < estimated_width_mm <= 150", "C", 1),
            ("SCRATCH03", "scratch", "scratch", "SURFACE_SCRATCH", "Vết xước dài", "Vết xước dài trên 150 mm", "Chọn khi estimated_width_mm > 150", "B", 1),
            ("SCRATCH04", "scratch", "scratch", "SURFACE_SCRATCH_CLUSTER", "Cụm nhiều vết xước", "Nhiều vùng xước cùng xuất hiện trên một ảnh", "Chọn khi có từ 2 detection scratch trở lên", "B", 1),
            ("SCRATCH05", "scratch", "scratch", "SURFACE_SCRATCH_EDGE", "Vết xước vùng mép", "Vết xước nằm gần mép vùng quan sát hoặc đường ráp", "Chọn khi relative_position nằm sát trái/phải", "B", 1),
            ("DENT01", "dent", "dent", "PANEL_DENT", "Vết móp nhỏ", "Vết móp đơn, bề rộng ước lượng đến 50 mm", "Chọn khi estimated_width_mm <= 50 và chỉ có một vùng móp", "C", 1),
            ("DENT02", "dent", "dent", "PANEL_DENT", "Vết móp trung bình", "Vết móp rộng trên 50 đến 150 mm", "Chọn khi 50 < estimated_width_mm <= 150", "B", 1),
            ("DENT03", "dent", "dent", "PANEL_DENT", "Vết móp lớn", "Vết móp rộng trên 150 mm", "Chọn khi estimated_width_mm > 150", "A", 1),
            ("DENT04", "dent", "dent", "PANEL_DENT_CREASE", "Móp có nếp gấp", "Vùng móp kéo dài hoặc có tỷ lệ dài/rộng lớn, cần QC xác nhận nếp gấp", "Chọn khi bbox aspect ratio >= 2; luôn yêu cầu QC xác nhận", "A", 1),
            ("DENT05", "dent", "dent", "PANEL_DENT_CLUSTER", "Cụm nhiều vết móp", "Nhiều vùng móp cùng xuất hiện trên một ảnh", "Chọn khi có từ 2 detection dent trở lên", "A", 1),
        )
        statement = text(
            """INSERT INTO defect_catalog
            (defect_code, defect_type, cv_label, defect_family, display_name, description,
             classification_rule, default_severity, measurement_required, active, created_at, updated_at)
            VALUES (:defect_code, :defect_type, :cv_label, :defect_family, :display_name, :description,
                    :classification_rule,
                    :default_severity, :measurement_required, 1, :created_at, :updated_at)
            ON CONFLICT(defect_code) DO UPDATE SET
                defect_type = excluded.defect_type,
                cv_label = excluded.cv_label,
                defect_family = excluded.defect_family,
                display_name = excluded.display_name,
                description = excluded.description,
                classification_rule = excluded.classification_rule,
                default_severity = excluded.default_severity,
                measurement_required = excluded.measurement_required,
                updated_at = excluded.updated_at"""
        )
        with self.begin() as connection:
            connection.execute(
                text(
                    """UPDATE defect_catalog SET active = 0, updated_at = :updated_at
                    WHERE defect_code IN ('PAINT01', 'CRACK01', 'GLASS01', 'LAMP01', 'TIRE01')"""
                ),
                {"updated_at": now},
            )
            connection.execute(
                statement,
                [
                    {
                        "defect_code": item[0],
                        "defect_type": item[1],
                        "cv_label": item[2],
                        "defect_family": item[3],
                        "display_name": item[4],
                        "description": item[5],
                        "classification_rule": item[6],
                        "default_severity": item[7],
                        "measurement_required": item[8],
                        "created_at": now,
                        "updated_at": now,
                    }
                    for item in defaults
                ],
            )

    def _seed_shifts(self) -> None:
        """Seed the 3 standard shifts so the inspection form's dropdown isn't empty on a fresh
        database. ON CONFLICT DO NOTHING preserves any edits a Supervisor already made."""
        now = datetime.now(UTC).isoformat()
        defaults = (("CA1", "Ca 1", "06:00", "14:00"), ("CA2", "Ca 2", "14:00", "22:00"), ("CA3", "Ca 3", "22:00", "06:00"))
        statement = text(
            """INSERT INTO shifts (shift_id, name, start_time, end_time, active, created_at, updated_at)
            VALUES (:shift_id, :name, :start_time, :end_time, 1, :created_at, :updated_at)
            ON CONFLICT(shift_id) DO NOTHING"""
        )
        with self.begin() as connection:
            connection.execute(
                statement,
                [
                    {
                        "shift_id": shift_id,
                        "name": name,
                        "start_time": start_time,
                        "end_time": end_time,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for shift_id, name, start_time, end_time in defaults
                ],
            )

    def list_shifts(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM shifts"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY shift_id"
        return self.fetch_all(query)

    def create_shift(self, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        self.execute(
            """INSERT INTO shifts (shift_id, name, start_time, end_time, active, created_at, updated_at)
            VALUES (:shift_id, :name, :start_time, :end_time, :active, :created_at, :updated_at)""",
            {
                **record,
                "active": 1 if record.get("active", True) else 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        return self.fetch_one("SELECT * FROM shifts WHERE shift_id = :shift_id", {"shift_id": record["shift_id"]}) or {}

    def update_shift(self, shift_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.fetch_one("SELECT * FROM shifts WHERE shift_id = :shift_id", {"shift_id": shift_id})
        if not existing:
            return None
        fields = {key: value for key, value in patch.items() if value is not None}
        if "active" in patch:
            fields["active"] = 1 if patch["active"] else 0
        if fields:
            fields["updated_at"] = datetime.now(UTC).isoformat()
            assignments = ", ".join(f"{key} = :{key}" for key in fields)
            self.execute(
                f"UPDATE shifts SET {assignments} WHERE shift_id = :shift_id",
                {**fields, "shift_id": shift_id},
            )
        return self.fetch_one("SELECT * FROM shifts WHERE shift_id = :shift_id", {"shift_id": shift_id})

    def list_lots(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM production_lots"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY created_at DESC"
        return self.fetch_all(query)

    def get_lot(self, lot_id: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM production_lots WHERE lot_id = :lot_id", {"lot_id": lot_id})

    def get_station(self, station_id: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM stations WHERE station_id = :station_id", {"station_id": station_id})

    def get_shift(self, shift_id: str) -> dict[str, Any] | None:
        return self.fetch_one("SELECT * FROM shifts WHERE shift_id = :shift_id", {"shift_id": shift_id})

    def create_lot(self, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        self.execute(
            """INSERT INTO production_lots
            (lot_id, note, station_id, shift_id, vehicle_type, quantity, active, created_at, updated_at)
            VALUES (:lot_id, :note, :station_id, :shift_id, :vehicle_type, :quantity, :active,
                    :created_at, :updated_at)""",
            {
                **record,
                "active": 1 if record.get("active", True) else 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        quantity = int(record.get("quantity") or 0)
        if quantity > 0:
            self._generate_lot_products(record["lot_id"], record["vehicle_type"], 1, quantity)
        return self.fetch_one("SELECT * FROM production_lots WHERE lot_id = :lot_id", {"lot_id": record["lot_id"]}) or {}

    def update_lot(self, lot_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.fetch_one("SELECT * FROM production_lots WHERE lot_id = :lot_id", {"lot_id": lot_id})
        if not existing:
            return None
        fields = {key: value for key, value in patch.items() if value is not None}
        if "active" in patch:
            fields["active"] = 1 if patch["active"] else 0
        if fields:
            fields["updated_at"] = datetime.now(UTC).isoformat()
            assignments = ", ".join(f"{key} = :{key}" for key in fields)
            self.execute(
                f"UPDATE production_lots SET {assignments} WHERE lot_id = :lot_id",
                {**fields, "lot_id": lot_id},
            )
        if "quantity" in fields:
            new_quantity = int(fields["quantity"])
            old_quantity = int(existing.get("quantity") or 0)
            if new_quantity > old_quantity:
                vehicle_type = existing.get("vehicle_type") or ""
                self._generate_lot_products(lot_id, vehicle_type, old_quantity + 1, new_quantity)
        return self.fetch_one("SELECT * FROM production_lots WHERE lot_id = :lot_id", {"lot_id": lot_id})

    def _generate_lot_products(self, lot_id: str, vehicle_type: str, start_seq: int, end_seq: int) -> None:
        """Auto-generate per-vehicle product codes for a lot: <vehicle_type>-<stt>, stt from
        start_seq to end_seq inclusive (stt counts 1..quantity, matching the physical vehicles
        produced in this lot). Example: vehicle_type "VF8", quantity 3 -> VF8-1, VF8-2, VF8-3."""
        now = datetime.now(UTC).isoformat()
        statement = text(
            """INSERT INTO lot_products (product_code, lot_id, seq, vehicle_type, created_at)
            VALUES (:product_code, :lot_id, :seq, :vehicle_type, :created_at)
            ON CONFLICT(product_code) DO NOTHING"""
        )
        with self.begin() as connection:
            connection.execute(
                statement,
                [
                    {
                        "product_code": f"{vehicle_type}-{seq}",
                        "lot_id": lot_id,
                        "seq": seq,
                        "vehicle_type": vehicle_type,
                        "created_at": now,
                    }
                    for seq in range(start_seq, end_seq + 1)
                ],
            )

    def list_lot_products(self, lot_id: str) -> list[dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM lot_products WHERE lot_id = :lot_id ORDER BY seq", {"lot_id": lot_id}
        )

    def _seed_stations(self) -> None:
        """Seed the stations already referenced by default form values elsewhere in the app
        (inspection.tsx's "QC-03", langgraph_api.py's "FNS_LINE_HA_01") so the dropdown isn't
        empty on a fresh database. ON CONFLICT DO NOTHING preserves Supervisor edits."""
        now = datetime.now(UTC).isoformat()
        defaults = (("FNS_LINE_HA_01", "Trạm FNS Line HA 01"), ("QC-03", "Trạm QC 03"))
        statement = text(
            """INSERT INTO stations (station_id, name, active, created_at, updated_at)
            VALUES (:station_id, :name, 1, :created_at, :updated_at)
            ON CONFLICT(station_id) DO NOTHING"""
        )
        with self.begin() as connection:
            connection.execute(
                statement,
                [
                    {
                        "station_id": station_id,
                        "name": name,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for station_id, name in defaults
                ],
            )

    def list_stations(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM stations"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY station_id"
        return self.fetch_all(query)

    def create_station(self, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        self.execute(
            """INSERT INTO stations (station_id, name, active, created_at, updated_at)
            VALUES (:station_id, :name, :active, :created_at, :updated_at)""",
            {
                **record,
                "active": 1 if record.get("active", True) else 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        return self.fetch_one(
            "SELECT * FROM stations WHERE station_id = :station_id", {"station_id": record["station_id"]}
        ) or {}

    def update_station(self, station_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.fetch_one(
            "SELECT * FROM stations WHERE station_id = :station_id", {"station_id": station_id}
        )
        if not existing:
            return None
        fields = {key: value for key, value in patch.items() if value is not None}
        if "active" in patch:
            fields["active"] = 1 if patch["active"] else 0
        if fields:
            fields["updated_at"] = datetime.now(UTC).isoformat()
            assignments = ", ".join(f"{key} = :{key}" for key in fields)
            self.execute(
                f"UPDATE stations SET {assignments} WHERE station_id = :station_id",
                {**fields, "station_id": station_id},
            )
        return self.fetch_one("SELECT * FROM stations WHERE station_id = :station_id", {"station_id": station_id})

    def fetch_all(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(text(query), parameters or {}).mappings().all()
        return [dict(row) for row in rows]

    def fetch_one(self, query: str, parameters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(query), parameters or {}).mappings().first()
        return dict(row) if row else None

    def execute(self, query: str, parameters: dict[str, Any] | None = None) -> None:
        with self.begin() as connection:
            connection.execute(text(query), parameters or {})

    def list_defect_codes(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM defect_catalog"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY defect_type, defect_code"
        return self.fetch_all(query)

    def get_defect_code(self, defect_code: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM defect_catalog WHERE defect_code = :defect_code AND active = 1",
            {"defect_code": defect_code.upper()},
        )

    def match_defect_codes(self, cv_label: str) -> list[dict[str, Any]]:
        return self.fetch_all(
            """SELECT * FROM defect_catalog
            WHERE active = 1 AND (cv_label = :label OR defect_type = :label)
            ORDER BY defect_code""",
            {"label": cv_label.strip().lower()},
        )

    def create_defect_code(self, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        self.execute(
            """INSERT INTO defect_catalog
            (defect_code, defect_type, cv_label, defect_family, display_name, description,
             classification_rule, default_severity, measurement_required, active, created_at, updated_at)
            VALUES (:defect_code, :defect_type, :cv_label, :defect_family, :display_name, :description,
                    :classification_rule,
                    :default_severity, :measurement_required, :active, :created_at, :updated_at)""",
            {
                **record,
                "defect_family": record.get("defect_family") or record["defect_type"].upper(),
                "classification_rule": record.get("classification_rule") or "QC confirmation required",
                "active": 1 if record.get("active", True) else 0,
                "measurement_required": 1 if record.get("measurement_required", False) else 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        return self.get_defect_code(record["defect_code"]) or {}

    def create_qc_decision(self, record: dict[str, Any]) -> dict[str, Any]:
        values = {
            **record,
            "decision_id": str(record.get("decision_id") or uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.execute(
            """INSERT INTO qc_decisions
            (decision_id, thread_id, inspection_id, vehicle_id, defect_code, defect_type,
             location, length_mm, severity, action, disposition,
             reviewer, reason, notes, created_at)
            VALUES (:decision_id, :thread_id, :inspection_id, :vehicle_id, :defect_code,
                    :defect_type, :location, :length_mm, :severity,
                    :action, :disposition, :reviewer, :reason, :notes, :created_at)""",
            values,
        )
        return self.fetch_one(
            "SELECT * FROM qc_decisions WHERE decision_id = :decision_id",
            {"decision_id": values["decision_id"]},
        ) or {}

    def list_qc_decisions(self, *, inspection_id: str | None = None) -> list[dict[str, Any]]:
        if inspection_id:
            return self.fetch_all(
                "SELECT * FROM qc_decisions WHERE inspection_id = :inspection_id ORDER BY created_at DESC",
                {"inspection_id": inspection_id},
            )
        return self.fetch_all("SELECT * FROM qc_decisions ORDER BY created_at DESC")

    def get_or_create_profile(
        self, user_id: str, email: str | None, default_role: str
    ) -> dict[str, Any]:
        """Return the profile row for `user_id`, provisioning one with `default_role`
        on first authenticated request (ENVIRONMENT.md: DEFAULT_QC_ROLE)."""
        existing = self.fetch_one(
            "SELECT * FROM profiles WHERE user_id = :user_id", {"user_id": user_id}
        )
        if existing:
            return existing
        now = datetime.now(UTC).isoformat()
        self.execute(
            """INSERT INTO profiles (user_id, email, role, created_at, updated_at)
            VALUES (:user_id, :email, :role, :created_at, :updated_at)
            ON CONFLICT(user_id) DO NOTHING""",
            {"user_id": user_id, "email": email, "role": default_role, "created_at": now, "updated_at": now},
        )
        return self.fetch_one(
            "SELECT * FROM profiles WHERE user_id = :user_id", {"user_id": user_id}
        ) or {"user_id": user_id, "email": email, "role": default_role}

    _TREND_GROUP_EXPRESSIONS = {
        "hour": "substr(updated_at, 1, 13)",
        "day": "COALESCE(production_date, substr(updated_at, 1, 10))",
        "shift": "COALESCE(shift_id, 'UNASSIGNED')",
        "lot": "COALESCE(lot_id, 'UNASSIGNED')",
    }

    def get_trend(
        self,
        *,
        group_by: str,
        shift_id: str | None = None,
        lot_id: str | None = None,
        station_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Historical Trend aggregation (PRD.md §6.3 / API_CONTRACT.md §7.5).

        Separate from the realtime Sliding Window anomaly engine: this reads
        the latest persisted run per vehicle and groups it by hour/shift/lot/day.
        """
        group_expr = self._TREND_GROUP_EXPRESSIONS.get(group_by)
        if group_expr is None:
            raise ValueError(f"Unsupported group_by={group_by!r}")
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if shift_id:
            clauses.append("shift_id = :shift_id")
            params["shift_id"] = shift_id
        if lot_id:
            clauses.append("lot_id = :lot_id")
            params["lot_id"] = lot_id
        if station_id:
            clauses.append("station_id = :station_id")
            params["station_id"] = station_id
        if date_from:
            clauses.append("COALESCE(production_date, substr(updated_at, 1, 10)) >= :date_from")
            params["date_from"] = date_from
        if date_to:
            clauses.append("COALESCE(production_date, substr(updated_at, 1, 10)) <= :date_to")
            params["date_to"] = date_to
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.fetch_all(
            f"""SELECT
                {group_expr} AS group_value,
                COUNT(*) AS total_inspections,
                SUM(CASE WHEN defect_type = 'scratch' THEN 1 ELSE 0 END) AS scratch_count,
                SUM(CASE WHEN defect_type = 'dent' THEN 1 ELSE 0 END) AS dent_count,
                SUM(CASE WHEN status = 'PASS' THEN 1 ELSE 0 END) AS pass_count
            FROM agent_graph_runs
            {where}
            GROUP BY group_value
            ORDER BY group_value""",
            params,
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            total = row["total_inspections"] or 0
            scratch = row["scratch_count"] or 0
            dent = row["dent_count"] or 0
            passed = row["pass_count"] or 0
            results.append(
                {
                    "group_by": group_by,
                    "group_value": row["group_value"],
                    "total_inspections": total,
                    "scratch_count": scratch,
                    "dent_count": dent,
                    "pass_count": passed,
                    "fail_count": total - passed,
                    "scratch_rate": round(scratch / total, 4) if total else 0.0,
                    "dent_rate": round(dent / total, 4) if total else 0.0,
                    "pass_fail_rate": round(passed / total, 4) if total else 0.0,
                }
            )
        return results

    def close(self) -> None:
        self.engine.dispose()


# Backward-compatible import while callers migrate to the provider-neutral name.
SQLiteDatabase = Database
