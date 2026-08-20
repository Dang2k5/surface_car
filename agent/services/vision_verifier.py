from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel

from agent.graph.state import QCState
from agent.services.image_source import primary_image_source, resolve_local_path

logger = logging.getLogger(__name__)

_IMAGE_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class VisualAssessment(BaseModel):
    """source = multimodal_llm — visual cross-check, not ground truth. See API_CONTRACT.md §3."""

    visual_verification: Literal["SUPPORTED", "CONFLICT", "UNCERTAIN"]
    shape_pattern: str | None = None
    continuity: str | None = None
    distribution: str | None = None
    visibility: str | None = None
    possible_artifact: str | None = None
    visual_uncertainty: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
    description: str | None = None
    provider: str = "groq"
    model: str = ""


class VisionUnavailableError(RuntimeError):
    """Raised when the configured Vision LLM cannot produce a validated assessment."""


class VisionVerifierService(Protocol):
    def verify_visual(self, state: QCState) -> VisualAssessment | None: ...

    def runtime_status(self) -> dict[str, object]: ...


class NoopVisionVerifier:
    """Default when VISION_LLM_PROVIDER is unset — no fabricated visual assessment."""

    def verify_visual(self, state: QCState) -> VisualAssessment | None:
        return None

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "NOT_CONFIGURED",
            "provider": None,
            "configured": False,
            "llm_accessed": False,
            "last_call_status": "NOT_APPLICABLE",
            "last_success_at": None,
            "last_error": None,
        }


class UnavailableVisionVerifier:
    """Fail-closed service used when VISION_LLM_PROVIDER is set without a usable model/key."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def verify_visual(self, state: QCState) -> VisualAssessment | None:
        raise VisionUnavailableError(self.reason)

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "VISION_LLM_REQUIRED",
            "provider": "groq",
            "configured": False,
            "llm_accessed": False,
            "last_call_status": "UNAVAILABLE",
            "last_success_at": None,
            "last_error": self.reason,
        }


class MockVisionVerifier:
    """Deterministic test double keyed off state['mock_vision_scenario']."""

    _SCENARIOS: dict[str, VisualAssessment] = {
        "supported": VisualAssessment(
            visual_verification="SUPPORTED",
            shape_pattern="thin_linear",
            continuity="continuous",
            distribution="localized",
            visibility="clear",
            possible_artifact="none",
            visual_uncertainty="LOW",
            description="Mock: evidence supports the YOLO detection.",
            provider="mock",
            model="mock-vision-v1",
        ),
        "conflict": VisualAssessment(
            visual_verification="CONFLICT",
            possible_artifact="reflection",
            visual_uncertainty="MEDIUM",
            description="Mock: visual evidence conflicts with the YOLO detection.",
            provider="mock",
            model="mock-vision-v1",
        ),
        "uncertain_high": VisualAssessment(
            visual_verification="UNCERTAIN",
            possible_artifact="shadow",
            visual_uncertainty="HIGH",
            description="Mock: visual uncertainty is high.",
            provider="mock",
            model="mock-vision-v1",
        ),
    }

    def verify_visual(self, state: QCState) -> VisualAssessment | None:
        scenario = state.get("mock_vision_scenario") or "supported"
        if scenario == "unavailable":
            raise VisionUnavailableError("MOCK_VISION_UNAVAILABLE")
        return self._SCENARIOS.get(scenario, self._SCENARIOS["supported"])

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "MOCK",
            "provider": "mock",
            "configured": True,
            "llm_accessed": True,
            "last_call_status": "NOT_APPLICABLE",
            "last_success_at": None,
            "last_error": None,
        }


class GroqVisionVerifierService:
    """Sends real image evidence to a Groq multimodal (image-input) model."""

    def __init__(self, *, api_key: str, model: str) -> None:
        from groq import Groq

        self.client = Groq(api_key=api_key)
        self.model = model
        self.last_call_status = "NOT_CALLED"
        self.last_success_at: str | None = None
        self.last_error: str | None = None

    def runtime_status(self) -> dict[str, object]:
        return {
            "mode": "VISION_LLM_AGENT",
            "provider": "groq",
            "model": self.model,
            "configured": True,
            "llm_accessed": self.last_success_at is not None,
            "last_call_status": self.last_call_status,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
        }

    def _mark_success(self) -> None:
        self.last_call_status = "SUCCESS"
        self.last_success_at = datetime.now(UTC).isoformat()
        self.last_error = None

    def _mark_failure(self, error: Exception) -> None:
        self.last_call_status = "FAILED_REQUIRES_HITL"
        self.last_error = type(error).__name__

    def _load_image_data_uri(self, state: QCState) -> str:
        source = primary_image_source(state)
        local_path = resolve_local_path(source)
        if local_path is None or not local_path.is_file():
            raise VisionUnavailableError("VISION_LLM_IMAGE_SOURCE_UNAVAILABLE")
        mime = _IMAGE_MIME_BY_SUFFIX.get(local_path.suffix.lower(), "image/jpeg")
        encoded = base64.b64encode(local_path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    def verify_visual(self, state: QCState) -> VisualAssessment | None:
        try:
            image_data_uri = self._load_image_data_uri(state)
        except VisionUnavailableError:
            raise
        except Exception as exc:  # pragma: no cover - filesystem edge cases
            self._mark_failure(exc)
            raise VisionUnavailableError(type(exc).__name__) from exc

        evidence = {
            "defect_type": state.get("defect_type"),
            "confidence": state.get("confidence"),
            "bbox": state.get("bbox"),
            "zone_name": state.get("zone_name"),
            "camera_id": state.get("camera_id"),
        }
        instructions = (
            "You are a visual cross-check for an automotive QC computer-vision "
            "pipeline. You receive the original station image and a prior YOLO "
            "detection (class, confidence, bbox) as context. Assess ONLY what is "
            "visually observable in the image. Do not estimate physical size, "
            "depth, tolerance, material, or a PASS/FAIL decision — those come from "
            "other controlled sources. Return only the requested JSON schema."
        )
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[
                    {"role": "system", "content": instructions},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "YOLO detection context (JSON): "
                                    + json.dumps(evidence, ensure_ascii=False)
                                    + ". Verify whether the image visually supports this "
                                    "detection, describe the observed region, and flag "
                                    "any non-defect visual artifact (reflection, shadow, "
                                    "dirt) you suspect."
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": image_data_uri}},
                        ],
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "visual_assessment",
                        "strict": False,
                        "schema": VisualAssessment.model_json_schema(),
                    },
                },
            )
            content = completion.choices[0].message.content or "{}"
            assessment = VisualAssessment.model_validate_json(content)
            self._mark_success()
            return assessment.model_copy(update={"provider": "groq", "model": self.model})
        except Exception as exc:
            self._mark_failure(exc)
            logger.warning("Groq vision verification failed; HITL is required: %s", exc)
            raise VisionUnavailableError(type(exc).__name__) from exc
