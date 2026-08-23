from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from backend.app.database import Database, normalize_database_url


@pytest.fixture
def test_db_schema(monkeypatch) -> str:
    """A throwaway PostgreSQL schema for one test, on the same Supabase project as
    production (DATABASE_URL) -- isolates test data without touching real QC records."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        pytest.fail(
            "DATABASE_URL is not set. Tests run against the real Supabase PostgreSQL "
            "project used in production, isolated per test in a throwaway schema -- "
            "set DATABASE_URL (same connection string as production) before running "
            "pytest. See docs/ENVIRONMENT.md."
        )
    schema = f"test_{uuid4().hex[:16]}"
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    yield schema
    normalized = normalize_database_url(database_url)
    engine = create_engine(normalized, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def use_isolated_test_environment(monkeypatch, tmp_path, test_db_schema):
    """Tests run the same real local_yolo detector and PostgreSQL as production; only
    the schema (test_db_schema) isolates each test's data from real QC records."""
    monkeypatch.setenv("QC_REASONING_PROVIDER", "deterministic")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.setenv("AUDIT_AUTO_EXPORT_ENABLED", "true")
    monkeypatch.setenv("AUDIT_EXPORT_DIR", str(tmp_path / "audit-exports"))


@pytest.fixture
def test_database(test_db_schema: str) -> Database:
    """A real Database connected to the isolated per-test schema, for tests that need
    direct repository/catalog access without going through the FastAPI app."""
    database = Database(os.environ["DATABASE_URL"], schema=test_db_schema)
    try:
        yield database
    finally:
        database.close()
