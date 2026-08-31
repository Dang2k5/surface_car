from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from jwt import PyJWKClient
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from agent.graph.builder import build_qc_graph
from agent.services.audit_export import JsonAuditExporter
from agent.services.defect_catalog import DatabaseDefectCatalog
from agent.services.object_storage import LocalDiskObjectStorage, ObjectStorageService, S3ObjectStorage
from agent.services.policy import PolicyCatalog
from agent.services.reasoning import (
    DeterministicReasoningService,
    GroqReasoningService,
    UnavailableReasoningService,
)
from agent.services.repository import PostgresQCRepository
from agent.services.verifier import ModelVerifier
from agent.services.yolo_detector import LocalYoloSegmentationDetector

from .auth_api import router as auth_router
from .catalog_api import router as catalog_router
from .config import AuditExportSettings, AuthSettings, ModelSettings, ObjectStorageSettings
from .database import Database, normalize_database_url
from .hitl_alerts import HitlRateAlertService
from .hitl_alerts_api import router as hitl_alerts_router
from .langgraph_api import router as langgraph_router
from .objects_api import router as objects_router
from .policy_api import router as policy_router
from .policy_extract_api import router as policy_extract_router
from .qc_api import router as qc_router
from .quality_alerts_api import router as quality_alerts_router
from .trend_api import router as trend_router
from .v1_api import router as v1_router

load_dotenv()
logger = logging.getLogger(__name__)


