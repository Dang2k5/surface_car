from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, create_engine, inspect, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "visual_qc.db"
TABLE_ORDER = ("defect_catalog", "agent_graph_runs", "qc_decisions")
PRIMARY_KEYS = {
    "defect_catalog": "defect_code",
    "agent_graph_runs": "thread_id",
    "qc_decisions": "decision_id",
}
TEST_VEHICLE_PREFIXES = ("TEST-", "MOCK-", "DEMO-")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate Visual QC business data from SQLite to Supabase PostgreSQL.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="SQLite database path (default: data/visual_qc.db).",
    )
    parser.add_argument(
        "--target-url",
        default=None,
        help="PostgreSQL URL. Defaults to DATABASE_URL; never printed by this script.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write to PostgreSQL. Without this flag the script only performs a dry-run.",
    )
    parser.add_argument(
        "--exclude-test-data",
        action="store_true",
        help="Exclude obvious TEST-/MOCK-/DEMO- vehicles and mock_scenario graph states.",
    )
    parser.add_argument(
        "--on-conflict",
        choices=("update", "skip"),
        default="update",
        help="How to handle rows whose primary key already exists (default: update).",
    )
    parser.add_argument("--batch-size", type=int, default=200)
    return parser.parse_args()


def normalize_target_url(url: str) -> str:
    value = url.strip()
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgres://")
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
    if value.startswith("postgresql+psycopg://"):
        scheme, remainder = value.split("://", 1)
        if "@" in remainder:
            user_info, server = remainder.rsplit("@", 1)
            if ":" in user_info:
                username, password = user_info.split(":", 1)
                encoded_password = quote(unquote(password), safe="")
                value = f"{scheme}://{username}:{encoded_password}@{server}"
    return value


def is_test_row(table_name: str, row: dict[str, Any]) -> bool:
    vehicle_id = str(row.get("vehicle_id") or "").upper()
    if vehicle_id.startswith(TEST_VEHICLE_PREFIXES):
        return True
    if table_name != "agent_graph_runs":
        return False
    try:
        state = json.loads(str(row.get("state_json") or "{}"))
    except json.JSONDecodeError:
        return False
    marker = str(state.get("mock_scenario") or "").strip()
    image_url = str(state.get("image_url") or "").lower()
    return bool(marker or "/test-fixtures/" in image_url)


