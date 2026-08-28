from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from agent.graph.state import QCState, TraceEvent
from agent.services.defect_catalog import DefectCatalogService
from agent.services.detector import DetectorService
from agent.services.policy import PolicyCatalog, PolicyDecision
from agent.services.reasoning import (
    DefectCodeClassification,
    ReasoningAnalysis,
    ReasoningService,
    ReasoningUnavailableError,
)
from agent.services.repository import QCRepository
from agent.services.verifier import VerifierService


def _trace(node: str, detail: str, status: str = "COMPLETED") -> list[TraceEvent]:
    return [{"node": node, "status": status, "detail": detail}]


# Static position labels for the 5 fixed camera mounts, mirroring the frontend's
# CAMERA_POSITION_LABELS (frontend/src/lib/detection-geometry.ts) — there's no backend camera
# catalog to derive this from, so the mount layout is duplicated here on purpose.
_CAMERA_ZONE_NAMES: dict[str, str] = {
    "CAM-01": "truoc",
    "CAM-02": "sau",
    "CAM-03": "trai",
    "CAM-04": "phai",
    "CAM-05": "tren_toan_canh",
}


def _detection_priority_key(item: dict[str, Any]) -> tuple[int, float, float]:
    """Mirrors yolo_detector.py's detection_priority_key (duplicated, not imported, to keep
    this module working against the DetectorService Protocol rather than the concrete YOLO
    implementation): class safety priority first, then estimated size, confidence last."""
    measurements = item.get("visual_measurements") or {}
    length_mm = float(measurements.get("estimated_length_mm") or 0.0)
    return (
        int(item.get("safety_priority", 0)),
        length_mm,
        float(item.get("confidence") or 0.0),
    )


_SEVERITY_LETTER_RANK = {"A": 3, "B": 2, "C": 1}


def _classification_rank(item: dict[str, Any]) -> tuple[int, float]:
    """Ranks a per-camera classification for "which camera's finding is worst" —
    used to pick the single decision that drives the LLM narrative once every camera's
    finding has already been independently classified and policy-evaluated."""
    measurements = item.get("visual_measurements") or {}
    length_mm = float(measurements.get("estimated_length_mm") or 0.0)
    return (_SEVERITY_LETTER_RANK.get(str(item.get("severity") or "").upper(), 0), length_mm)


def _zone_name_for_camera(camera_id: Any, fallback: str) -> str:
    """A caller never explicitly picks a zone in the upload form (there's no such field), so
    the request always arrives with the Pydantic default "unknown_zone" — derive a real zone
    from which camera mount actually saw the finding instead of leaving it unknown."""
    zone = _CAMERA_ZONE_NAMES.get(str(camera_id or "").strip().upper())
    return zone or fallback


