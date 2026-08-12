from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ModelSettings:
    detector_provider: str
    model_path: Path
    model_device: str
    model_confidence: float
    model_image_size: int
    auto_pass_enabled: bool
    confirmed_threshold: float
    verify_threshold: float
    reasoning_provider: str
    groq_api_key: str | None
    groq_model: str

    @classmethod
    def from_env(cls) -> ModelSettings:
        configured_path = Path(os.getenv("MODEL_PATH", "./data/best.pt"))
        model_path = configured_path if configured_path.is_absolute() else PROJECT_ROOT / configured_path
        return cls(
            detector_provider=os.getenv("DETECTOR_PROVIDER", "local_yolo").strip().lower(),
            model_path=model_path.resolve(),
            model_device=os.getenv("MODEL_DEVICE", "cpu").strip(),
            model_confidence=float(os.getenv("MODEL_CONFIDENCE", "0.25")),
            model_image_size=int(os.getenv("MODEL_IMAGE_SIZE", "1280")),
            auto_pass_enabled=_env_bool("AUTO_PASS_ENABLED", False),
            confirmed_threshold=float(os.getenv("CONFIRMED_THRESHOLD", "0.70")),
            verify_threshold=float(os.getenv("VERIFY_THRESHOLD", "0.40")),
            reasoning_provider=os.getenv("QC_REASONING_PROVIDER", "deterministic").strip().lower(),
            groq_api_key=os.getenv("GROQ_API_KEY") or None,
            groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
        )


@dataclass(frozen=True)
class AuditExportSettings:
    enabled: bool
    directory: Path

    @classmethod
    def from_env(cls) -> AuditExportSettings:
        configured_path = Path(os.getenv("AUDIT_EXPORT_DIR", "./data/exports"))
        directory = configured_path if configured_path.is_absolute() else PROJECT_ROOT / configured_path
        return cls(
            enabled=_env_bool("AUDIT_AUTO_EXPORT_ENABLED", True),
            directory=directory.resolve(),
        )