def batched(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def reflect_table(engine: Engine, table_name: str) -> Table:
    metadata = MetaData()
    return Table(table_name, metadata, autoload_with=engine)


def normalize_row(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    """Backfill fields introduced after the first SQLite MVP schema."""
    if table_name != "defect_catalog":
        return row

    defect_type = str(row.get("defect_type") or "unknown").strip().lower()
    cv_label = str(row.get("cv_label") or defect_type).strip().lower()
    row.update(
        defect_type=defect_type,
        cv_label=cv_label.replace(" ", "_"),
        defect_family=str(row.get("defect_family") or defect_type.upper()),
        display_name=str(row.get("display_name") or row.get("defect_code") or defect_type),
        description=str(row.get("description") or ""),
        classification_rule=str(row.get("classification_rule") or "QC confirmation required"),
        default_severity=str(row.get("default_severity") or "UNASSESSED"),
        measurement_required=int(row.get("measurement_required") or 0),
        active=int(row.get("active") if row.get("active") is not None else 1),
    )
    return row


def load_rows(
    source_engine: Engine,
    target_engine: Engine,
    table_name: str,
    *,
    exclude_test_data: bool,
) -> tuple[list[dict[str, Any]], int]:
    source_table = reflect_table(source_engine, table_name)
    target_columns = {
        column["name"] for column in inspect(target_engine).get_columns(table_name)
    }
    with source_engine.connect() as connection:
        raw_rows = [dict(row) for row in connection.execute(select(source_table)).mappings()]
    excluded = 0
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if exclude_test_data and is_test_row(table_name, row):
            excluded += 1
            continue
        compatible_row = {key: value for key, value in row.items() if key in target_columns}
        rows.append(normalize_row(table_name, compatible_row))
    return rows, excluded


def upsert_rows(
    target_engine: Engine,
    table_name: str,
    rows: list[dict[str, Any]],
    *,
    conflict_mode: str,
    batch_size: int,
) -> None:
    if not rows:
        return
    table = reflect_table(target_engine, table_name)
    primary_key = PRIMARY_KEYS[table_name]
    with target_engine.begin() as connection:
        for batch in batched(rows, batch_size):
            statement = postgresql_insert(table).values(batch)
            if conflict_mode == "skip":
                statement = statement.on_conflict_do_nothing(index_elements=[primary_key])
            else:
                update_columns = {
                    column.name: statement.excluded[column.name]
                    for column in table.columns
                    if column.name != primary_key and column.name in batch[0]
                }
                statement = statement.on_conflict_do_update(
                    index_elements=[primary_key],
                    set_=update_columns,
                )
            connection.execute(statement)


def verify_primary_keys(
    target_engine: Engine,
    table_name: str,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    if not rows:
        return 0, 0
    table = reflect_table(target_engine, table_name)
    primary_key = PRIMARY_KEYS[table_name]
    expected = {row[primary_key] for row in rows}
    found: set[Any] = set()
    with target_engine.connect() as connection:
        for key_batch in batched([{primary_key: value} for value in expected], 500):
            values = [item[primary_key] for item in key_batch]
            result = connection.execute(
                select(table.c[primary_key]).where(table.c[primary_key].in_(values))
            )
            found.update(result.scalars())
    return len(expected), len(found)


def main() -> int:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    source_path = args.source.resolve()
    if not source_path.is_file():
        print(f"ERROR: SQLite source not found: {source_path}", file=sys.stderr)
        return 2
    if args.batch_size < 1:
        print("ERROR: --batch-size must be at least 1", file=sys.stderr)
        return 2

    target_url = args.target_url or os.getenv("DATABASE_URL", "")
    target_url = normalize_target_url(target_url)
    if not target_url.startswith("postgresql+psycopg://"):
        print(
            "ERROR: target must be a PostgreSQL/Supabase URL using psycopg. "
            "Set DATABASE_URL or pass --target-url.",
            file=sys.stderr,
        )
        return 2

    source_engine = create_engine(f"sqlite+pysqlite:///{source_path.as_posix()}")
    target_engine = create_engine(target_url, pool_pre_ping=True)
    try:
        source_tables = set(inspect(source_engine).get_table_names())
        target_tables = set(inspect(target_engine).get_table_names())
        missing_source = [name for name in TABLE_ORDER if name not in source_tables]
        missing_target = [name for name in TABLE_ORDER if name not in target_tables]
        if missing_source:
            print(f"ERROR: source is missing table(s): {', '.join(missing_source)}", file=sys.stderr)
            return 2
        if missing_target:
            print(
                "ERROR: Supabase is missing table(s): "
                f"{', '.join(missing_target)}. Run database/supabase_schema.sql first.",
                file=sys.stderr,
            )
            return 2

        prepared: dict[str, list[dict[str, Any]]] = {}
        print("Visual QC SQLite → Supabase migration")
        print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
        print(f"Source: {source_path}")
        print("Target: PostgreSQL connection verified (credentials hidden)")
        for table_name in TABLE_ORDER:
            rows, excluded = load_rows(
                source_engine,
                target_engine,
                table_name,
                exclude_test_data=args.exclude_test_data,
            )
            prepared[table_name] = rows
            print(f"  {table_name}: ready={len(rows)}, excluded={excluded}")

        if not args.execute:
            print("Dry-run complete. Re-run with --execute to write these rows.")
            return 0

        for table_name in TABLE_ORDER:
            upsert_rows(
                target_engine,
                table_name,
                prepared[table_name],
                conflict_mode=args.on_conflict,
                batch_size=args.batch_size,
            )
            expected, found = verify_primary_keys(
                target_engine,
                table_name,
                prepared[table_name],
            )
            print(f"  {table_name}: verified={found}/{expected}")
            if found != expected:
                print(f"ERROR: verification failed for {table_name}", file=sys.stderr)
                return 1
        print("Migration completed. The SQLite source was not modified or deleted.")
        return 0
    except IntegrityError as error:
        original = getattr(error, "orig", error)
        print(
            "ERROR: migration data violates the Supabase schema. "
            f"No partial batch was committed. Detail: {original}",
            file=sys.stderr,
        )
        return 2
    except SQLAlchemyError as error:
        original = getattr(error, "orig", error)
        print(
            "ERROR: cannot connect to Supabase PostgreSQL. Check the Session pooler "
            f"host, database password, network and sslmode. Detail: {original}",
            file=sys.stderr,
        )
        return 2
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
