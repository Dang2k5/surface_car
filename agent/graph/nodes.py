from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from agent.graph.state import QCState, TraceEvent
from agent.services.defect_catalog import DefectCatalogService
from agent.services.detector import DetectorService
from agent.services.policy import PolicyCatalog
from agent.services.reasoning import (
    DefectCodeClassification,
    ReasoningAnalysis,
    ReasoningService,
    ReasoningUnavailableError,
)
from agent.services.repository import QCRepository
from agent.services.verifier import VerifierService
from agent.services.vision_verifier import VisionUnavailableError, VisionVerifierService


def _trace(node: str, detail: str, status: str = "COMPLETED") -> list[TraceEvent]:
    return [{"node": node, "status": status, "detail": detail}]


class QCNodes:
    def __init__(
        self,
        detector: DetectorService,
        verifier: VerifierService,
        reasoning: ReasoningService,
        policy_catalog: PolicyCatalog,
        repository: QCRepository,
        defect_catalog: DefectCatalogService,
        vision: VisionVerifierService,
    ) -> None:
        self.detector = detector
        self.verifier = verifier
        self.reasoning = reasoning
        self.policy_catalog = policy_catalog
        self.repository = repository
        self.defect_catalog = defect_catalog
        self.vision = vision

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
        suggested_codes = self.defect_catalog.match(str(detection.get("defect_type") or "none"))
        try:
            classification = self.reasoning.classify_defect_code(
                {**state, **detection}, suggested_codes
            )
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
        visual = detection.get("visual_measurements") or {}
        geometry_detail = (
            f" khung_bao={float(visual.get('width_px', 0)):.0f}x"
            f"{float(visual.get('height_px', 0)):.0f}px, "
            f"tỉ_lệ_diện_tích_ảnh={float(visual.get('image_area_ratio', 0)):.1%};"
            if visual
            else ""
        )
        return {
            **detection,
            "zone_name": str(state.get("zone_name") or "unknown_zone"),
            "suggested_defect_codes": suggested_codes,
            "defect_code_classification": classification.model_dump(mode="json"),
            "agent_reasoning_status": reasoning_status,
            "classified_defect_code": classification.defect_code,
            "defect_family": classification.defect_family,
            "severity": (
                str(classified_record.get("default_severity") or "UNASSESSED")
                if classified_record
                else str(detection.get("severity") or "UNASSESSED")
            ),
            "similar_defect_warning": classification.similar_observation_warning,
            "execution_trace": _trace(
                "detect_defect",
                f"{model_name} trả về defect_detected={detected}, "
                f"độ_tin_cậy={float(detection.get('confidence', 0.0)):.2f}, "
                f"số_phát_hiện={len(detection.get('detections', []))} trên "
                f"{len(detection.get('camera_results', [])) or 1} camera; "
                f"khớp_danh_mục={len(suggested_codes)}, mã_đã_chọn={classification.defect_code}, "
                f"bộ_phân_loại={classification.provider};{geometry_detail} "
                "kích_thước_mm=cần hiệu chuẩn.",
            ),
        }

    def multimodal_verify(self, state: QCState) -> dict[str, Any]:
        if not state.get("defect_detected", False):
            return {
                "agent_vision_status": "SKIPPED_NO_DEFECT",
                "execution_trace": _trace(
                    "multimodal_verify", "Không phát hiện lỗi; bỏ qua đối chiếu bằng hình ảnh."
                ),
            }
        try:
            assessment = self.vision.verify_visual(state)
        except VisionUnavailableError as error:
            return {
                "visual_assessment": None,
                "agent_vision_status": "UNAVAILABLE_REQUIRES_HITL",
                "execution_trace": _trace(
                    "multimodal_verify",
                    f"Vision LLM không khả dụng hoặc trả về kết quả không hợp lệ: {error}.",
                    "FAILED",
                ),
            }
        if assessment is None:
            return {
                "visual_assessment": None,
                "agent_vision_status": "NOT_CONFIGURED",
                "execution_trace": _trace(
                    "multimodal_verify", "Chưa cấu hình VISION_LLM_PROVIDER; bỏ qua bước này."
                ),
            }
        return {
            "visual_assessment": assessment.model_dump(mode="json"),
            "agent_vision_status": "COMPLETED",
            "execution_trace": _trace(
                "multimodal_verify",
                f"kết_quả_đối_chiếu={assessment.visual_verification}, "
                f"độ_không_chắc_chắn={assessment.visual_uncertainty}, "
                f"nghi_ngờ_nhiễu_ảnh={assessment.possible_artifact}.",
            ),
        }

    def assess_result(self, state: QCState) -> dict[str, Any]:
        if state.get("inference_status") == "ERROR":
            route = "HITL"
            decision = "MODEL_ERROR_REVIEW_REQUIRED"
            reason = "Suy luận mô hình thất bại; bắt buộc QC xét duyệt để đảm bảo an toàn."
        elif not state.get("defect_detected", False):
            route = "PASS"
            decision = "PASS"
            reason = "Không phát hiện lỗi bề mặt nào thuộc danh mục được hỗ trợ."
        elif state.get("defect_type") == "unknown" or not state.get("classified_defect_code"):
            route = "HITL"
            decision = "UNKNOWN_CLASS_REVIEW_REQUIRED"
            reason = "Phát hiện một lỗi mới hoặc chưa có trong danh mục nên Agent không thể phân loại."
        else:
            route = "CONFIRMED"
            decision = "DEFECT_CONFIRMED"
            reason = "Agent đã phân loại lỗi đã biết và chọn được mã QC đang hoạt động."

        # Multimodal LLM visual cross-check must never let a CONFLICT/HIGH-uncertainty
        # result slip through as an automatic PASS/CONFIRMED (POLICY_GOVERNANCE.md).
        visual = state.get("visual_assessment")
        if state.get("agent_vision_status") == "UNAVAILABLE_REQUIRES_HITL":
            route = "HITL"
            decision = "VISION_LLM_UNAVAILABLE"
            reason = "Vision LLM không tạo được đánh giá hình ảnh hợp lệ; bắt buộc QC xét duyệt để đảm bảo an toàn."
        elif visual and visual.get("visual_verification") == "CONFLICT":
            route = "HITL"
            decision = "VISUAL_LLM_CONFLICT_REQUIRES_HITL"
            reason = "Kết quả đối chiếu Vision LLM mâu thuẫn với phát hiện của YOLO; cần QC xét duyệt."
        elif visual and visual.get("visual_uncertainty") == "HIGH":
            route = "HITL"
            decision = "VISUAL_LLM_UNCERTAINTY_HIGH_REQUIRES_HITL"
            reason = "Độ không chắc chắn khi đối chiếu Vision LLM ở mức CAO; cần QC xét duyệt."

        policy = self.policy_catalog.evaluate(state)
        analysis: ReasoningAnalysis | None = None
        if route == "CONFIRMED":
            try:
                analysis = self.reasoning.analyze(state, policy)
            except ReasoningUnavailableError as error:
                route = "HITL"
                decision = "LLM_AGENT_UNAVAILABLE"
                reason = f"LLM Agent không thể đưa ra quyết định hợp lệ: {error}."
        review = policy.document_review
        return {
            "assessment_route": route,
            "decision": decision,
            "hitl_status": "PENDING" if route == "HITL" else "CONFIRMED",
            "enriched_defects": _enrich_defects(state),
            "reason": reason,
            "human_required": route == "HITL",
            "policy_decision": policy.model_dump(mode="json"),
            "ai_analysis": analysis.model_dump(mode="json") if analysis else {},
            "agent_reasoning_status": (
                "LLM_DECISION_COMPLETED" if analysis else state.get("agent_reasoning_status", "NOT_RUN")
            ),
            "execution_trace": _trace(
                "assess_result",
                f"Định_tuyến={route}. Tra cứu chính sách khớp {review.matched_document_count} tài liệu "
                f"kiểm soát, thiếu {len(review.missing_data)} minh chứng, và phát sinh "
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
        decision = "DEFECT_CONFIRMED" if action in {"APPROVE", "OVERRIDE"} else "REINSPECTION_REQUIRED"
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
        (send the vehicle back to REINSPECTION_REQUIRED) before the graph can finalize."""
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
            "decision": "DEFECT_CONFIRMED" if approved else "REINSPECTION_REQUIRED",
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
                    "final_status": "HUMAN_OVERRIDE_APPLIED",
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
        return {
            "severity": analysis.severity,
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

    Only the primary detection (the one that drove assess_result/policy) is
    classified into a QC severity; a fabricated severity must never be
    attributed to the other camera views' findings.
    """
    zone_name = str(state.get("zone_name") or "unknown_zone")
    primary_detection_id = state.get("primary_detection_id")
    return [
        {
            **item,
            "zone_name": zone_name,
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
                state.get("severity") or "UNASSESSED"
                if item.get("detection_id") == primary_detection_id
                else "UNCLASSIFIED_SECONDARY_FINDING"
            ),
            "is_primary": item.get("detection_id") == primary_detection_id,
        }
        for item in state.get("detections", [])
    ]
