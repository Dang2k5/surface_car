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
from agent.services.repository import SQLiteQCRepository

from .database import DEFAULT_DATABASE_URL, SQLiteDatabase
from .langgraph_api import router as langgraph_router
from .routes import router

load_dotenv()
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Return a SQLite URL for the current mock-only checkpoint.

    PostgreSQL is a future checkpoint. A legacy template value must not be
    interpreted as a Windows file path or prevent the local demo from booting.
    """
    configured_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    if configured_url == ":memory:" or configured_url.startswith("sqlite:///"):
        return configured_url
    logger.warning(
        "DATABASE_URL uses an unsupported driver for the SQLite mock backend; "
        "falling back to %s",
        DEFAULT_DATABASE_URL,
    )
    return DEFAULT_DATABASE_URL


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database = SQLiteDatabase(get_database_url())
    app.state.qc_checkpointer = InMemorySaver()
    app.state.qc_repository = SQLiteQCRepository(app.state.database)
    app.state.qc_langgraph = build_qc_graph(
        repository=app.state.qc_repository,
        checkpointer=app.state.qc_checkpointer,
    )
    yield
    app.state.database.close()


app = FastAPI(
    title="Visual QC Agent Backend",
    description="Mock-first API for FNS vehicle quality inspections.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(langgraph_router)

train_image_directory = Path(__file__).resolve().parents[2] / "data" / "train"
if train_image_directory.is_dir():
    app.mount("/assets/train", StaticFiles(directory=train_image_directory), name="train-images")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend", "mode": "mock"}
