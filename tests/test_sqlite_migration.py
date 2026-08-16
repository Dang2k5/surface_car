from scripts.migrate_sqlite_to_postgres import normalize_row


def test_defect_catalog_backfills_missing_cv_label() -> None:
    row = normalize_row(
        "defect_catalog",
        {
            "defect_code": "CRACK01",
            "defect_type": "crack",
            "cv_label": None,
            "display_name": "Body crack",
            "description": None,
            "default_severity": "A",
            "measurement_required": None,
            "active": None,
        },
    )

    assert row["cv_label"] == "crack"
    assert row["description"] == ""
    assert row["measurement_required"] == 0
    assert row["active"] == 1


def test_non_catalog_row_is_unchanged() -> None:
    row = {"thread_id": "thread-1", "status": "PASS"}
    assert normalize_row("agent_graph_runs", row) == row
