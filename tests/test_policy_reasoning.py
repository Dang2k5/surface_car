from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from agent.services.policy import PolicyCatalog
from agent.services.reasoning import DeterministicReasoningService
from backend.app.main import app


def test_surface_policy_is_cited_but_blocked_from_production_release():
    catalog = PolicyCatalog()
    decision = catalog.evaluate(
        {
            "defect_type": "scratch",
            "confidence": 0.88,
            "severity": "UNASSESSED",
        }
    )
    assert decision.policy_id == "FNS-SURFACE-001"
    assert decision.policy_status == "APPROVED"
    assert decision.approval_scope == "DEMO_BASELINE_ONLY"
    assert decision.production_eligible is False
    assert decision.test_drive_allowed is False
    assert "approved_oem_acceptance_criteria" in decision.missing_evidence
    assert {item.id for item in decision.references} == {
        "FNS-QC-POLICY-DEMO-2026",
        "IATF-16949-2016",
        "ISO-9001-2015",
        "FNS-SEVERITY-CRITERIA-INTERNAL",
    }
    review = decision.document_review
    assert review.query == {
        "vehicle_model": "unknown_model",
        "defect_type": "scratch",
    }
    assert review.matched_document_count == 1
    assert "approved_oem_acceptance_criteria" in review.missing_data
    assert review.approved_checklist
    assert review.proposed_checklist
    assert {item.revision for item in review.citations} == {"2026.08.1", "2016", "2015"}
    warning_codes = {item.code for item in review.warnings}
    assert "POLICY_QUERY_CONTEXT_INCOMPLETE" in warning_codes
    assert "EFFECTIVE_DATE_UNCONFIRMED" not in warning_codes
    assert "CHECKLIST_NOT_APPROVED" not in warning_codes

    analysis = DeterministicReasoningService().analyze(
        {"defect_type": "scratch", "confidence": 0.88, "severity": "UNASSESSED"},
        decision,
    )
    assert analysis.provider == "deterministic"
    assert "DEMO_APPROVAL_NOT_PRODUCTION_RELEASE" in analysis.risk_flags
    assert set(analysis.cited_source_ids) == {
        "FNS-QC-POLICY-DEMO-2026",
        "IATF-16949-2016",
        "ISO-9001-2015",
        "FNS-SEVERITY-CRITERIA-INTERNAL",
    }


def test_document_review_blocks_expired_and_conflicting_revisions(tmp_path):
    source = PolicyCatalog().public_catalog()
    catalog_document = json.loads(json.dumps(source))
    base = catalog_document["sources"][0]
    base.update(
        {
            "document_status": "APPROVED",
            "authority": "CONTROLLED_POLICY",
            "effective_date": "2020-01-01",
            "expiry_date": "2020-12-31",
        }
    )
    conflicting = {**base, "id": "IATF-16949-2024", "revision": "2024", "expiry_date": None}
    catalog_document["sources"].append(conflicting)
    surface = next(item for item in catalog_document["policies"] if item["id"] == "FNS-SURFACE-001")
    surface["source_ids"] = [base["id"], conflicting["id"]]
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog_document), encoding="utf-8")

    decision = PolicyCatalog(path).evaluate(
        {
            "vehicle_model": "SUV_EV_2026",
            "defect_type": "scratch",
        }
    )
    warning_codes = {item.code for item in decision.document_review.warnings}
    assert "DOCUMENT_EXPIRED" in warning_codes
    assert "REVISION_CONFLICT" in warning_codes
    assert decision.production_eligible is False


def _catalog_with_draft_policy(tmp_path, defect_type: str):
    catalog_document = json.loads(json.dumps(PolicyCatalog().public_catalog()))
    draft_policy = {
        "id": "FNS-DRAFT-TEST-001",
        "title": "Draft policy not yet reviewed",
        "applicability": {"vehicle_models": ["*"]},
        "conditions": [],
        "checklist_status": "DRAFT",
        "defect_types": [defect_type],
        "action_code": "SURFACE_DAMAGE_ASSESSMENT_AND_REINSPECT",
        "final_status": "PASS",
        "test_drive_allowed": True,
        "human_required": False,
        "required_evidence": [],
        "steps": [],
        "source_ids": [],
    }
    # Insert ahead of any approved policy so a naive "first match wins" lookup
    # would pick the DRAFT one if the approval gate were missing.
    catalog_document["policies"].insert(0, draft_policy)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog_document), encoding="utf-8")
    return path


def test_draft_policy_is_skipped_in_favor_of_an_approved_match(tmp_path):
    # scratch already has an APPROVED policy (FNS-SURFACE-001) -- the DRAFT one
    # must never win the match just by being listed first.
    path = _catalog_with_draft_policy(tmp_path, "scratch")
    decision = PolicyCatalog(path).evaluate({"defect_type": "scratch", "vehicle_model": "unknown_model"})
    assert decision.policy_id == "FNS-SURFACE-001"

    # Naming it explicitly (evaluate_named) is an internal/administrative lookup,
    # not the automatic per-defect routing path, so it is not gated the same way.
    named = PolicyCatalog(path).evaluate_named(
        "FNS-DRAFT-TEST-001", {"defect_type": "scratch", "vehicle_model": "unknown_model"}
    )
    assert named.policy_id == "FNS-DRAFT-TEST-001"


def test_draft_policy_with_no_approved_alternative_falls_back_to_manual_reinspection(tmp_path):
    # A DRAFT policy (freshly saved from the Rules UI, or AI-extracted but not yet
    # reviewed) must not silently start deciding real vehicles -- with no other
    # approved policy for this defect type, routing must fall through to the
    # manual-reinspection fail-safe until a supervisor approves it.
    path = _catalog_with_draft_policy(tmp_path, "custom_test_defect")
    decision = PolicyCatalog(path).evaluate(
        {"defect_type": "custom_test_defect", "vehicle_model": "unknown_model"}
    )
    assert decision.policy_id == "FNS-MANUAL-001"
    assert decision.final_status == "FAIL"
    assert decision.human_required is True


@pytest.mark.asyncio
async def test_policy_catalog_api_exposes_revision_status_and_references(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            catalog = await client.get("/api/policies")
            assert catalog.status_code == 200
            assert catalog.json()["status"] == "APPROVED"

            policy = await client.get("/api/policies/FNS-GEOMETRY-001")
            assert policy.status_code == 200
            body = policy.json()
            assert body["catalog_status"] == "APPROVED"
            assert body["approval_scope"] == "DEMO_BASELINE_ONLY"
            assert {item["id"] for item in body["references"]} == {
                "FNS-QC-POLICY-DEMO-2026",
                "ISO-1101-2017",
                "IATF-16949-2016",
                "ISO-9001-2015",
                "FNS-SEVERITY-CRITERIA-INTERNAL",
            }
