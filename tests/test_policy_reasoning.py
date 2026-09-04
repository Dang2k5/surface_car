from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from agent.services.policy import PolicyCatalog
from agent.services.reasoning import DeterministicReasoningService
from backend.app.database import Database
from backend.app.main import app


def test_surface_policy_is_cited_but_blocked_from_production_release(test_database):
    catalog = PolicyCatalog(test_database)
    decision = catalog.evaluate(
        {
            "defect_type": "scratch",
            "catalog_defect_type": "scratch",
            # SCRATCH02 (medium) -- FNS-SURFACE-001 now only governs the medium/large
            # severity band; SCRATCH01 (small) and SCRATCH04/05 (cluster/edge) route to
            # their own PASS/HITL policies instead (agent/services/policy.py's
            # _matches_defect_code).
            "classified_defect_code": "SCRATCH02",
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
    assert {item.revision for item in review.citations} == {"2026.08.1", "2026.08.2", "2016", "2015"}
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


def test_document_review_blocks_expired_and_conflicting_revisions(test_database):
    catalog = PolicyCatalog(test_database)
    controlled_expired = catalog.create_source(
        {
            "id": "TEST-CONTROLLED-EXPIRED-001",
            "document_family": "IATF-16949",
            "revision": "2020",
            "section": "Khung quản lý chất lượng ngành ô tô",
            "document_status": "APPROVED",
            "authority": "CONTROLLED_POLICY",
            "title": "Test controlled/expired copy",
            "scope": "Test-only expired controlled reference.",
            "url": "https://example.invalid/iatf-2020",
            "effective_date": "2020-01-01",
            "expiry_date": "2020-12-31",
        }
    )
    controlled_conflicting = catalog.create_source(
        {
            "id": "TEST-CONTROLLED-CONFLICT-001",
            "document_family": "IATF-16949",
            "revision": "2024",
            "section": "Khung quản lý chất lượng ngành ô tô",
            "document_status": "APPROVED",
            "authority": "CONTROLLED_POLICY",
            "title": "Test controlled/conflicting-revision copy",
            "scope": "Test-only conflicting-revision controlled reference.",
            "url": "https://example.invalid/iatf-2024",
            "effective_date": "2020-01-01",
            "expiry_date": None,
        }
    )
    catalog.update_policy(
        "FNS-SURFACE-001",
        {"source_ids": [controlled_expired["id"], controlled_conflicting["id"]]},
    )

    decision = catalog.evaluate(
        {
            "vehicle_model": "SUV_EV_2026",
            "defect_type": "scratch",
            "catalog_defect_type": "scratch",
            "classified_defect_code": "SCRATCH02",
        }
    )
    warning_codes = {item.code for item in decision.document_review.warnings}
    assert "DOCUMENT_EXPIRED" in warning_codes
    assert "REVISION_CONFLICT" in warning_codes
    assert decision.production_eligible is False


def _catalog_with_draft_policy(test_database: Database, defect_type: str) -> PolicyCatalog:
    catalog = PolicyCatalog(test_database)
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
    catalog.create_policy(draft_policy)
    # New policies always sort_order-append last (see Database.create_policy) -- force this
    # one ahead of every existing policy instead, so a naive "first match wins" lookup would
    # pick the DRAFT one if the approval gate (PolicyCatalog.is_approved) were missing. Only
    # reachable by going straight at the DB: PolicyCatalog's own API deliberately has no way
    # to insert at an arbitrary position.
    test_database.execute(
        "UPDATE policies SET sort_order = -1 WHERE id = :id", {"id": draft_policy["id"]}
    )
    catalog._reload()
    return catalog


def test_draft_policy_is_skipped_in_favor_of_an_approved_match(test_database):
    # scratch already has an APPROVED policy (FNS-SURFACE-001) -- the DRAFT one
    # must never win the match just by sorting first.
    catalog = _catalog_with_draft_policy(test_database, "scratch")
    decision = catalog.evaluate(
        {
            "defect_type": "scratch",
            "catalog_defect_type": "scratch",
            "classified_defect_code": "SCRATCH02",
            "vehicle_model": "unknown_model",
        }
    )
    assert decision.policy_id == "FNS-SURFACE-001"

    # Naming it explicitly (evaluate_named) is an internal/administrative lookup,
    # not the automatic per-defect routing path, so it is not gated the same way.
    named = catalog.evaluate_named(
        "FNS-DRAFT-TEST-001", {"defect_type": "scratch", "vehicle_model": "unknown_model"}
    )
    assert named.policy_id == "FNS-DRAFT-TEST-001"


def test_unclassified_finding_never_lets_policy_decide_from_raw_cv_label(test_database):
    # A raw CV label alone (no defect_catalog-confirmed defect_code yet) must never let
    # Policy infer an action_code/final_status -- even though "scratch" alone would match
    # FNS-SURFACE-001, evaluate() must fall through to the manual-reinspection fail-safe
    # because catalog_defect_type is absent (agent/services/policy.py's evaluate()).
    decision = PolicyCatalog(test_database).evaluate(
        {"defect_type": "scratch", "vehicle_model": "unknown_model"}
    )
    assert decision.policy_id == "FNS-MANUAL-001"
    assert decision.final_status == "FAIL"
    assert decision.human_required is True


def test_draft_policy_with_no_approved_alternative_falls_back_to_manual_reinspection(test_database):
    # A DRAFT policy (freshly saved from the Rules UI, or AI-extracted but not yet
    # reviewed) must not silently start deciding real vehicles -- with no other
    # approved policy for this defect type, routing must fall through to the
    # manual-reinspection fail-safe until a supervisor approves it.
    catalog = _catalog_with_draft_policy(test_database, "custom_test_defect")
    decision = catalog.evaluate(
        {
            "defect_type": "custom_test_defect",
            "catalog_defect_type": "custom_test_defect",
            "vehicle_model": "unknown_model",
        }
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
