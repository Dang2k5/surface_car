from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, unquote
from uuid import uuid4

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError


def normalize_database_url(database_url: str) -> str:
    """Normalize a PostgreSQL connection URL (Supabase or self-hosted) for psycopg."""
    value = database_url.strip()
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
    if not value.startswith("postgresql+psycopg://"):
        raise ValueError(
            f"Unsupported DATABASE_URL scheme: {value!r}; only PostgreSQL is supported"
        )
    return _encode_connection_password(value)


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
    """SQLAlchemy Core adapter over the shared Supabase PostgreSQL database.

    `schema` isolates callers (currently: the pytest suite) in a throwaway PostgreSQL
    schema on the same database/project as production, instead of touching `public`.
    """

    def __init__(self, database_url: str, *, schema: str | None = None) -> None:
        self.database_url = normalize_database_url(database_url)
        self.schema = schema
        # Transaction-mode pgbouncer (Supabase pooler port 6543) can route each
        # statement to a different backend connection, so a server-side prepared
        # statement from one may not exist (or may collide by name) on the next
        # -- psycopg's default is to prepare after a few uses, so this must be
        # disabled explicitly (mirrors the checkpointer's own psycopg.connect
        # in backend/app/main.py's _build_qc_checkpointer).
        connect_args: dict[str, Any] = {"prepare_threshold": None}
        # A stuck/slow query would otherwise hold one of the pool's few connections
        # (pool_size=3 + max_overflow=2) indefinitely, starving the rest of the app's
        # DB access -- cap any single statement at 8s so it fails fast instead of hanging.
        options = ["-c statement_timeout=8000"]
        if schema:
            bootstrap_engine = create_engine(self.database_url, pool_pre_ping=True)
            try:
                with bootstrap_engine.begin() as connection:
                    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            finally:
                bootstrap_engine.dispose()
            options.append(f"-c search_path={schema}")
        connect_args["options"] = " ".join(options)
        self.engine: Engine = create_engine(
            self.database_url,
            pool_pre_ping=True,
            # Supabase's pooler already pools connections upstream; keep this
            # app-side pool small so one backend instance can't alone approach
            # the project's shared connection cap (SQLAlchemy's unset default
            # is 5 + 10 overflow = 15, enough on its own to exhaust a small cap).
            pool_size=3,
            max_overflow=2,
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
                source_id TEXT,
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
                full_name TEXT,
                role TEXT NOT NULL DEFAULT 'QC_OPERATOR',
                station_id TEXT,
                active INTEGER NOT NULL DEFAULT 1,
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
                name TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                station_id TEXT,
                shift_id TEXT,
                product_model TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS lot_products (
                product_code TEXT PRIMARY KEY,
                lot_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                vehicle_model TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS stations (
                station_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS production_line_status (
                station_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'RUNNING',
                stop_reason TEXT,
                stopped_by TEXT,
                stopped_at TEXT,
                resumed_by TEXT,
                resumed_at TEXT,
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
        # station_id indexes must run after _ensure_columns() above -- on a database
        # created before this column existed (older schema, additive migration only),
        # CREATE INDEX on agent_graph_runs(station_id) run any earlier fails outright
        # because the column doesn't exist yet on that table.
        self.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_graph_runs_station_updated ON agent_graph_runs(station_id, updated_at DESC)"
        )
        self.execute(
            """CREATE INDEX IF NOT EXISTS idx_agent_graph_runs_trend
            ON agent_graph_runs(station_id, shift_id, lot_id, production_date)"""
        )
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
            "source_id": "TEXT",
            # Structured, machine-evaluable counterpart to the free-text
            # `classification_rule` above (agent/services/defect_rule_engine.py reads
            # these; `classification_rule` stays free text for humans to read). NULL
            # `rule_type` means "no automatic rule configured yet" -- the rule engine
            # always routes those to HITL rather than guessing.
            # rule_type: 'THRESHOLD_MM' | 'MIN_COUNT' | 'REQUIRES_HUMAN' | NULL
            "rule_type": "TEXT",
            "min_mm": "REAL",
            "max_mm": "REAL",
            "min_detection_count": "INTEGER",
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
            # Mirrors QCState.assessment_route (set once in QCNodes.assess_result, never
            # reset) so HitlRateAlertService.get_recent_outcomes_by_station can read the
            # single field it actually needs directly, instead of loading and
            # json.loads()-ing every full `state_json` blob (some are >1MB) on every
            # single inspection submission just to check one boolean-ish column.
            "assessment_route": "TEXT",
        }
        lot_existing = {
            column["name"] for column in inspect(self.engine).get_columns("production_lots")
        }
        lot_columns = {
            "station_id": "TEXT",
            "shift_id": "TEXT",
            "name": "TEXT NOT NULL DEFAULT ''",
            "product_model": "TEXT NOT NULL DEFAULT ''",
            "quantity": "INTEGER NOT NULL DEFAULT 0",
        }
        station_existing = {
            column["name"] for column in inspect(self.engine).get_columns("stations")
        }
        profile_existing = {
            column["name"] for column in inspect(self.engine).get_columns("profiles")
        }
        product_existing = {
            column["name"] for column in inspect(self.engine).get_columns("lot_products")
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
            # A lot no longer has a single fixed vehicle_type — each product's model is supplied
            # per-inspection when its code is allocated (Database.allocate_lot_product).
            if "vehicle_type" in lot_existing:
                connection.execute(text("ALTER TABLE production_lots DROP COLUMN vehicle_type"))
            if "vehicle_model" not in product_existing:
                connection.execute(
                    text("ALTER TABLE lot_products ADD COLUMN vehicle_model TEXT NOT NULL DEFAULT ''")
                )
            if "vehicle_type" in product_existing:
                connection.execute(
                    text(
                        "UPDATE lot_products SET vehicle_model = vehicle_type "
                        "WHERE vehicle_model = '' AND vehicle_type IS NOT NULL"
                    )
                )
                connection.execute(text("ALTER TABLE lot_products DROP COLUMN vehicle_type"))
            if "zone_name" in station_existing:
                connection.execute(text("ALTER TABLE stations DROP COLUMN zone_name"))
            if "station_id" not in profile_existing:
                connection.execute(text("ALTER TABLE profiles ADD COLUMN station_id TEXT"))
            if "full_name" not in profile_existing:
                connection.execute(text("ALTER TABLE profiles ADD COLUMN full_name TEXT"))
            # Deactivating an account is how a supervisor offboards someone (staff left, rotated
            # out) — enforced centrally in backend/app/auth.py's get_current_user, so every
            # endpoint is closed at once. Existing rows default to active.
            if "active" not in profile_existing:
                connection.execute(
                    text("ALTER TABLE profiles ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
                )
        self._backfill_default_defect_code_rules()

    def _backfill_default_defect_code_rules(self) -> None:
        """One-time, idempotent seed of `rule_type`/`min_mm`/`max_mm`/`min_detection_count`
        for the standard catalog codes (mirrors the bands in
        agent/services/defect_catalog.py's StaticDefectCatalog). Only fills rows that still
        have `rule_type IS NULL` -- a supervisor-authored code (or one already migrated)
        is never touched. Codes whose classification_rule is qualitative
        ("... and QC confirmation", "left/right edge position") get REQUIRES_HUMAN: the
        rule engine must never guess on those, only a human can."""
        threshold_defaults = {
            "DENT01": (None, 25),
            "DENT02": (25, 50),
            "DENT03": (50, None),
            "SCRATCH01": (None, 50),
            "SCRATCH02": (50, 100),
            "SCRATCH03": (100, None),
        }
        min_count_defaults = {"DENT05": 2, "SCRATCH04": 2}
        requires_human_defaults = ("DENT04", "SCRATCH05")
        with self.begin() as connection:
            for code, (min_mm, max_mm) in threshold_defaults.items():
                connection.execute(
                    text(
                        """UPDATE defect_catalog SET rule_type = 'THRESHOLD_MM',
                        min_mm = :min_mm, max_mm = :max_mm
                        WHERE defect_code = :code AND rule_type IS NULL"""
                    ),
                    {"code": code, "min_mm": min_mm, "max_mm": max_mm},
                )
            for code, min_count in min_count_defaults.items():
                connection.execute(
                    text(
                        """UPDATE defect_catalog SET rule_type = 'MIN_COUNT',
                        min_detection_count = :min_count
                        WHERE defect_code = :code AND rule_type IS NULL"""
                    ),
                    {"code": code, "min_count": min_count},
                )
            for code in requires_human_defaults:
                connection.execute(
                    text(
                        """UPDATE defect_catalog SET rule_type = 'REQUIRES_HUMAN'
                        WHERE defect_code = :code AND rule_type IS NULL"""
                    ),
                    {"code": code},
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

    def delete_shift(self, shift_id: str) -> bool:
        """Hard delete -- only when this shift was never referenced by a real inspection
        (agent_graph_runs) or production lot (production_lots). Shifts/stations have no
        DB-level foreign key (unlike defect_catalog -> qc_decisions), so this is checked
        explicitly rather than relying on a database-raised IntegrityError. Returns False
        if the shift doesn't exist; raises ValueError if it's in use (caller maps to 409)."""
        if self.get_shift(shift_id) is None:
            return False
        in_use = self.fetch_one(
            """SELECT 1 AS hit FROM agent_graph_runs WHERE shift_id = :shift_id
            UNION ALL
            SELECT 1 AS hit FROM production_lots WHERE shift_id = :shift_id
            LIMIT 1""",
            {"shift_id": shift_id},
        )
        if in_use:
            raise ValueError(
                "Ca làm việc đã được dùng trong inspection hoặc lô sản xuất — không thể xóa cứng, chỉ có thể Tắt."
            )
        self.execute("DELETE FROM shifts WHERE shift_id = :shift_id", {"shift_id": shift_id})
        return True

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
            (lot_id, name, note, station_id, shift_id, product_model, quantity, active, created_at, updated_at)
            VALUES (:lot_id, :name, :note, :station_id, :shift_id, :product_model, :quantity, :active,
                    :created_at, :updated_at)""",
            {
                **record,
                "active": 1 if record.get("active", True) else 0,
                "created_at": now,
                "updated_at": now,
            },
        )
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
        return self.fetch_one("SELECT * FROM production_lots WHERE lot_id = :lot_id", {"lot_id": lot_id})

    def count_lot_products(self, lot_id: str) -> int:
        row = self.fetch_one(
            "SELECT COUNT(*) AS n FROM lot_products WHERE lot_id = :lot_id", {"lot_id": lot_id}
        )
        return int(row["n"]) if row else 0

    def allocate_lot_product(self, lot_id: str, vehicle_model: str) -> dict[str, Any]:
        """Allocate the next sequential product code for a lot as it passes the camera:
        <Mã Lô>-<Model sản phẩm>-<STT>, STT starting at 1 and counting up per lot until the
        lot's quantity is used up. Caller (catalog_api.create_lot_product) has already checked
        the lot exists, is active, and has remaining capacity; the small retry loop here just
        guards against a rare race between two allocations reading the same count."""
        now = datetime.now(UTC).isoformat()
        statement = text(
            """INSERT INTO lot_products (product_code, lot_id, seq, vehicle_model, created_at)
            VALUES (:product_code, :lot_id, :seq, :vehicle_model, :created_at)"""
        )
        for _ in range(5):
            seq = self.count_lot_products(lot_id) + 1
            product_code = f"{lot_id}-{vehicle_model}-{seq}"
            try:
                with self.begin() as connection:
                    connection.execute(
                        statement,
                        {
                            "product_code": product_code,
                            "lot_id": lot_id,
                            "seq": seq,
                            "vehicle_model": vehicle_model,
                            "created_at": now,
                        },
                    )
            except IntegrityError:
                continue
            return self.fetch_one(
                "SELECT * FROM lot_products WHERE product_code = :product_code",
                {"product_code": product_code},
            ) or {}
        raise RuntimeError(f"Could not allocate a product code for lot {lot_id} after 5 attempts")

    def list_lot_products(self, lot_id: str) -> list[dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM lot_products WHERE lot_id = :lot_id ORDER BY seq", {"lot_id": lot_id}
        )

    def _seed_stations(self) -> None:
        """Seed the standard QC stations so the dropdown isn't empty on a fresh database.
        ON CONFLICT DO NOTHING preserves Supervisor edits."""
        now = datetime.now(UTC).isoformat()
        defaults = (("QC-01", "Trạm QC 01"), ("QC-02", "Trạm QC 02"), ("QC-03", "Trạm QC 03"))
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

    def delete_station(self, station_id: str) -> bool:
        """Hard delete -- only when this station was never referenced by a real inspection
        (agent_graph_runs), production lot (production_lots), or a QC account's assigned
        station (profiles). Returns False if the station doesn't exist; raises ValueError
        if it's in use (caller maps to 409)."""
        if self.get_station(station_id) is None:
            return False
        in_use = self.fetch_one(
            """SELECT 1 AS hit FROM agent_graph_runs WHERE station_id = :station_id
            UNION ALL
            SELECT 1 AS hit FROM production_lots WHERE station_id = :station_id
            UNION ALL
            SELECT 1 AS hit FROM profiles WHERE station_id = :station_id
            LIMIT 1""",
            {"station_id": station_id},
        )
        if in_use:
            raise ValueError(
                "Trạm đã được dùng trong inspection, lô sản xuất hoặc gán cho tài khoản — không thể xóa cứng, chỉ có thể Tắt."
            )
        self.execute("DELETE FROM stations WHERE station_id = :station_id", {"station_id": station_id})
        return True

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

    def list_defect_codes(
        self, *, active_only: bool = True, limit: int = 500, offset: int = 0
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM defect_catalog"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY defect_type, defect_code LIMIT :limit OFFSET :offset"
        return self.fetch_all(query, {"limit": limit, "offset": offset})

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
             classification_rule, default_severity, measurement_required, active, source_id,
             rule_type, min_mm, max_mm, min_detection_count,
             created_at, updated_at)
            VALUES (:defect_code, :defect_type, :cv_label, :defect_family, :display_name, :description,
                    :classification_rule,
                    :default_severity, :measurement_required, :active, :source_id,
                    :rule_type, :min_mm, :max_mm, :min_detection_count,
                    :created_at, :updated_at)""",
            {
                **record,
                "defect_family": record.get("defect_family") or record["defect_type"].upper(),
                "description": record.get("description") or "",
                "classification_rule": record.get("classification_rule") or "QC confirmation required",
                "active": 1 if record.get("active", True) else 0,
                "measurement_required": 1 if record.get("measurement_required", False) else 0,
                "source_id": record.get("source_id"),
                # NULL rule_type means "no automatic rule yet" -- the rule engine
                # (agent/services/defect_rule_engine.py) always routes those to HITL.
                "rule_type": record.get("rule_type"),
                "min_mm": record.get("min_mm"),
                "max_mm": record.get("max_mm"),
                "min_detection_count": record.get("min_detection_count"),
                "created_at": now,
                "updated_at": now,
            },
        )
        return self.get_defect_code(record["defect_code"]) or {}

    def update_defect_code(self, defect_code: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        code = defect_code.upper()
        existing = self.fetch_one(
            "SELECT * FROM defect_catalog WHERE defect_code = :defect_code", {"defect_code": code}
        )
        if not existing:
            return None
        fields = {key: value for key, value in patch.items() if value is not None}
        if "active" in patch:
            fields["active"] = 1 if patch["active"] else 0
        if "measurement_required" in patch:
            fields["measurement_required"] = 1 if patch["measurement_required"] else 0
        if fields:
            fields["updated_at"] = datetime.now(UTC).isoformat()
            assignments = ", ".join(f"{key} = :{key}" for key in fields)
            self.execute(
                f"UPDATE defect_catalog SET {assignments} WHERE defect_code = :defect_code",
                {**fields, "defect_code": code},
            )
        return self.fetch_one(
            "SELECT * FROM defect_catalog WHERE defect_code = :defect_code", {"defect_code": code}
        )

    def delete_defect_code(self, defect_code: str) -> bool:
        """Hard delete -- defect_catalog has a real DB-level foreign key from
        qc_decisions.defect_code (unlike shifts/stations), so a code that was ever used in
        a real QC decision raises IntegrityError here instead of silently breaking that
        decision's audit trail; the caller maps it to 409. Returns False if it doesn't exist."""
        code = defect_code.upper()
        existing = self.fetch_one(
            "SELECT 1 FROM defect_catalog WHERE defect_code = :defect_code", {"defect_code": code}
        )
        if existing is None:
            return False
        self.execute("DELETE FROM defect_catalog WHERE defect_code = :defect_code", {"defect_code": code})
        return True

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

    def list_qc_decisions(
        self, *, inspection_id: str | None = None, limit: int = 500, offset: int = 0
    ) -> list[dict[str, Any]]:
        if inspection_id:
            return self.fetch_all(
                """SELECT * FROM qc_decisions WHERE inspection_id = :inspection_id
                ORDER BY created_at DESC LIMIT :limit OFFSET :offset""",
                {"inspection_id": inspection_id, "limit": limit, "offset": offset},
            )
        return self.fetch_all(
            "SELECT * FROM qc_decisions ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
            {"limit": limit, "offset": offset},
        )

    def get_or_create_profile(
        self,
        user_id: str,
        email: str | None,
        default_role: str,
        full_name: str | None = None,
        station_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the profile row for `user_id`, provisioning one with `default_role`
        on first authenticated request (ENVIRONMENT.md: DEFAULT_QC_ROLE).

        `full_name` and `station_id` come from the Supabase JWT's `user_metadata`, set at
        sign-up (frontend/src/lib/auth.tsx signUp). Backfill them onto an already-provisioned
        row too — the first authenticated request can race the metadata landing on the token,
        and older rows were provisioned before these columns existed.

        `station_id` is only honoured when it names a station that actually exists; a stale or
        removed station in the token is ignored rather than blocking sign-in, leaving the
        account unassigned for a supervisor to fix (frontend/src/routes/supervisor/accounts.tsx).
        """
        if station_id and self.get_station(station_id) is None:
            station_id = None
        existing = self.fetch_one(
            "SELECT * FROM profiles WHERE user_id = :user_id", {"user_id": user_id}
        )
        if existing:
            backfill: dict[str, Any] = {}
            if full_name and not existing.get("full_name"):
                backfill["full_name"] = full_name
            if station_id and not existing.get("station_id"):
                backfill["station_id"] = station_id
            if backfill:
                assignments = ", ".join(f"{key} = :{key}" for key in backfill)
                self.execute(
                    f"UPDATE profiles SET {assignments}, updated_at = :updated_at "
                    "WHERE user_id = :user_id",
                    {
                        **backfill,
                        "updated_at": datetime.now(UTC).isoformat(),
                        "user_id": user_id,
                    },
                )
                existing = {**existing, **backfill}
            return existing
        now = datetime.now(UTC).isoformat()
        self.execute(
            """INSERT INTO profiles
            (user_id, email, full_name, role, station_id, active, created_at, updated_at)
            VALUES (:user_id, :email, :full_name, :role, :station_id, 1, :created_at, :updated_at)
            ON CONFLICT(user_id) DO NOTHING""",
            {
                "user_id": user_id,
                "email": email,
                "full_name": full_name,
                "role": default_role,
                "station_id": station_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        return self.fetch_one(
            "SELECT * FROM profiles WHERE user_id = :user_id", {"user_id": user_id}
        ) or {
            "user_id": user_id,
            "email": email,
            "full_name": full_name,
            "role": default_role,
            "station_id": station_id,
            "active": 1,
        }

    def list_profiles(self) -> list[dict[str, Any]]:
        return self.fetch_all("SELECT * FROM profiles ORDER BY created_at")

    def update_profile(self, user_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Supervisor-only account management: reassign an inspector's station, promote/demote
        between QC_OPERATOR and QC_SUPERVISOR, or deactivate the account (backend/app/auth_api.py)."""
        existing = self.fetch_one(
            "SELECT * FROM profiles WHERE user_id = :user_id", {"user_id": user_id}
        )
        if not existing:
            return None
        fields = {
            key: value for key, value in patch.items() if key in ("role", "station_id", "active")
        }
        if "active" in fields:
            fields["active"] = 1 if fields["active"] else 0
        if fields:
            fields["updated_at"] = datetime.now(UTC).isoformat()
            assignments = ", ".join(f"{key} = :{key}" for key in fields)
            self.execute(
                f"UPDATE profiles SET {assignments} WHERE user_id = :user_id",
                {**fields, "user_id": user_id},
            )
        return self.fetch_one("SELECT * FROM profiles WHERE user_id = :user_id", {"user_id": user_id})

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

    def get_recent_outcomes_by_station(self, station_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Most recent inspection outcomes for one station, newest first.

        Used by HitlRateAlertService to compute the HITL streak/rate signals — deliberately
        a lightweight, station-scoped query instead of PostgresQCRepository.list_with_metadata()
        (which loads every station's latest-per-vehicle rows with no LIMIT).

        Returns the dedicated `assessment_route` column (not the `status` column): `status`
        is overwritten with the final PASS/FAIL once a HITL case is resumed
        (backend/app/langgraph_api.py's resume_langgraph_inspection re-saves with the
        completed state), so it can no longer tell "this case needed a human" after the
        fact. `assessment_route` is set once in assess_result and never reset by
        human_review/supervisor_review/generate_recommendation, so it stays a reliable "did
        this need HITL" marker whether the case is still pending or already resolved.

        Selects `assessment_route` directly instead of `state_json` -- some persisted states
        are well over 1MB (full detections/segmentation/execution_trace), and this query runs
        on every single inspection submission (_enforce_line_gate), so loading and
        `json.loads()`-ing up to `limit` full blobs just to read one field was adding a real,
        avoidable latency tax ahead of every inspection.
        """
        return self.fetch_all(
            """SELECT assessment_route, updated_at FROM agent_graph_runs
            WHERE station_id = :station_id
            ORDER BY updated_at DESC
            LIMIT :limit""",
            {"station_id": station_id, "limit": limit},
        )

    def get_line_status(self, station_id: str) -> dict[str, Any] | None:
        return self.fetch_one(
            "SELECT * FROM production_line_status WHERE station_id = :station_id",
            {"station_id": station_id},
        )

    def stop_line(self, station_id: str, user_id: str, reason: str) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        self.execute(
            """INSERT INTO production_line_status
            (station_id, status, stop_reason, stopped_by, stopped_at, resumed_by, resumed_at, updated_at)
            VALUES (:station_id, 'STOPPED', :reason, :user_id, :now, NULL, NULL, :now)
            ON CONFLICT(station_id) DO UPDATE SET
                status = 'STOPPED',
                stop_reason = excluded.stop_reason,
                stopped_by = excluded.stopped_by,
                stopped_at = excluded.stopped_at,
                resumed_by = NULL,
                resumed_at = NULL,
                updated_at = excluded.updated_at""",
            {"station_id": station_id, "reason": reason, "user_id": user_id, "now": now},
        )
        return self.get_line_status(station_id) or {}

    def resume_line(self, station_id: str, user_id: str) -> dict[str, Any] | None:
        """Returns None if the station has no status row at all (never stopped)."""
        existing = self.get_line_status(station_id)
        if existing is None:
            return None
        now = datetime.now(UTC).isoformat()
        self.execute(
            """UPDATE production_line_status SET
                status = 'RUNNING',
                resumed_by = :user_id,
                resumed_at = :now,
                updated_at = :now
            WHERE station_id = :station_id""",
            {"station_id": station_id, "user_id": user_id, "now": now},
        )
        return self.get_line_status(station_id)

    def close(self) -> None:
        self.engine.dispose()
