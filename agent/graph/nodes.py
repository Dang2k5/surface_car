from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langgraph.types import interrupt

from agent.graph.state import QCState, TraceEvent
from agent.services.defect_catalog import DefectCatalogService
from agent.services.defect_rule_engine import classify_by_rule
from agent.services.detector import DetectorService
from agent.services.policy import PolicyCatalog, PolicyDecision
from agent.services.reasoning import (
    DefectCodeClassification,
    DeterministicReasoningService,
    ReasoningAnalysis,
    ReasoningService,
    ReasoningUnavailableError,
)
from agent.services.repository import QCRepository


def _trace(node: str, detail: str, status: str = "COMPLETED") -> list[TraceEvent]:
    return [{"node": node, "status": status, "detail": detail}]


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
    """Ranks a single classified finding for "which finding is worst overall" —
    used to pick the single decision that drives the LLM narrative once every finding
    has already been independently classified and policy-evaluated."""
    measurements = item.get("visual_measurements") or {}
    length_mm = float(measurements.get("estimated_length_mm") or 0.0)
    return (_SEVERITY_LETTER_RANK.get(str(item.get("severity") or "").upper(), 0), length_mm)


# Each of the 5 camera mounts is physically fixed to point at one specific side of the
# vehicle body (confirmed by the plant setup — this is a real fixture fact, not a guess):
# CAM-01=front, CAM-02=rear, CAM-03=left, CAM-04=right, CAM-05=top/overview. A defect seen by
# a given camera really is on that side of the vehicle.
_CAMERA_ZONE_NAMES: dict[str, str] = {
    "CAM-01": "truoc",
    "CAM-02": "sau",
    "CAM-03": "trai",
    "CAM-04": "phai",
    "CAM-05": "tren_toan_canh",
}


def _zone_name_for_camera(camera_id: Any, fallback: str) -> str:
    """A caller never explicitly picks a zone in the upload form (there's no such field), so
    the request always arrives with the Pydantic default "unknown_zone" — derive the real
    zone from which fixed camera mount actually saw the finding instead of leaving it
    unknown."""
    zone = _CAMERA_ZONE_NAMES.get(str(camera_id or "").strip().upper())
    return zone or fallback


