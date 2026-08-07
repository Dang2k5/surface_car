from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import SQLiteDatabase
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database = SQLiteDatabase()
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "backend", "mode": "mock"}
