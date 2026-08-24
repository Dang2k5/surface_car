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
    fixed_camera_calibration_enabled: bool
    calibration_mm_per_pixel_x: float
    calibration_mm_per_pixel_y: float
    calibration_profile_id: str
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
            model_image_size=int(os.getenv("MODEL_IMAGE_SIZE", "640")),
            fixed_camera_calibration_enabled=_env_bool(
                "FIXED_CAMERA_CALIBRATION_ENABLED", True
            ),
            calibration_mm_per_pixel_x=float(
                os.getenv("CALIBRATION_MM_PER_PIXEL_X", "0.8")
            ),
            calibration_mm_per_pixel_y=float(
                os.getenv("CALIBRATION_MM_PER_PIXEL_Y", "0.8")
            ),
            calibration_profile_id=os.getenv(
                "CALIBRATION_PROFILE_ID", "FNS_FRONT_PILOT_1280"
            ).strip(),
            auto_pass_enabled=_env_bool("AUTO_PASS_ENABLED", True),
            confirmed_threshold=float(os.getenv("CONFIRMED_THRESHOLD", "0.70")),
            verify_threshold=float(os.getenv("VERIFY_THRESHOLD", "0.40")),
            reasoning_provider=os.getenv("QC_REASONING_PROVIDER", "groq").strip().lower(),
            groq_api_key=os.getenv("GROQ_API_KEY") or None,
            groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip(),
        )


@dataclass(frozen=True)
class AuthSettings:
    supabase_url: str | None
    supabase_jwt_secret: str | None
    default_qc_role: str

    @property
    def jwks_url(self) -> str | None:
        """Supabase's per-project JWKS endpoint, used to verify tokens signed with an
        asymmetric key (ES256/RS256) — the default for projects on Supabase's newer API-key
        system, which has no shared HS256 secret (see SUPABASE_JWT_SECRET below)."""
        if not self.supabase_url:
            return None
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @classmethod
    def from_env(cls) -> AuthSettings:
        return cls(
            supabase_url=os.getenv("SUPABASE_URL") or None,
            supabase_jwt_secret=os.getenv("SUPABASE_JWT_SECRET") or None,
            default_qc_role=os.getenv("DEFAULT_QC_ROLE", "QC_OPERATOR").strip(),
        )


@dataclass(frozen=True)
class ObjectStorageSettings:
    provider: str
    endpoint: str | None
    bucket: str
    access_key: str | None
    secret_key: str | None
    region: str | None

    @classmethod
    def from_env(cls) -> ObjectStorageSettings:
        return cls(
            provider=os.getenv("OBJECT_STORAGE_PROVIDER", "s3").strip().lower(),
            endpoint=os.getenv("S3_ENDPOINT") or None,
            bucket=os.getenv("S3_BUCKET", "visual-qc").strip(),
            access_key=os.getenv("S3_ACCESS_KEY") or None,
            secret_key=os.getenv("S3_SECRET_KEY") or None,
            region=os.getenv("S3_REGION") or None,
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