class QCNodes:
    def __init__(
        self,
        detector: DetectorService,
        reasoning: ReasoningService,
        policy_catalog: PolicyCatalog,
        repository: QCRepository,
        defect_catalog: DefectCatalogService,
    ) -> None:
        self.detector = detector
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
        """Classify ONE camera's own worst finding against the defect catalog's structured
        rules, independently of every other camera's finding. Called once per camera that
        has a detection (bounded by KNOWN_CAMERA_IDS, currently 5), so a defect on CAM-03
        is classified on its own merits instead of only ever being read off the single
        global-worst detection.

        This is a pure threshold/count decision (agent/services/defect_rule_engine.py) -- no
        LLM call. docs/DE_BAI_GOC.md assigns the LLM the "mô tả/giải thích lỗi" role
        (explaining an already-made decision, in generate_recommendation/analyze()), while
        the "decide" step is meant to run on a confidence/measurement threshold. The catalog's
        rules are pure numeric thresholds, so there is nothing here an LLM would decide any
        better than a rule -- and a rule can never time out or hallucinate a wrong code."""
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
        classification = classify_by_rule(overlay, suggested_codes)
        if classification is not None:
            reasoning_status = "RULE_ENGINE_CLASSIFICATION_COMPLETED"
        else:
            classification = DefectCodeClassification(
                defect_code=None,
                defect_family=None,
                confidence=0.0,
                rationale_vi=(
                    "Không có luật tự động khớp rõ ràng cho phát hiện này; cần QC kiểm duyệt."
                ),
                candidate_codes=[str(item.get("defect_code")) for item in suggested_codes],
                provider="rule_engine",
                model="threshold-v1",
                fallback_reason="NO_MATCHING_RULE",
            )
            reasoning_status = "RULE_ENGINE_NO_MATCH_REQUIRES_HITL"
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
            precomputed = state.get("precomputed_detection")
            detection = precomputed if precomputed is not None else self.detector.detect(state)
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

        # One classification per DETECTION, not per camera — a camera can hold several
        # findings (e.g. two separate scratches), and each one must independently be able
        # to drive PASS/FAIL/HITL. Picking only that camera's single worst finding would
        # silently drop every other finding from classification and policy evaluation,
        # letting several real (if individually minor) defects go unassessed.
        local_detections = [
            local
            for camera in detection.get("camera_results", [])
            if camera.get("defect_detected")
            for local in camera["detections"]
        ]
        # Each classification is an independent, blocking Groq HTTP call -- run them
        # concurrently instead of one-at-a-time so N findings cost ~one round-trip instead
        # of N of them summed.
        if len(local_detections) <= 1:
            camera_classifications: list[dict[str, Any]] = [
                self._classify_local_detection(state, detection, local)
                for local in local_detections
            ]
        else:
            with ThreadPoolExecutor(max_workers=min(len(local_detections), 8)) as executor:
                camera_classifications = list(
                    executor.map(
                        lambda local: self._classify_local_detection(state, detection, local),
                        local_detections,
                    )
                )
        primary_detection_id = detection.get("primary_detection_id")
        worst = next(
            (item for item in camera_classifications if item["detection_id"] == primary_detection_id),
            None,
        )
        # A camera can now appear more than once here (one entry per detection on it), so
        # dedupe — otherwise an unresolved camera with N unmatched findings would repeat
        # its id N times in the HITL trace message below.
        unresolved_camera_ids = sorted(
            {item["camera_id"] for item in camera_classifications if item["catalog_defect_type"] is None}
        )

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
            _zone_name_for_camera(detection.get("camera_id"), raw_zone_name)
            if raw_zone_name == "unknown_zone"
            else raw_zone_name
        )
        # Every zone (vehicle body side) that actually has a defect in THIS inspection — not
        # just the single worst one. One inspection combines all 5 fixed cameras, so it can
        # genuinely have simultaneous findings on more than one side (e.g. front AND left);
        # collapsing that down to one `zone_name` would hide the other side's defect from any
        # "vùng lỗi" log/summary.
        affected_zones = sorted(
            {
                _zone_name_for_camera(camera["camera_id"], "unknown_zone")
                for camera in detection.get("camera_results", [])
                if camera.get("defect_detected")
            }
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
            "affected_zones": affected_zones,
            "execution_trace": _trace(
                "detect_defect",
                f"{model_name} trả về defect_detected={detected}, "
                f"độ_tin_cậy={float(detection.get('confidence', 0.0)):.2f}, "
                f"số_phát_hiện={len(detection.get('detections', []))} trên "
                f"{len(detection.get('camera_results', [])) or 1} camera; "
                f"vùng_lỗi={', '.join(affected_zones) or 'không có'}; "
                f"phân_loại_độc_lập_theo_camera={len(camera_classifications)} "
                f"(chưa_khớp_danh_mục={len(unresolved_camera_ids)}); "
                f"mã_đã_chọn={classified_defect_code};{geometry_detail}"
                f"{size_detail}",
            ),
        }

    def assess_result(self, state: QCState) -> dict[str, Any]:
        camera_classifications = state.get("camera_classifications") or []
        # Reconnects backend/app/config.py's ModelSettings.confirmed_threshold (already flowed
        # into initial state by langgraph_api.py) to the actual routing decision -- previously
        # computed but never read anywhere, so a 26%-confidence detection was treated identically
        # to a 99%-confidence one. A finding's own YOLO confidence must clear this bar before its
        # rule-engine/policy classification is trusted to stand on its own; below it, the finding
        # is "ambiguous" no matter how clean its catalog match looks, and must go to a human
        # instead of silently deciding PASS/FAIL.
        confirmed_threshold = float(state.get("confirmed_threshold") or 0.85)

        def _is_confident(item: dict[str, Any]) -> bool:
            return (
                item.get("catalog_defect_type") is not None
                and float(item.get("confidence") or 0.0) >= confirmed_threshold
            )

        camera_policy_decisions: list[dict[str, Any]] = []
        analysis: ReasoningAnalysis | None = None
        reasoning_degraded = False
        evaluated: list[tuple[dict[str, Any], PolicyDecision]] = []

        if state.get("inference_status") == "ERROR":
            route = "HITL"
            decision = "MODEL_ERROR_REVIEW_REQUIRED"
            reason = "Suy luận mô hình thất bại; bắt buộc QC xét duyệt để đảm bảo an toàn."
        elif not state.get("defect_detected", False):
            route = "PASS"
            decision = "PASS"
            reason = "Không phát hiện lỗi bề mặt nào thuộc danh mục được hỗ trợ."
        else:
            # Evaluate policy for EVERY camera's own finding independently, confident or not --
            # ambiguous ones still get a fail-safe policy (manual reinspection) for the audit
            # trail (camera_policy_decisions), they are just excluded below from driving an
            # automated decision on their own.
            for item in camera_classifications:
                overlay_state = {
                    **state,
                    "defect_type": item["defect_type"],
                    "catalog_defect_type": item["catalog_defect_type"],
                    "classified_defect_code": item["classified_defect_code"],
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
                    "policy_decision": policy_decision.model_dump(mode="json"),
                }
                for item, policy_decision in evaluated
            ]

            confident_pairs = [pair for pair in evaluated if _is_confident(pair[0])]
            ambiguous_pairs = [pair for pair in evaluated if not _is_confident(pair[0])]

            # A confidently classified, policy-confirmed FAIL is decisive on its own: the
            # vehicle is already certain to need holding, so it must not wait on every OTHER,
            # unrelated ambiguous finding being resolved first -- that was exactly the "many
            # confident FAILs but still HITL just because one unrelated finding was unresolved"
            # bug this closes. human_required is still excluded here even when confident: it
            # means no approved policy could authorize a disposition, which is a different
            # problem (missing policy coverage) than an uncertain finding.
            decisive_fail = [
                pair for pair in confident_pairs if pair[1].final_status == "FAIL" and not pair[1].human_required
            ]
            needs_human = [pair for pair in confident_pairs if pair[1].human_required]

            if decisive_fail:
                route = "CONFIRMED"
                decision = "DEFECT_CONFIRMED"
                reason = (
                    f"{len(decisive_fail)} lỗi được phân loại tin cậy cao "
                    f"(≥{confirmed_threshold:.0%}) và chính sách xác nhận FAIL; xe bị giữ lại "
                    "bất kể các phát hiện khác."
                )
                if ambiguous_pairs:
                    reason += (
                        f" Còn {len(ambiguous_pairs)} phát hiện chưa đủ tin cậy hoặc chưa khớp "
                        "danh mục cần QC xem lại bổ sung."
                    )
            elif ambiguous_pairs:
                route = "HITL"
                decision = "LOW_CONFIDENCE_OR_UNCLASSIFIED_REVIEW_REQUIRED"
                cameras = ", ".join(sorted({item["camera_id"] for item, _ in ambiguous_pairs}))
                reason = (
                    f"{len(ambiguous_pairs)} phát hiện ở camera {cameras} chưa đủ độ tin cậy "
                    f"(<{confirmed_threshold:.0%}) hoặc chưa khớp danh mục lỗi; cần QC xét duyệt "
                    "để tránh bỏ sót lỗi thật."
                )
            elif needs_human:
                route = "HITL"
                decision = "MANUAL_REINSPECTION_REQUIRED"
                cameras = ", ".join(sorted({item["camera_id"] for item, _ in needs_human}))
                reason = (
                    f"Không tìm được chính sách đã duyệt phù hợp cho camera {cameras}; "
                    "cần QC xét duyệt thủ công."
                )
            else:
                route = "CONFIRMED"
                decision = "DEFECT_CONFIRMED"
                reason = (
                    f"Agent đã phân loại tin cậy cao {len(confident_pairs)} lỗi phát hiện "
                    "và chọn được mã QC đang hoạt động cho từng lỗi."
                )

        # Andon-style escalation gate (backend/app/hitl_alerts.py's HitlRateAlertService):
        # when this station's HITL rate is CRITICAL, every new inspection is forced through
        # human_review regardless of what it would otherwise have decided — PASS and CONFIRMED
        # both normally skip straight to save_result with no human ever seeing them (see
        # agent/graph/builder.py's edges), which is exactly the silent-failure risk this closes.
        # `force_human_review` is computed fresh per-request (never persisted), so this simply
        # stops firing on its own once the rate/streak drops back down — there is no sticky flag
        # to remember to clear.
        mandatory_review_forced = bool(state.get("force_human_review")) and route != "HITL"
        if mandatory_review_forced:
            original_route = route
            route = "HITL"
            decision = "MANDATORY_REVIEW_LINE_ALERT"
            reason = (
                f"Trạm đang có tỷ lệ HITL bất thường (chế độ Duyệt Bắt Buộc đang bật); "
                f"kết quả gốc lẽ ra là {original_route} nhưng bắt buộc chuyển sang QC xét duyệt."
            )

        if route == "CONFIRMED":
            # Worst-wins, deterministically, among the CONFIDENT findings only (ambiguous ones
            # never reach here — either they produced a decisive FAIL already, or route would
            # have been HITL). The single decision that drives the LLM narrative is the
            # highest-severity FAIL among them (or, if nothing fails, the highest-severity
            # finding overall).
            failing = [pair for pair in confident_pairs if pair[1].final_status == "FAIL"]
            _worst_item, policy = max(
                failing or confident_pairs, key=lambda pair: _classification_rank(pair[0])
            )
            aggregate_final_status = "FAIL" if failing else "PASS"

            try:
                analysis = self.reasoning.analyze(state, policy)
            except ReasoningUnavailableError as error:
                # route/decision above are already final -- they come entirely from
                # deterministic policy evaluation. Groq only ever adds the human-readable
                # narrative on top (docs/DE_BAI_GOC.md: LLM explains, it does not decide),
                # so losing it must never force HITL or change the outcome -- substitute a
                # deterministic narrative instead.
                reasoning_degraded = True
                analysis = DeterministicReasoningService().analyze(state, policy).model_copy(
                    update={"fallback_reason": f"LLM giải trình không khả dụng: {error}."}
                )

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
            "mandatory_review_forced": mandatory_review_forced,
            "policy_decision": policy.model_dump(mode="json"),
            "camera_policy_decisions": camera_policy_decisions,
            "ai_analysis": analysis.model_dump(mode="json") if analysis else {},
            "agent_reasoning_status": (
                "LLM_UNAVAILABLE_FALLBACK_DETERMINISTIC"
                if reasoning_degraded
                else "LLM_DECISION_COMPLETED"
                if analysis
                else state.get("agent_reasoning_status", "NOT_RUN")
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

    def human_review(self, state: QCState) -> dict[str, Any]:
        response = interrupt(
            {
                "type": "visual_qc_review",
                "inspection_id": state["inspection_id"],
                "vehicle_id": state["vehicle_id"],
                "defect_type": state.get("defect_type"),
                "confidence": state.get("confidence"),
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
        A supervisor cannot invent a disposition out of thin air here: they either uphold the
        automated catalog decision (UPHOLD_POLICY), or pick ONE specific APPROVED policy from
        the catalog to apply as this vehicle's final disposition instead — every PASS/FAIL must
        still trace back to a real, versioned policy (POLICY_GOVERNANCE.md), never to a
        supervisor's free-text note."""
        human_decision = state.get("human_decision") or {}
        eligible_policies = [
            {
                "policy_id": item["id"],
                "title": item["title"],
                "action_code": item.get("action_code") or "MULTIPLE_BY_DEFECT",
                "final_status": item.get("final_status"),
            }
            for item in self.policy_catalog.list_approved_policies()
        ]
        allowed_policy_ids = {item["policy_id"] for item in eligible_policies}
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
                "eligible_policies": eligible_policies,
                "allowed_actions": ["UPHOLD_POLICY", *sorted(allowed_policy_ids)],
            }
        )
        if not isinstance(response, dict):
            raise ValueError("Supervisor resume payload must be an object")
        action = str(response.get("action", "")).strip()
        if action != "UPHOLD_POLICY" and action not in allowed_policy_ids:
            raise ValueError("Supervisor action must be UPHOLD_POLICY or the id of an approved policy")
        applied_policy = action != "UPHOLD_POLICY"
        updated_human_decision = {
            **human_decision,
            "supervisor_action": action,
            "supervisor_reviewer": response.get("reviewer"),
            "supervisor_reason": response.get("reason"),
        }
        return {
            "human_decision": updated_human_decision,
            "decision": f"SUPERVISOR_APPLIED_POLICY:{action}" if applied_policy else "OVERRIDE_REJECTED_BY_SUPERVISOR",
            "hitl_status": "SUPERVISOR_APPROVED" if applied_policy else "SUPERVISOR_REJECTED",
            "reason": str(
                response.get("reason")
                or (
                    f"Giám sát viên đã áp dụng chính sách {action} cho trường hợp chuyển cấp."
                    if applied_policy
                    else "Giám sát viên đã giữ nguyên quyết định chính sách gốc, không theo đề xuất."
                )
            ),
            "execution_trace": _trace(
                "supervisor_review", f"Giám sát viên đã xét duyệt chuyển cấp với hành động={action}."
            ),
        }

    def generate_recommendation(self, state: QCState) -> dict[str, Any]:
        policy = self.policy_catalog.evaluate(state)
        human_action = str((state.get("human_decision") or {}).get("action", "")).upper()
        supervisor_action = str((state.get("human_decision") or {}).get("supervisor_action") or "").strip()
        # An OVERRIDE only reaches here after supervisor_review resolves it (routes.py's
        # route_after_human_review). UPHOLD_POLICY (or no supervisor action at all, e.g. this
        # case never escalated) means the automated catalog decision computed above already
        # stands. Any other value is the id of an APPROVED policy the supervisor explicitly
        # chose to apply as the final disposition — re-checked for approval here (not just
        # trusted from the interrupt) in case it was edited/unapproved on the Rules page
        # between the interrupt being raised and the supervisor's resume.
        if human_action == "OVERRIDE" and supervisor_action and supervisor_action != "UPHOLD_POLICY":
            policy_record = next(
                (item for item in self.policy_catalog.document["policies"] if item["id"] == supervisor_action),
                None,
            )
            if policy_record is not None and self.policy_catalog.is_approved(policy_record):
                policy = self.policy_catalog.evaluate_named(supervisor_action, state)
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
            try:
                analysis = self.reasoning.analyze(state, policy)
            except ReasoningUnavailableError as error:
                # Same rationale as assess_result: `policy` above already fixes the
                # decision deterministically, Groq only narrates it -- never let a
                # narrative failure crash the request or change the outcome.
                analysis = DeterministicReasoningService().analyze(state, policy).model_copy(
                    update={"fallback_reason": f"LLM giải trình không khả dụng: {error}."}
                )
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
