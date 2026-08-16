from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import InMemorySaver

from agent.graph.builder import build_qc_graph
from agent.services.audit_export import JsonAuditExporter
from agent.services.defect_catalog import DatabaseDefectCatalog
from agent.services.detector import MockDetector
from agent.services.policy import PolicyCatalog
from agent.services.reasoning import DeterministicReasoningService, GroqReasoningService
from agent.services.repository import SQLiteQCRepository
from agent.services.verifier import MockVerifier, ModelVerifier
from agent.services.yolo_detector import LocalYoloSegmentationDetector

from .config import AuditExportSettings, ModelSettings
from .database import DEFAULT_DATABASE_URL, Database
from .langgraph_api import router as langgraph_router
from .policy_api import router as policy_router
from .qc_api import router as qc_router
from .quality_alerts_api import router as quality_alerts_router
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
    """Return the configured SQLite or PostgreSQL connection URL."""
    configured_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    supported_prefixes = (
        "sqlite:///",
        "sqlite+pysqlite:///",
        "postgres://",
        "postgresql://",
        "postgresql+psycopg://",
    )
    if configured_url == ":memory:" or configured_url.startswith(supported_prefixes):
        return configured_url
    logger.warning(
        "DATABASE_URL uses an unsupported driver; "
        "falling back to %s",
        DEFAULT_DATABASE_URL,
    )
    return DEFAULT_DATABASE_URL


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database = Database(get_database_url())
    app.state.qc_checkpointer = InMemorySaver()
    app.state.audit_export_settings = AuditExportSettings.from_env()
    app.state.qc_audit_exporter = JsonAuditExporter(
        app.state.audit_export_settings.directory,
        enabled=app.state.audit_export_settings.enabled,
    )
    app.state.qc_repository = SQLiteQCRepository(
        app.state.database,
        audit_exporter=app.state.qc_audit_exporter,
    )
    app.state.qc_defect_catalog = DatabaseDefectCatalog(app.state.database)
    app.state.model_settings = ModelSettings.from_env()
    app.state.reasoning_requested_provider = app.state.model_settings.reasoning_provider
    app.state.reasoning_key_configured = bool(app.state.model_settings.groq_api_key)
    app.state.qc_policy_catalog = PolicyCatalog()
    deterministic_reasoning = DeterministicReasoningService()
    if app.state.model_settings.reasoning_provider == "groq" and app.state.model_settings.groq_api_key:
        app.state.qc_reasoning = GroqReasoningService(
            api_key=app.state.model_settings.groq_api_key,
            model=app.state.model_settings.groq_model,
            fallback=deterministic_reasoning,
        )
    else:
        if app.state.model_settings.reasoning_provider == "groq":
            logger.warning("QC_REASONING_PROVIDER=groq but GROQ_API_KEY is missing; using deterministic reasoning")
        app.state.qc_reasoning = deterministic_reasoning
    if app.state.model_settings.detector_provider == "local_yolo":
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
        )
        app.state.qc_verifier = ModelVerifier(
            app.state.qc_detector,
            min_confidence=app.state.model_settings.verify_threshold,
        )
    elif app.state.model_settings.detector_provider == "mock":
        app.state.qc_detector = MockDetector()
        app.state.qc_verifier = MockVerifier()
    else:
        raise RuntimeError(
            f"Unsupported DETECTOR_PROVIDER={app.state.model_settings.detector_provider!r}"
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
app.include_router(langgraph_router)
app.include_router(quality_alerts_router)
app.include_router(policy_router)
app.include_router(qc_router)
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
    """Expose whether reasoning came from Groq or the local safety fallback."""
    return {
        "langgraph": "READY",
        "checkpointer": type(getattr(app.state, "qc_checkpointer", None)).__name__,
        "reasoning": _reasoning_runtime_status(),
    }