class QCNodes:
    def __init__(
        self,
        detector: DetectorService,
        verifier: VerifierService,
        reasoning: ReasoningService,
        policy_catalog: PolicyCatalog,
        repository: QCRepository,
        defect_catalog: DefectCatalogService,
    ) -> None:
        self.detector = detector
        self.verifier = verifier
        self.reasoning = reasoning
        self.policy_catalog = policy_catalog
        self.repository = repository
        self.defect_catalog = defect_catalog

    def prepare_input(self, state: QCState) -> dict[str, Any]:
        camera_evidence = state.get("camera_evidence", [])
        image_paths = state.get("image_paths", [])
        image_url = state.get("image_url", "")
        if not camera_evidence and not image_url and not image_paths:
            raise ValueError("image_url or image_paths is required")
        return {
            "verify_count": 0,
            "verify_result": "NOT_RUN",
            "human_required": False,
            "human_decision": None,
            "retry_count": state.get("retry_count", 0),
            "max_retries": state.get("max_retries", 2),
            "error": None,
            "execution_trace": _trace(
                "prepare_input",
                f"Đã xác thực dữ liệu đầu vào cho {len(camera_evidence) or 1} camera.",
            ),
        }

    def _classify_local_detection(
        self, state: QCState, base_detection: dict[str, Any], local: dict[str, Any]
    ) -> dict[str, Any]:
        """Classify ONE camera's own worst finding against the defect catalog + LLM,
        independently of every other camera's finding. Called once per camera that has
        a detection (bounded by KNOWN_CAMERA_IDS, currently 5), so a defect on CAM-03
        is classified on its own merits instead of only ever being read off the single
        global-worst detection."""
        suggested_codes = self.defect_catalog.match(str(local.get("class_name") or "none"))
        overlay = {
            **state,
            **base_detection,
            "defect_type": local.get("class_name"),
            "confidence": local.get("confidence"),
            "bbox": local.get("bbox"),
            "segmentation_result": local.get("segmentation"),
            "visual_measurements": local.get("visual_measurements"),
            "camera_id": local.get("camera_id"),
        }
        try:
            classification = self.reasoning.classify_defect_code(overlay, suggested_codes)
            reasoning_status = "LLM_CLASSIFICATION_COMPLETED"
        except ReasoningUnavailableError as error:
            classification = DefectCodeClassification(
                defect_code=None,
                defect_family=None,
                confidence=0.0,
                rationale_vi="LLM Agent chưa thể phân loại; cần QC kiểm duyệt.",
                candidate_codes=[str(item.get("defect_code")) for item in suggested_codes],
                provider="groq",
                model="unavailable",
                fallback_reason=str(error),
            )
            reasoning_status = "LLM_UNAVAILABLE_REQUIRES_HITL"
        classified_record = next(
            (
                item
                for item in suggested_codes
                if item.get("defect_code") == classification.defect_code
            ),
            None,
        )
        return {
            "detection_id": local.get("detection_id"),
            "camera_id": local.get("camera_id"),
            "defect_type": local.get("class_name"),
            "confidence": local.get("confidence"),
            "bbox": local.get("bbox"),
            "visual_measurements": local.get("visual_measurements"),
            "suggested_defect_codes": suggested_codes,
            "defect_code_classification": classification.model_dump(mode="json"),
            "reasoning_status": reasoning_status,
            "classified_defect_code": classification.defect_code,
            "defect_family": classification.defect_family,
            "catalog_defect_type": classified_record.get("defect_type") if classified_record else None,
            "severity": (
                str(classified_record.get("default_severity") or "UNASSESSED")
                if classified_record
                else "UNASSESSED"
            ),
            "severity_source_id": classified_record.get("source_id") if classified_record else None,
            "similar_defect_warning": classification.similar_observation_warning,
        }

    def detect_defect(self, state: QCState) -> dict[str, Any]:
        try:
            detection = self.detector.detect(state)
        except Exception as error:
            return {
                "defect_detected": False,
                "defect_type": "unknown",
                "confidence": 0.0,
                "bbox": None,
                "segmentation_result": None,
                "detections": [],
                "camera_classifications": [],
                "unresolved_camera_ids": [],
                "inference_status": "ERROR",
                "error": str(error),
                "execution_trace": _trace(
                    "detect_defect",
                    f"Suy luận mô hình gặp lỗi (đã chặn an toàn): {error}",
                    "FAILED",
                ),
            }
        detected = bool(detection.get("defect_detected"))
        model_name = str(detection.get("model_name") or type(self.detector).__name__)

        # One classification per camera that actually has a detection — each of the 5
        # fixed camera mounts observes a different panel of the vehicle, so a finding on
        # any one of them must independently be able to drive PASS/FAIL/HITL, not just
        # whichever camera happens to hold the single worst finding overall.
        camera_classifications: list[dict[str, Any]] = [
            self._classify_local_detection(
                state, detection, max(camera["detections"], key=_detection_priority_key)
            )
            for camera in detection.get("camera_results", [])
            if camera.get("defect_detected")
        ]
        primary_detection_id = detection.get("primary_detection_id")
        worst = next(
            (item for item in camera_classifications if item["detection_id"] == primary_detection_id),
            None,
        )
        unresolved_camera_ids = [
            item["camera_id"] for item in camera_classifications if item["catalog_defect_type"] is None
        ]

        if worst is not None:
            suggested_codes = worst["suggested_defect_codes"]
            reasoning_status = worst["reasoning_status"]
            classification_dump = worst["defect_code_classification"]
            classified_defect_code = worst["classified_defect_code"]
            defect_family = worst["defect_family"]
            catalog_defect_type = worst["catalog_defect_type"]
            severity = worst["severity"]
            severity_source_id = worst["severity_source_id"]
            similar_defect_warning = worst["similar_defect_warning"]
        else:
            suggested_codes = []
            reasoning_status = "NOT_RUN"
            classification_dump = {}
            classified_defect_code = None
            defect_family = None
            catalog_defect_type = None
            severity = str(detection.get("severity") or "UNASSESSED")
            severity_source_id = None
            similar_defect_warning = False

        visual = detection.get("visual_measurements") or {}
        geometry_detail = (
            f" khung_bao={float(visual.get('width_px', 0)):.0f}x"
            f"{float(visual.get('height_px', 0)):.0f}px, "
            f"tỉ_lệ_diện_tích_ảnh={float(visual.get('image_area_ratio', 0)):.1%};"
            if visual
            else ""
        )
        length_mm = visual.get("estimated_length_mm")
        size_status = visual.get("physical_size_status")
        size_detail = (
            f" kích_thước_ước_lượng={float(length_mm):.1f}mm "
            f"(hiệu_chuẩn={visual.get('calibration_profile_id')}, trạng_thái={size_status})."
            if length_mm is not None
            else f" kích_thước_mm=chưa đo được (trạng_thái={size_status or 'REQUIRES_CAMERA_CALIBRATION'})."
        )
        raw_zone_name = str(state.get("zone_name") or "unknown_zone")
        zone_name = (
            _zone_name_for_camera(state.get("camera_id"), raw_zone_name)
            if raw_zone_name == "unknown_zone"
            else raw_zone_name
        )
        return {
            **detection,
            "zone_name": zone_name,
            "suggested_defect_codes": suggested_codes,
            "defect_code_classification": classification_dump,
            "agent_reasoning_status": reasoning_status,
            "classified_defect_code": classified_defect_code,
            "defect_family": defect_family,
            # Set ONLY when defect_catalog confirmed a real defect_code for this finding —
            # PolicyCatalog.evaluate() matches on this, never on the raw CV label directly
            # (agent/services/policy.py), so an unclassified finding can never let Policy
            # infer an action_code/final_status from an unvetted YOLO output.
            "catalog_defect_type": catalog_defect_type,
            "severity": severity,
            "severity_source_id": severity_source_id,
            "similar_defect_warning": similar_defect_warning,
            "camera_classifications": camera_classifications,
            "unresolved_camera_ids": unresolved_camera_ids,
            "execution_trace": _trace(
                "detect_defect",
                f"{model_name} trả về defect_detected={detected}, "
                f"độ_tin_cậy={float(detection.get('confidence', 0.0)):.2f}, "
                f"số_phát_hiện={len(detection.get('detections', []))} trên "
                f"{len(detection.get('camera_results', [])) or 1} camera; "
                f"phân_loại_độc_lập_theo_camera={len(camera_classifications)} "
                f"(chưa_khớp_danh_mục={len(unresolved_camera_ids)}); "
                f"mã_đã_chọn={classified_defect_code};{geometry_detail}"
                f"{size_detail}",
            ),
        }

    def assess_result(self, state: QCState) -> dict[str, Any]:
        camera_classifications = state.get("camera_classifications") or []
        unresolved_camera_ids = state.get("unresolved_camera_ids") or []

        if state.get("inference_status") == "ERROR":
            route = "HITL"
            decision = "MODEL_ERROR_REVIEW_REQUIRED"
            reason = "Suy luận mô hình thất bại; bắt buộc QC xét duyệt để đảm bảo an toàn."
        elif not state.get("defect_detected", False):
            route = "PASS"
            decision = "PASS"
            reason = "Không phát hiện lỗi bề mặt nào thuộc danh mục được hỗ trợ."
        elif unresolved_camera_ids:
            route = "HITL"
            decision = "UNKNOWN_CLASS_REVIEW_REQUIRED"
            reason = (
                "Phát hiện lỗi mới hoặc chưa có trong danh mục ở camera "
                f"{', '.join(unresolved_camera_ids)} nên Agent không thể phân loại."
            )
        else:
            route = "CONFIRMED"
            decision = "DEFECT_CONFIRMED"
            reason = (
                f"Agent đã phân loại độc lập {len(camera_classifications)} camera có lỗi "
                "và chọn được mã QC đang hoạt động cho từng camera."
            )

        camera_policy_decisions: list[dict[str, Any]] = []
        analysis: ReasoningAnalysis | None = None

        if route == "CONFIRMED":
            # Evaluate policy for EVERY camera's own finding independently — a defect on
            # CAM-03 that the catalog/policy says must FAIL cannot be hidden just because
            # CAM-01's finding happened to be classified as PASS-eligible.
            evaluated: list[tuple[dict[str, Any], PolicyDecision]] = []
            for item in camera_classifications:
                overlay_state = {
                    **state,
                    "defect_type": item["defect_type"],
                    "catalog_defect_type": item["catalog_defect_type"],
                    "confidence": item["confidence"],
                    "severity": item["severity"],
                    "bbox": item["bbox"],
                    "visual_measurements": item["visual_measurements"],
                    "camera_id": item["camera_id"],
                }
                evaluated.append((item, self.policy_catalog.evaluate(overlay_state)))

            camera_policy_decisions = [
                {
                    "camera_id": item["camera_id"],
                    "detection_id": item["detection_id"],
                    "policy_decision": decision.model_dump(mode="json"),
                }
                for item, decision in evaluated
            ]

            # Worst-wins, deterministically: ANY camera FAILing fails the whole vehicle.
            # The single decision that drives the LLM narrative is the highest-severity
            # FAIL (or, if nothing fails, just the highest-severity finding overall).
            failing = [pair for pair in evaluated if pair[1].final_status == "FAIL"]
            _worst_item, policy = max(failing or evaluated, key=lambda pair: _classification_rank(pair[0]))
            aggregate_final_status = "FAIL" if failing else "PASS"

            try:
                analysis = self.reasoning.analyze(state, policy)
            except ReasoningUnavailableError as error:
                route = "HITL"
                decision = "LLM_AGENT_UNAVAILABLE"
                reason = f"LLM Agent không thể đưa ra quyết định hợp lệ: {error}."
            else:
                # The LLM only ever reasons about ONE camera's policy — it cannot know a
                # DIFFERENT camera's defect is what actually fails the vehicle, so the
                # deterministic cross-camera aggregate always overrides its free-form status.
                if analysis.final_status != aggregate_final_status:
                    analysis = analysis.model_copy(
                        update={
                            "final_status": aggregate_final_status,
                            "allow_test_drive": (
                                aggregate_final_status == "PASS" and analysis.allow_test_drive
                            ),
                        }
                    )
        else:
            policy = self.policy_catalog.evaluate(state)

        review = policy.document_review
        return {
            "assessment_route": route,
            "decision": decision,
            "hitl_status": "PENDING" if route == "HITL" else "CONFIRMED",
            "enriched_defects": _enrich_defects(state),
            "reason": reason,
            "human_required": route == "HITL",
            "policy_decision": policy.model_dump(mode="json"),
            "camera_policy_decisions": camera_policy_decisions,
            "ai_analysis": analysis.model_dump(mode="json") if analysis else {},
            "agent_reasoning_status": (
                "LLM_DECISION_COMPLETED" if analysis else state.get("agent_reasoning_status", "NOT_RUN")
            ),
            "execution_trace": _trace(
                "assess_result",
                f"Định_tuyến={route}. Đánh giá chính sách độc lập cho "
                f"{len(camera_policy_decisions)} camera; tra cứu chính sách khớp "
                f"{review.matched_document_count} tài liệu kiểm soát, thiếu "
                f"{len(review.missing_data)} minh chứng, và phát sinh "
                f"{len(review.warnings)} cảnh báo kiểm soát tài liệu.",
            ),
        }

    def verify_defect(self, state: QCState) -> dict[str, Any]:
        result = self.verifier.verify(state)
        return {
            **result,
            "execution_trace": _trace(
                "verify_defect",
                f"Lượt xác minh {result['verify_count']} trả về kết quả {result['verify_result']}.",
            ),
        }

    def human_review(self, state: QCState) -> dict[str, Any]:
        response = interrupt(
            {
                "type": "visual_qc_review",
                "inspection_id": state["inspection_id"],
                "vehicle_id": state["vehicle_id"],
                "defect_type": state.get("defect_type"),
                "confidence": state.get("confidence"),
                "verify_count": state.get("verify_count", 0),
                "reason": state.get("reason"),
                "allowed_actions": ["APPROVE", "REJECT", "OVERRIDE"],
            }
        )
        if not isinstance(response, dict):
            raise ValueError("HITL resume payload must be an object")
        action = str(response.get("action", "")).upper()
        if action not in {"APPROVE", "REJECT", "OVERRIDE"}:
            raise ValueError("HITL action must be APPROVE, REJECT, or OVERRIDE")
        decision = "DEFECT_CONFIRMED" if action in {"APPROVE", "OVERRIDE"} else "DEFECT_REJECTED_BY_QC"
        measurements = dict(state.get("measurements") or {})
        if response.get("length_mm") is not None:
            measurements["defect_length_mm"] = float(response["length_mm"])
        if response.get("location"):
            measurements["defect_location"] = str(response["location"])
        return {
            "human_required": False,
            "human_decision": response,
            "decision": decision,
            "hitl_status": "OVERRIDDEN" if action == "OVERRIDE" else "CONFIRMED",
            "reason": str(response.get("reason") or f"Nhân viên QC đã chọn hành động {action}."),
            "measurements": measurements,
            "execution_trace": _trace("human_review", f"HITL đã tiếp tục với hành động={action}."),
        }

    def supervisor_review(self, state: QCState) -> dict[str, Any]:
        """Second HITL gate, reached only when an operator chose OVERRIDE in `human_review`.
        A supervisor must APPROVE (keep the operator's override recommendation) or REJECT it
        (fall back to the normal catalog policy decision) before the graph can finalize."""
        human_decision = state.get("human_decision") or {}
        response = interrupt(
            {
                "type": "supervisor_escalation_review",
                "inspection_id": state["inspection_id"],
                "vehicle_id": state["vehicle_id"],
                "defect_type": state.get("defect_type"),
                "confidence": state.get("confidence"),
                "operator_reviewer": human_decision.get("reviewer"),
                "operator_reason": human_decision.get("reason"),
                "operator_recommendation": human_decision.get("recommendation"),
                "allowed_actions": ["APPROVE", "REJECT"],
            }
        )
        if not isinstance(response, dict):
            raise ValueError("Supervisor resume payload must be an object")
        action = str(response.get("action", "")).upper()
        if action not in {"APPROVE", "REJECT"}:
            raise ValueError("Supervisor action must be APPROVE or REJECT")
        approved = action == "APPROVE"
        updated_human_decision = {
            **human_decision,
            "supervisor_action": action,
            "supervisor_reviewer": response.get("reviewer"),
            "supervisor_reason": response.get("reason"),
        }
        return {
            "human_decision": updated_human_decision,
            "decision": "DEFECT_CONFIRMED" if approved else "OVERRIDE_REJECTED_BY_SUPERVISOR",
            "hitl_status": "SUPERVISOR_APPROVED" if approved else "SUPERVISOR_REJECTED",
            "reason": str(
                response.get("reason")
                or f"Giám sát viên đã {'phê duyệt' if approved else 'từ chối'} yêu cầu chuyển cấp."
            ),
            "execution_trace": _trace(
                "supervisor_review", f"Giám sát viên đã xét duyệt chuyển cấp với hành động={action}."
            ),
        }

    def generate_recommendation(self, state: QCState) -> dict[str, Any]:
        policy = self.policy_catalog.evaluate(state)
        human_action = str((state.get("human_decision") or {}).get("action", "")).upper()
        supervisor_action = str((state.get("human_decision") or {}).get("supervisor_action", "")).upper()
        override = (state.get("human_decision") or {}).get("recommendation")
        # An OVERRIDE only reaches here after supervisor_review resolves it (routes.py's
        # route_after_human_review) — only apply the operator's override once the supervisor
        # APPROVEd it; a REJECTed override must fall through to the normal policy decision.
        if human_action == "OVERRIDE" and supervisor_action == "APPROVE" and override:
            policy = policy.model_copy(
                update={
                    "action_code": str(override),
                    "action_label": str(override).replace("_", " ").strip().title(),
                    "final_status": "FAIL",
                    "production_eligible": False,
                }
            )
        stored_analysis = state.get("ai_analysis") or {}
        if stored_analysis:
            analysis = ReasoningAnalysis.model_validate(stored_analysis)
        elif state.get("human_decision"):
            review_reason = str(
                (state.get("human_decision") or {}).get("reason")
                or state.get("reason")
                or "QC đã hoàn tất bước xét duyệt thủ công theo yêu cầu."
            )
            analysis = ReasoningAnalysis(
                summary_en=review_reason,
                summary_vi=review_reason,
                risk_flags=["HUMAN_REVIEW_DECISION"],
                recommended_checks=policy.required_steps,
                cited_source_ids=[item.id for item in policy.references],
                provider="human_review",
                model="qc-resume",
                severity=str(state.get("severity") or "UNASSESSED"),
                action_code=policy.action_code,
                action_label=policy.action_label,
                final_status=policy.final_status,
                allow_test_drive=bool(policy.test_drive_allowed),
                decision_rationale_vi=review_reason,
            )
        else:
            analysis = self.reasoning.analyze(state, policy)
        visual = state.get("visual_measurements") or {}
        classification = state.get("defect_code_classification") or {}
        warnings = list(analysis.risk_flags)
        if state.get("similar_defect_warning"):
            warnings.append("MULTIPLE_SIMILAR_DEFECT_REGIONS")
        primary_detection_id = state.get("primary_detection_id")
        enriched_defects = [
            {**item, "severity_rank": analysis.severity}
            if item.get("detection_id") == primary_detection_id
            else item
            for item in state.get("enriched_defects") or []
        ]
        return {
            "severity": analysis.severity,
            "enriched_defects": enriched_defects,
            "recommendation_code": analysis.action_code,
            "recommendation": analysis.action_label,
            "final_status": analysis.final_status,
            "allow_test_drive": analysis.allow_test_drive,
            "reason": analysis.summary_vi,
            "human_required": policy.human_required,
            "policy_decision": policy.model_dump(mode="json"),
            "ai_analysis": analysis.model_dump(mode="json"),
            "agent_analysis": {
                "reasoning_source": analysis.provider,
                "reasoning_model": analysis.model,
                "llm_used": analysis.provider == "groq",
                "defect": {
                    "type": state.get("defect_type"),
                    "code": state.get("classified_defect_code"),
                    "family": state.get("defect_family"),
                    "confidence": state.get("confidence"),
                    "classification_confidence": classification.get("confidence"),
                    "classification_reason_vi": classification.get("rationale_vi"),
                },
                "geometry": {
                    "length_mm": visual.get("estimated_length_mm"),
                    "width_mm": visual.get("estimated_width_mm"),
                    "height_mm": visual.get("estimated_height_mm"),
                    "surface_area_mm2": visual.get("estimated_mask_area_mm2"),
                    "width_px": visual.get("width_px"),
                    "height_px": visual.get("height_px"),
                    "image_area_ratio": visual.get("image_area_ratio"),
                    "measurement_status": visual.get("physical_size_status"),
                    "calibration_profile_id": visual.get("calibration_profile_id"),
                },
                "location": {
                    "zone_name": state.get("zone_name"),
                    "relative_position": visual.get("relative_position"),
                    "camera_id": state.get("camera_id"),
                    "bbox": state.get("bbox"),
                },
                "plan": {
                    "code": analysis.action_code,
                    "label": analysis.action_label,
                    "final_status": analysis.final_status,
                    "allow_test_drive": analysis.allow_test_drive,
                    "required_steps": analysis.recommended_checks,
                },
                "warnings": warnings,
                "missing_evidence": policy.missing_evidence,
            },
            "execution_trace": _trace(
                "generate_recommendation",
                f"Chính sách {policy.policy_id}@{policy.policy_revision} chọn "
                f"{analysis.action_code}; nguồn_quyết_định={analysis.provider}.",
            ),
        }

    def save_result(self, state: QCState) -> dict[str, Any]:
        update: dict[str, Any] = {}
        if state.get("decision") == "PASS":
            update = {
                "recommendation_code": "RELEASE_TO_NEXT_QUALITY_GATE",
                "recommendation": "Cho phép xe chuyển sang trạm kiểm tra chất lượng tiếp theo",
                "final_status": "PASS",
                "allow_test_drive": True,
                "hitl_status": "CONFIRMED",
                "reason": state.get("reason", "Không phát hiện lỗi."),
            }
        completed_state: QCState = {
            **state,
            **update,
            "execution_trace": [
                *state.get("execution_trace", []),
                *_trace("save_result", "Đã lưu trạng thái cuối cùng qua repository."),
            ],
        }
        self.repository.save(completed_state)
        return {
            **update,
            "execution_trace": _trace(
                "save_result",
                "Đã lưu trạng thái cuối cùng qua repository.",
            ),
        }


