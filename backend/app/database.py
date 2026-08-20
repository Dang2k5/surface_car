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
