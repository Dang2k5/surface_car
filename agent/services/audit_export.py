from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def build_audit_export(state: dict[str, Any]) -> dict[str, Any]:
    """Build a portable audit package without workstation-local file paths."""
    final_status = state.get("final_status", "UNKNOWN")
    return {
        "schema": "visual-qc-agent-audit/v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "identity": {
            "thread_id": state.get("thread_id"),
            "inspection_id": state.get("inspection_id"),
            "vehicle_id": state.get("vehicle_id"),
            "vehicle_model": state.get("vehicle_model"),
            "status": final_status,
        },
        "evidence": {
            "image_url": state.get("image_url"),
            "image_sha256": state.get("image_sha256"),
            "camera_id": state.get("camera_id"),
            "camera_evidence": [
                {
                    "camera_id": item.get("camera_id"),
                    "image_url": item.get("image_url"),
                    "image_sha256": item.get("image_sha256"),
                }
                for item in state.get("camera_evidence", [])
            ],
            "zone_name": state.get("zone_name"),
        },
        "model_result": {
            "model_name": state.get("model_name"),
            "model_version": state.get("model_version"),
            "model_task": state.get("model_task"),
            "inference_ms": state.get("inference_ms"),
            "defect_detected": state.get("defect_detected"),
            "defect_type": state.get("defect_type"),
            "confidence": state.get("confidence"),
            "severity": state.get("severity"),
            "bbox": state.get("bbox"),
            "segmentation_result": state.get("segmentation_result"),
            "detections": state.get("detections", []),
            "enriched_defects": state.get("enriched_defects", []),
            "camera_results": state.get("camera_results", []),
            "finding_groups": state.get("finding_groups", []),
            "suggested_defect_codes": state.get("suggested_defect_codes", []),
            "classified_defect_code": state.get("classified_defect_code"),
            "defect_family": state.get("defect_family"),
            "defect_code_classification": state.get("defect_code_classification"),
            "similar_defect_warning": state.get("similar_defect_warning", False),
            "camera_classifications": state.get("camera_classifications", []),
            "affected_zones": state.get("affected_zones", []),
            "measurements": state.get("measurements", {}),
        },
        "workflow": {
            "assessment_route": state.get("assessment_route"),
            "camera_policy_decisions": state.get("camera_policy_decisions", []),
            "verify_count": state.get("verify_count", 0),
            "verify_result": state.get("verify_result"),
            "human_required": state.get("human_required", False),
            "hitl_status": state.get("hitl_status"),
            "human_decision": state.get("human_decision"),
            "qc_decision_record": state.get("qc_decision_record"),
            "execution_trace": state.get("execution_trace", []),
        },
        "outcome": {
            "decision": state.get("decision"),
            "recommendation_code": state.get("recommendation_code"),
            "recommendation": state.get("recommendation"),
            "allow_test_drive": state.get("allow_test_drive", False),
            "severity": state.get("severity"),
            "reason": state.get("reason"),
            "final_status": final_status,
        },
        "policy": state.get("policy_decision"),
        "reasoning": state.get("ai_analysis"),
        "agent_analysis": state.get("agent_analysis"),
    }


class JsonAuditExporter:
    """Write the latest state of each graph thread as an atomic JSON artifact."""

    def __init__(self, export_directory: Path, *, enabled: bool = True) -> None:
        self.export_directory = export_directory
        self.enabled = enabled

    def export(self, state: dict[str, Any]) -> Path | None:
        if not self.enabled:
            return None
        thread_id = str(state["thread_id"])
        destination = self.export_directory / f"visual-qc-inspection-{thread_id}.json"
        temporary = destination.with_suffix(".json.tmp")
        try:
            self.export_directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(build_audit_export(state), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(destination)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            logger.exception("Unable to auto-export audit JSON for thread %s", thread_id)
            return None
        return destination
