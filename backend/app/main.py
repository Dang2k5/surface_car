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
from agent.services.detector import MockDetector
from agent.services.repository import SQLiteQCRepository
from agent.services.verifier import MockVerifier, ModelVerifier
from agent.services.yolo_detector import LocalYoloSegmentationDetector

from .config import ModelSettings
from .database import DEFAULT_DATABASE_URL, SQLiteDatabase
from .langgraph_api import router as langgraph_router
from .quality_alerts_api import router as quality_alerts_router

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


def get_database_url() -> str:
    """Return a SQLite URL for the current baseline checkpoint.

    PostgreSQL is a future checkpoint. A legacy template value must not be
    interpreted as a Windows file path or prevent the local runtime from booting.
    """
    configured_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    if configured_url == ":memory:" or configured_url.startswith("sqlite:///"):
        return configured_url
    logger.warning(
        "DATABASE_URL uses an unsupported driver for the SQLite baseline backend; "
        "falling back to %s",
        DEFAULT_DATABASE_URL,
    )
    return DEFAULT_DATABASE_URL


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database = SQLiteDatabase(get_database_url())
    app.state.qc_checkpointer = InMemorySaver()
    app.state.qc_repository = SQLiteQCRepository(app.state.database)
    app.state.model_settings = ModelSettings.from_env()
    if app.state.model_settings.detector_provider == "local_yolo":
        app.state.qc_detector = LocalYoloSegmentationDetector(
            app.state.model_settings.model_path,
            device=app.state.model_settings.model_device,
            confidence=app.state.model_settings.model_confidence,
            image_size=app.state.model_settings.model_image_size,
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
        repository=app.state.qc_repository,
        checkpointer=app.state.qc_checkpointer,
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
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(langgraph_router)
app.include_router(quality_alerts_router)

upload_image_directory = Path(__file__).resolve().parents[2] / "data" / "uploads"
upload_image_directory.mkdir(parents=True, exist_ok=True)
app.mount("/assets/uploads", StaticFiles(directory=upload_image_directory), name="uploaded-images")


@app.get("/health")
def health() -> dict[str, str]:
    provider = getattr(getattr(app.state, "model_settings", None), "detector_provider", "starting")
    return {"status": "ok", "service": "backend", "mode": provider}
