from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from agent.services.policy import PolicyCatalog
from backend.app.main import app


def test_create_source_registers_a_new_document_and_rejects_duplicates(tmp_path):
    # Exercises PolicyCatalog directly against a throwaway copy of the catalog file --
    # never through the live app, which is wired to the real, git-tracked
    # agent/policies/qc_policy_catalog.json (see test_document_review_blocks_expired_and_conflicting_revisions
    # in test_policy_reasoning.py for the same isolation pattern).
    source_document = PolicyCatalog().public_catalog()
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(source_document), encoding="utf-8")
    catalog = PolicyCatalog(path)

    new_source = {
        "id": "FNS-WI-BODY-COSMETIC-001",
        "document_family": "FNS-WI",
        "revision": "01",
        "section": "Toàn bộ tài liệu",
        "document_status": "DRAFT",
        "authority": "REFERENCE",
        "title": "Tiêu chí kiểm tra ngoại quan thân vỏ ô tô",
        "scope": "Xước và móp",
        "url": "/assets/objects/policy-sources/abc/FNS-WI-BODY-COSMETIC-001.pdf",
    }
    created = catalog.create_source(new_source)
    assert created["id"] == "FNS-WI-BODY-COSMETIC-001"
    assert "FNS-WI-BODY-COSMETIC-001" in catalog.sources
    # Persisted to disk, and reloadable.
    reloaded = PolicyCatalog(path)
    assert "FNS-WI-BODY-COSMETIC-001" in reloaded.sources

    with pytest.raises(ValueError, match="already exists"):
        catalog.create_source(new_source)


@pytest.fixture(autouse=True)
def _dev_role_bypass(monkeypatch):
    """X-Dev-Role only takes effect when Supabase JWT verification is unconfigured
    (backend/app/auth.py get_current_user) -- clear both env vars that gate it so
    these tests can simulate QC_OPERATOR/QC_SUPERVISOR without a real Supabase token."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)


@pytest.mark.asyncio
async def test_extract_policy_draft_requires_qc_supervisor_role():
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/policies/extract",
                headers={"X-Dev-Role": "QC_OPERATOR"},
                files={"file": ("wi.txt", b"Vet xuoc tren be mat than vo, nguong do 50mm.", "text/plain")},
            )
            assert response.status_code == 403


@pytest.mark.asyncio
async def test_extract_policy_draft_returns_reviewable_draft():
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            document_text = (
                "FNS WORK INSTRUCTION\n"
                "Tieu chi kiem tra loi xuoc (scratch) tren than vo o to.\n"
                "Vet xuoc <= 50mm: FAIL, chuyen danh gia be mat.\n"
            ).encode("utf-8")
            response = await client.post(
                "/api/policies/extract",
                headers={"X-Dev-Role": "QC_SUPERVISOR"},
                files={"file": ("FNS-WI-BODY-COSMETIC-001.txt", document_text, "text/plain")},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["policy_draft"]["defect_types"] == ["scratch"]
            assert body["policy_draft"]["suggested_id"]
            assert body["source_draft"]["title"] == "FNS-WI-BODY-COSMETIC-001.txt"
            # Nothing is written to object storage at extract time -- only when the
            # supervisor actually saves via POST /api/policies/sources (see below).
            assert "url" not in body["source_draft"]
            assert body["provider"] == "deterministic"


@pytest.mark.asyncio
async def test_extract_policy_draft_rejects_empty_document():
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/policies/extract",
                headers={"X-Dev-Role": "QC_SUPERVISOR"},
                files={"file": ("empty.txt", b"short", "text/plain")},
            )
            assert response.status_code == 422


def _source_form_fields(source_id: str) -> dict[str, str]:
    return {
        "id": source_id,
        "document_family": "FNS-WI",
        "revision": "01",
        "section": "Toàn bộ tài liệu",
        "title": "Tiêu chí kiểm tra ngoại quan thân vỏ ô tô",
        "scope": "Xước và móp",
        "document_status": "DRAFT",
        "authority": "REFERENCE",
    }


@pytest.mark.asyncio
async def test_create_source_requires_qc_supervisor_role(tmp_path):
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        # Swap in a throwaway catalog copy so this test never writes to the real,
        # git-tracked agent/policies/qc_policy_catalog.json (same isolation as
        # test_create_source_registers_a_new_document_and_rejects_duplicates above).
        real_catalog = app.state.qc_policy_catalog
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps(real_catalog.public_catalog()), encoding="utf-8")
        app.state.qc_policy_catalog = PolicyCatalog(path)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/policies/sources",
                    headers={"X-Dev-Role": "QC_OPERATOR"},
                    data=_source_form_fields("FNS-WI-ROLE-TEST-001"),
                    files={"file": ("wi.txt", b"content", "text/plain")},
                )
                assert response.status_code == 403
        finally:
            app.state.qc_policy_catalog = real_catalog


@pytest.mark.asyncio
async def test_create_source_writes_file_only_on_save_and_rejects_duplicate_id(tmp_path):
    # This is the endpoint that actually writes to object storage -- POST
    # /api/policies/extract (above) never does, so a supervisor who only extracts
    # and never saves leaves nothing behind to clean up.
    transport = ASGITransport(app=app)
    source_id = "FNS-WI-SAVE-TEST-001"
    async with app.router.lifespan_context(app):
        real_catalog = app.state.qc_policy_catalog
        path = tmp_path / "catalog.json"
        path.write_text(json.dumps(real_catalog.public_catalog()), encoding="utf-8")
        app.state.qc_policy_catalog = PolicyCatalog(path)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/policies/sources",
                    headers={"X-Dev-Role": "QC_SUPERVISOR"},
                    data=_source_form_fields(source_id),
                    files={"file": ("wi.txt", b"noi dung tai lieu", "text/plain")},
                )
                assert response.status_code == 201
                body = response.json()
                assert body["id"] == source_id
                assert body["url"].startswith("/assets/objects/policy-sources/")

                duplicate = await client.post(
                    "/api/policies/sources",
                    headers={"X-Dev-Role": "QC_SUPERVISOR"},
                    data=_source_form_fields(source_id),
                    files={"file": ("wi.txt", b"noi dung khac", "text/plain")},
                )
                assert duplicate.status_code == 409
        finally:
            app.state.qc_policy_catalog = real_catalog
