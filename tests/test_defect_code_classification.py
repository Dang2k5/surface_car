import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from agent.services.defect_catalog import StaticDefectCatalog
from agent.services.reasoning import DeterministicReasoningService
from backend.app.database import Database
from backend.app.main import app


def test_created_defect_codes_are_persisted_and_retrievable(test_database: Database) -> None:
    # defect_catalog is no longer auto-seeded (backend/app/database.py) -- a fresh
    # database starts empty and codes are written through create_defect_code, the same
    # path POST /api/qc/defect-codes uses (i.e. exactly what a supervisor does via the UI).
    test_database.create_defect_code(
        {
            "defect_code": "SCRATCH01",
            "defect_type": "scratch",
            "cv_label": "scratch",
            "defect_family": "SURFACE_SCRATCH",
            "display_name": "Vết xước nhỏ",
            "classification_rule": "estimated_width_mm <= 50",
            "default_severity": "C",
            "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL",
        }
    )
    test_database.create_defect_code(
        {
            "defect_code": "DENT01",
            "defect_type": "dent",
            "cv_label": "dent",
            "defect_family": "PANEL_DENT",
            "display_name": "Vết móp nhỏ",
            "classification_rule": "estimated_width_mm <= 25",
            "default_severity": "C",
            "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL",
        }
    )
    codes = test_database.list_defect_codes()
    assert {item["defect_code"] for item in codes} == {"SCRATCH01", "DENT01"}
    assert {item["defect_type"] for item in codes} == {"scratch", "dent"}
    assert all(item["defect_family"] for item in codes)
    assert all(item["classification_rule"] for item in codes)
    assert all(item["source_id"] == "FNS-SEVERITY-CRITERIA-INTERNAL" for item in codes)


def test_unused_defect_code_can_be_hard_deleted(test_database: Database) -> None:
    test_database.create_defect_code(
        {
            "defect_code": "SCRATCH99",
            "defect_type": "scratch",
            "cv_label": "scratch",
            "display_name": "Test scratch",
            "default_severity": "C",
        }
    )
    assert test_database.delete_defect_code("SCRATCH99") is True
    assert test_database.list_defect_codes(active_only=False) == []
    # Deleting again (already gone) reports "nothing to delete", not an error.
    assert test_database.delete_defect_code("SCRATCH99") is False


def test_defect_code_used_in_a_qc_decision_cannot_be_hard_deleted(test_database: Database) -> None:
    test_database.create_defect_code(
        {
            "defect_code": "SCRATCH99",
            "defect_type": "scratch",
            "cv_label": "scratch",
            "display_name": "Test scratch",
            "default_severity": "C",
        }
    )
    test_database.create_qc_decision(
        {
            "thread_id": "thread-1",
            "inspection_id": "insp-1",
            "vehicle_id": "veh-1",
            "defect_code": "SCRATCH99",
            "defect_type": "scratch",
            "location": "",
            "length_mm": None,
            "severity": "C",
            "action": "PASS",
            "disposition": "PASS",
            "reviewer": "tester",
            "reason": "test",
            "notes": "",
        }
    )
    # A real DB-level foreign key (qc_decisions.defect_code -> defect_catalog.defect_code)
    # protects this row's audit trail -- the caller (qc_api.py's DELETE endpoint) maps this
    # to HTTP 409 and tells the supervisor to use Tắt (deactivate) instead.
    with pytest.raises(IntegrityError):
        test_database.delete_defect_code("SCRATCH99")


@pytest.fixture(autouse=True)
def _dev_role_bypass(monkeypatch):
    """X-Dev-Role only takes effect when Supabase JWT verification is unconfigured
    (backend/app/auth.py get_current_user) -- clear both env vars so this test can
    simulate QC_SUPERVISOR without a real Supabase token (mirrors test_policy_extraction.py)."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)


@pytest.mark.asyncio
async def test_defect_codes_api_cites_their_severity_source(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/api/qc/defect-codes",
                headers={"X-Dev-Role": "QC_SUPERVISOR"},
                json={
                    "defect_code": "SCRATCH01",
                    "defect_type": "scratch",
                    "cv_label": "scratch",
                    "display_name": "Vết xước nhỏ",
                    "classification_rule": "estimated_width_mm <= 50",
                    "default_severity": "C",
                    "source_id": "FNS-SEVERITY-CRITERIA-INTERNAL",
                },
            )
            assert create_response.status_code == 201
            response = await client.get("/api/qc/defect-codes")
            assert response.status_code == 200
            codes = response.json()
            assert len(codes) == 1
            assert codes[0]["source_id"] == "FNS-SEVERITY-CRITERIA-INTERNAL"
            assert codes[0]["source_document_status"] == "DRAFT"
            assert codes[0]["source_title"]


def test_classifier_selects_size_band_from_fixed_camera_estimate() -> None:
    catalog = StaticDefectCatalog()
    candidates = catalog.match("scratch")
    result = DeterministicReasoningService().classify_defect_code(
        {
            "defect_type": "scratch",
            "detections": [{"class_name": "scratch"}],
            "visual_measurements": {
                "estimated_width_mm": 92.0,
                "relative_position": "middle_center",
            },
            "bbox": {"x1": 0, "y1": 0, "x2": 115, "y2": 20},
        },
        candidates,
    )
    assert result.defect_code == "SCRATCH02"
    assert result.defect_family == "SURFACE_SCRATCH"
    assert result.similar_observation_warning is False


def test_classifier_warns_and_selects_cluster_code_for_similar_detections() -> None:
    catalog = StaticDefectCatalog()
    result = DeterministicReasoningService().classify_defect_code(
        {
            "defect_type": "dent",
            "detections": [{"class_name": "dent"}, {"class_name": "dent"}],
            "visual_measurements": {"estimated_width_mm": 40.0},
            "bbox": {"x1": 0, "y1": 0, "x2": 50, "y2": 50},
        },
        catalog.match("dent"),
    )
    assert result.defect_code == "DENT05"
    assert result.similar_observation_warning is True
