from backend.app.database import normalize_database_url
from scripts.migrate_sqlite_to_postgres import normalize_target_url


def test_database_url_encodes_reserved_password_characters() -> None:
    raw_url = (
        "postgresql://postgres.project:secret@7#qc?"
        "@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
    )
    expected = (
        "postgresql+psycopg://postgres.project:secret%407%23qc%3F"
        "@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
    )

    assert normalize_database_url(raw_url) == expected
    assert normalize_target_url(raw_url) == expected


def test_database_url_preserves_existing_percent_encoding() -> None:
    encoded_url = (
        "postgresql://postgres.project:secret%407"
        "@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"
    )

    assert "%2540" not in normalize_database_url(encoded_url)
    assert "%2540" not in normalize_target_url(encoded_url)


def test_database_url_encodes_literal_percent_in_plaintext_password() -> None:
    raw_url = (
        "postgresql://postgres.project:example%pass@7"
        "@aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres"
    )

    normalized = normalize_database_url(raw_url)
    assert "example%25pass%407@aws-0-ap-southeast-2.pooler.supabase.com" in normalized