def _enrich_defects(state: QCState) -> list[dict[str, Any]]:
    """Add context and preserve the detector's explicit calibration provenance.

    Every camera that has its own classified finding (state["camera_classifications"],
    built in QCNodes.detect_defect/_classify_local_detection — one per camera with a
    detection) gets ITS OWN real severity and is_primary=True; a detection that lost
    out to another finding within the SAME camera still gets no fabricated severity.
    """
    fallback_zone_name = str(state.get("zone_name") or "unknown_zone")
    classified_by_detection_id = {
        item["detection_id"]: item for item in (state.get("camera_classifications") or [])
    }
    return [
        {
            **item,
            # Each detection may come from a different camera than the primary one (e.g. a
            # secondary finding on CAM-03 while the primary is CAM-01) — zone must reflect that
            # detection's own camera, not be a single value copied across every finding.
            "zone_name": _zone_name_for_camera(item.get("camera_id"), fallback_zone_name),
            "estimated_depth_mm": None,
            "estimated_width_mm": item.get("visual_measurements", {}).get(
                "estimated_width_mm"
            ),
            "estimated_height_mm": item.get("visual_measurements", {}).get(
                "estimated_height_mm"
            ),
            "surface_area_mm2": item.get("visual_measurements", {}).get(
                "estimated_mask_area_mm2"
            ),
            "physical_measurement_status": item.get("visual_measurements", {}).get(
                "physical_size_status",
                "REQUIRES_CALIBRATION_OR_QC_MEASUREMENT",
            ),
            "calibration_profile_id": item.get("visual_measurements", {}).get(
                "calibration_profile_id"
            ),
            "severity_rank": (
                classified_by_detection_id[item["detection_id"]]["severity"]
                if item.get("detection_id") in classified_by_detection_id
                else "UNCLASSIFIED_SECONDARY_FINDING"
            ),
            "is_primary": item.get("detection_id") in classified_by_detection_id,
        }
        for item in state.get("detections", [])
    ]