def configure_optional_langsmith_tracing() -> None:
    """Keep local inference offline unless LangSmith is explicitly enabled."""
    enabled = os.getenv("ENABLE_LANGSMITH_TRACING", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"


configure_optional_langsmith_tracing()


def get_cors_origins() -> list[str]:
    configured = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [item.strip().rstrip("/") for item in configured.split(",") if item.strip()]
    # Keep local fallback ports available during development, while production
    # deployments can still provide an explicit allow-list through the env.
    if os.getenv("APP_ENV", "development").strip().lower() == "development":
        origins.extend(
            [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3001",
            ]
        )
    return list(dict.fromkeys(origins))


def get_database_url() -> str:
    """Return the configured PostgreSQL connection URL, or fail loudly if missing/invalid."""
    configured_url = os.getenv("DATABASE_URL", "").strip()
    if not configured_url:
        raise RuntimeError(
            "DATABASE_URL is not set; a PostgreSQL/Supabase connection string is required "
            "(see docs/ENVIRONMENT.md)"
        )
    supported_prefixes = ("postgres://", "postgresql://", "postgresql+psycopg://")
    if not configured_url.startswith(supported_prefixes):
        raise RuntimeError(
            f"DATABASE_URL must be a PostgreSQL connection string, got: {configured_url!r}"
        )
    return configured_url


def get_database_schema() -> str | None:
    """Optional PostgreSQL schema override (tests isolate each run in a throwaway
    schema on the same Supabase project as production; see tests/conftest.py)."""
    return os.getenv("DATABASE_SCHEMA", "").strip() or None


def _build_object_storage(
    settings: ObjectStorageSettings, local_root: Path
) -> ObjectStorageService:
    """Build the configured object storage backend, never crashing startup.

    Mirrors the Noop/dev-bypass convention used by every other optional
    integration in this backend: an unreachable or unconfigured S3 falls
    back to local disk instead of blocking the whole app from starting
    (ENVIRONMENT.md Object Storage).
    """
    if settings.provider == "s3" and settings.access_key and settings.secret_key:
        try:
            return S3ObjectStorage(
                provider=settings.provider,
                bucket=settings.bucket,
                endpoint=settings.endpoint,
                access_key=settings.access_key,
                secret_key=settings.secret_key,
                region=settings.region,
            )
        except Exception:
            logger.warning(
                "OBJECT_STORAGE_PROVIDER=%s configured but unreachable at startup; "
                "falling back to local disk storage (dev/demo only)",
                settings.provider,
                exc_info=True,
            )
            return LocalDiskObjectStorage(local_root)
    logger.warning(
        "S3_ACCESS_KEY/S3_SECRET_KEY not configured; using local disk object "
        "storage (dev/demo only, ENVIRONMENT.md Object Storage)"
    )
    return LocalDiskObjectStorage(local_root)


def _build_qc_checkpointer(database_url: str, schema: str | None) -> tuple[Any, Any]:
    """Build the LangGraph checkpointer on the same Postgres database as DATABASE_URL.

    A checkpointer less durable/shared than app.state.qc_repository (agent_graph_runs)
    orphans the HITL queue: the repository keeps listing an interrupted run as pending,
    but the checkpoint needed to actually resume it lives somewhere the next request
    can't see (in-memory, wiped by any restart) -- resuming then 404s "LangGraph thread
    not found" while the queue still shows the case as waiting. Backing both by the same
    Postgres database (and schema) keeps them consistent.

    Backed by a ConnectionPool (not a single long-lived connection, as this used to do):
    video inspections run long (multiple uploads + sequential inference), and Supabase's
    pooler/idle timeout can silently drop a connection held open for the app's whole
    lifetime. A single dead connection then fails every subsequent request with
    psycopg.OperationalError("the connection is closed") until the process restarts. The
    pool checks each connection out fresh and reconnects dead ones automatically, mirroring
    the pool_pre_ping=True protection backend/app/database.py already gives the main DB.
    """
    normalized = normalize_database_url(database_url)
    pg_url = "postgresql://" + normalized.removeprefix("postgresql+psycopg://")
    connect_kwargs: dict[str, Any] = {}
    if schema:
        connect_kwargs["options"] = f"-c search_path={schema}"
    pool = ConnectionPool(
        pg_url,
        min_size=1,
        max_size=5,
        kwargs={
            # None disables server-side prepared statements outright (0 merely
            # prepares on first use, which still breaks under the transaction-mode
            # pooler -- see backend/app/database.py's matching connect_args).
            "autocommit": True,
            "prepare_threshold": None,
            "row_factory": dict_row,
            **connect_kwargs,
        },
        check=ConnectionPool.check_connection,
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return checkpointer, pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database = Database(get_database_url(), schema=get_database_schema())
    app.state.object_storage_settings = ObjectStorageSettings.from_env()
    app.state.object_storage = _build_object_storage(
        app.state.object_storage_settings, upload_image_directory
    )
    app.state.auth_settings = AuthSettings.from_env()
    # Supabase's newer API-key-system projects don't expose a shared HS256 secret at all —
    # SUPABASE_URL (+ its JWKS endpoint) is required to verify their ES256/RS256-signed tokens.
    app.state.supabase_jwks_client = (
        PyJWKClient(app.state.auth_settings.jwks_url, cache_keys=True)
        if app.state.auth_settings.jwks_url
        else None
    )
    if not app.state.auth_settings.supabase_jwt_secret and not app.state.supabase_jwks_client:
        logger.warning(
            "Neither SUPABASE_JWT_SECRET nor SUPABASE_URL is set; RBAC enforcement is "
            "disabled and all write endpoints accept unauthenticated requests (ENVIRONMENT.md)"
        )
    app.state.qc_checkpointer, app.state.qc_checkpointer_conn = _build_qc_checkpointer(
        get_database_url(), get_database_schema()
    )
    app.state.audit_export_settings = AuditExportSettings.from_env()
    app.state.qc_audit_exporter = JsonAuditExporter(
        app.state.audit_export_settings.directory,
        enabled=app.state.audit_export_settings.enabled,
    )
    app.state.qc_repository = PostgresQCRepository(
        app.state.database,
        audit_exporter=app.state.qc_audit_exporter,
    )
    app.state.qc_defect_catalog = DatabaseDefectCatalog(app.state.database)
    app.state.hitl_alert_service = HitlRateAlertService(app.state.database)
    app.state.model_settings = ModelSettings.from_env()
    app.state.reasoning_requested_provider = app.state.model_settings.reasoning_provider
    app.state.reasoning_key_configured = bool(app.state.model_settings.groq_api_key)
    app.state.qc_policy_catalog = PolicyCatalog()
    if app.state.model_settings.reasoning_provider == "groq" and app.state.model_settings.groq_api_key:
        app.state.qc_reasoning = GroqReasoningService(
            api_key=app.state.model_settings.groq_api_key,
            model=app.state.model_settings.groq_model,
        )
    elif app.state.model_settings.reasoning_provider == "groq":
        logger.warning("QC_REASONING_PROVIDER=groq but GROQ_API_KEY is missing; LLM decisions require HITL")
        app.state.qc_reasoning = UnavailableReasoningService("GROQ_API_KEY_MISSING")
    else:
        # Deterministic mode is retained for automated tests and explicit offline diagnostics.
        app.state.qc_reasoning = DeterministicReasoningService()
    if app.state.model_settings.detector_provider != "local_yolo":
        raise RuntimeError(
            f"Unsupported DETECTOR_PROVIDER={app.state.model_settings.detector_provider!r}; "
            "only 'local_yolo' is supported"
        )
    app.state.qc_detector = LocalYoloSegmentationDetector(
        app.state.model_settings.model_path,
        device=app.state.model_settings.model_device,
        confidence=app.state.model_settings.model_confidence,
        image_size=app.state.model_settings.model_image_size,
        fixed_calibration_enabled=(
            app.state.model_settings.fixed_camera_calibration_enabled
        ),
        mm_per_pixel_x=app.state.model_settings.calibration_mm_per_pixel_x,
        mm_per_pixel_y=app.state.model_settings.calibration_mm_per_pixel_y,
        calibration_profile_id=app.state.model_settings.calibration_profile_id,
        marker_calibration_enabled=app.state.model_settings.marker_calibration_enabled,
        marker_size_mm=app.state.model_settings.marker_size_mm,
        marker_dictionary=app.state.model_settings.marker_dictionary,
    )
    app.state.qc_verifier = ModelVerifier(
        app.state.qc_detector,
        min_confidence=app.state.model_settings.verify_threshold,
    )
    app.state.qc_langgraph = build_qc_graph(
        detector=app.state.qc_detector,
        verifier=app.state.qc_verifier,
        reasoning=app.state.qc_reasoning,
        policy_catalog=app.state.qc_policy_catalog,
        repository=app.state.qc_repository,
        checkpointer=app.state.qc_checkpointer,
        defect_catalog=app.state.qc_defect_catalog,
    )
    yield
    app.state.database.close()
    app.state.qc_checkpointer_conn.close()


app = FastAPI(
    title="Visual QC Agent Backend",
    description="Model-backed API for FNS vehicle quality inspections.",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(objects_router)
app.include_router(langgraph_router)
app.include_router(quality_alerts_router)
app.include_router(hitl_alerts_router)
app.include_router(policy_router)
app.include_router(policy_extract_router)
app.include_router(qc_router)
app.include_router(trend_router)
app.include_router(v1_router)

upload_image_directory = Path(__file__).resolve().parents[2] / "data" / "uploads"
upload_image_directory.mkdir(parents=True, exist_ok=True)
app.mount("/assets/uploads", StaticFiles(directory=upload_image_directory), name="uploaded-images")


def _reasoning_runtime_status() -> dict[str, object]:
    service = getattr(app.state, "qc_reasoning", None)
    status = service.runtime_status() if service and hasattr(service, "runtime_status") else {}
    return {
        **status,
        "requested_provider": getattr(app.state, "reasoning_requested_provider", "starting"),
        "api_key_configured": getattr(app.state, "reasoning_key_configured", False),
    }


def _object_storage_runtime_status() -> dict[str, object]:
    service = getattr(app.state, "object_storage", None)
    return service.runtime_status() if service and hasattr(service, "runtime_status") else {}


def _vision_runtime_status() -> dict[str, object]:
    settings = getattr(app.state, "model_settings", None)
    provider = getattr(settings, "detector_provider", None)
    detector = getattr(app.state, "qc_detector", None)
    return {
        "mode": provider or "starting",
        "provider": provider,
        "configured": detector is not None,
    }


@app.get("/health")
def health() -> dict[str, object]:
    provider = getattr(getattr(app.state, "model_settings", None), "detector_provider", "starting")
    return {
        "status": "ok",
        "service": "backend",
        "mode": provider,
        "reasoning": _reasoning_runtime_status(),
    }


@app.get("/agent/status")
def agent_status() -> dict[str, object]:
    """Expose whether the LLM Agent is available and has produced a decision."""
    return {
        "langgraph": "READY",
        "checkpointer": type(getattr(app.state, "qc_checkpointer", None)).__name__,
        "reasoning": _reasoning_runtime_status(),
        "vision": _vision_runtime_status(),
        "object_storage": _object_storage_runtime_status(),
    }
