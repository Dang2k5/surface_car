from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from agent.mock_workflow import MockQCAgent
from .llm import LLMNotConfiguredError, explain_qc_case, is_auto_explain_enabled

from .schemas import (
    DefectCreate,
    DefectResponse,
    InspectionCreate,
    InspectionResponse,
    InspectionStatus,
    YoloImageResult,
    YoloDetection,
    ClassificationResponse,
    DecisionResponse,
    DecisionRecommendation,
    HITLAction,
    HITLReviewCreate,
    HITLReviewResponse,
    WorkflowRunResponse,
    AgentExplainRequest,
    AgentExplainResponse,
)

router = APIRouter(prefix="/api")


MOCK_CLASSIFICATION_RULES = {
    "scratch": {"panel": "door_panel", "material": "ordinary_steel", "gdt_group": 3, "tolerance_mm": 0.5, "measurement_mm": 0.2, "severity_rank": "C"},
    "dent": {"panel": "quarter_panel", "material": "hot_stamped_steel", "gdt_group": 1, "tolerance_mm": 0.7, "measurement_mm": 1.1, "severity_rank": "P"},
    "paint_defect": {"panel": "hood_class_a_surface", "material": "coated_steel", "gdt_group": 2, "tolerance_mm": 0.3, "measurement_mm": 0.4, "severity_rank": "A"},
}


def _inspection_from_row(request: Request, row) -> InspectionResponse:
    defects = request.app.state.database.connection.execute(
        "SELECT * FROM defects WHERE inspection_id = ? ORDER BY id", (row["id"],)
    ).fetchall()
    response_defects = []
    for defect in defects:
        defect_data = dict(defect)
        if defect_data["location"]:
            defect_data["location"] = json.loads(defect_data["location"])
        if defect_data["bbox"]:
            defect_data["bbox"] = json.loads(defect_data["bbox"])
        defect_data["class_name"] = defect_data["defect_type"]
        response_defects.append(DefectResponse(**defect_data))
    return InspectionResponse(
        id=row["id"],
        vin=row["vin"],
        model=row["model"],
        station=row["station"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        defects=response_defects,
    )


def _create_inspection(request: Request, payload: InspectionCreate) -> InspectionResponse:
    database = request.app.state.database
    inspection_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    database.execute(
        "INSERT INTO inspections (id, vin, model, station, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (inspection_id, payload.vin, payload.model, payload.station, InspectionStatus.OPEN.value, created_at),
    )
    for defect in payload.defects:
        database.execute(
            "INSERT INTO defects (id, inspection_id, defect_type, confidence, camera_id, class_id, bbox, image_width, image_height, model_name, model_version, location, severity_rank) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                inspection_id,
                defect.defect_type.value,
                defect.confidence,
                defect.camera_id,
                defect.class_id,
                None if defect.bbox is None else json.dumps(defect.bbox.model_dump()),
                defect.image_width,
                defect.image_height,
                defect.model_name,
                defect.model_version,
                None if defect.location is None else json.dumps(defect.location),
                defect.severity_rank,
            ),
        )
    row = database.connection.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    inspection = _inspection_from_row(request, row)
    # CP3-CP5 mock workflow runs automatically after every inspection is created.
    # A production deployment will move this work to a background worker/event consumer.
    run_mock_workflow(request, inspection_id)
    return inspection


@router.post("/mock/seed", response_model=list[InspectionResponse])
def seed_mock_data(request: Request, reset: bool = False) -> list[InspectionResponse]:
    database = request.app.state.database
    if reset:
        database.execute("DELETE FROM hitl_reviews")
        database.execute("DELETE FROM workflow_runs")
        database.execute("DELETE FROM decisions")
        database.execute("DELETE FROM classifications")
        database.execute("DELETE FROM defects")
        database.execute("DELETE FROM inspections")
    existing = database.connection.execute("SELECT COUNT(*) AS count FROM inspections").fetchone()["count"]
    if existing:
        rows = database.connection.execute("SELECT * FROM inspections ORDER BY created_at").fetchall()
        return [_inspection_from_row(request, row) for row in rows]
    seed = [
        InspectionCreate(
            vin="MOCK-VIN-SCRATCH-001",
            model="Demo Sedan",
            defects=[DefectCreate(defect_type="scratch", class_id=0, confidence=0.96, camera_id="cam-front-left", bbox={"x1": 410, "y1": 235, "x2": 690, "y2": 310}, severity_rank="C")],
        ),
        InspectionCreate(
            vin="MOCK-VIN-DENT-001",
            model="Demo SUV",
            defects=[DefectCreate(defect_type="dent", class_id=1, confidence=0.91, camera_id="cam-rear-right", bbox={"x1": 1020, "y1": 380, "x2": 1325, "y2": 720}, severity_rank="P")],
        ),
        InspectionCreate(
            vin="MOCK-VIN-PAINT-001",
            model="Demo Hatchback",
            defects=[DefectCreate(defect_type="paint_defect", class_id=2, confidence=0.87, camera_id="cam-roof-top", bbox={"x1": 720, "y1": 145, "x2": 940, "y2": 230}, severity_rank="A")],
        ),
        InspectionCreate(vin="MOCK-VIN-PASS-001", model="Demo Wagon"),
        InspectionCreate(
            vin="MOCK-VIN-SCRATCH-LOW-001",
            model="Demo Sedan",
            defects=[DefectCreate(defect_type="scratch", class_id=0, confidence=0.62, camera_id="cam-front-left", bbox={"x1": 285, "y1": 360, "x2": 510, "y2": 420}, severity_rank="C")],
        ),
        InspectionCreate(
            vin="MOCK-VIN-DENT-LOW-001",
            model="Demo SUV",
            defects=[DefectCreate(defect_type="dent", class_id=1, confidence=0.74, camera_id="cam-rear-right", bbox={"x1": 1150, "y1": 410, "x2": 1390, "y2": 690}, severity_rank="P")],
        ),
        InspectionCreate(
            vin="MOCK-VIN-PAINT-LOW-001",
            model="Demo Hatchback",
            defects=[DefectCreate(defect_type="paint_defect", class_id=2, confidence=0.68, camera_id="cam-roof-top", bbox={"x1": 630, "y1": 210, "x2": 835, "y2": 290}, severity_rank="A")],
        ),
        InspectionCreate(
            vin="MOCK-VIN-SCRATCH-BORDERLINE-001",
            model="Demo Sedan",
            defects=[DefectCreate(defect_type="scratch", class_id=0, confidence=0.79, camera_id="cam-front-left", bbox={"x1": 890, "y1": 285, "x2": 1090, "y2": 345}, severity_rank="C")],
        ),
        InspectionCreate(
            vin="MOCK-VIN-DENT-BORDERLINE-001",
            model="Demo SUV",
            defects=[DefectCreate(defect_type="dent", class_id=1, confidence=0.77, camera_id="cam-rear-right", bbox={"x1": 950, "y1": 430, "x2": 1200, "y2": 710}, severity_rank="P")],
        ),
        InspectionCreate(
            vin="MOCK-VIN-PAINT-BORDERLINE-001",
            model="Demo Hatchback",
            defects=[DefectCreate(defect_type="paint_defect", class_id=2, confidence=0.72, camera_id="cam-roof-top", bbox={"x1": 740, "y1": 175, "x2": 990, "y2": 260}, severity_rank="A")],
        ),
        InspectionCreate(
            vin="MOCK-VIN-SCRATCH-HIGH-001",
            model="Demo Wagon",
            defects=[DefectCreate(defect_type="scratch", class_id=0, confidence=0.84, camera_id="cam-front-left", bbox={"x1": 340, "y1": 460, "x2": 550, "y2": 520}, severity_rank="C")],
        ),
    ]
    return [_create_inspection(request, item) for item in seed]


@router.post("/inspections", response_model=InspectionResponse, status_code=201)
def create_inspection(request: Request, payload: InspectionCreate) -> InspectionResponse:
    return _create_inspection(request, payload)


@router.get("/inspections", response_model=list[InspectionResponse])
def list_inspections(request: Request) -> list[InspectionResponse]:
    rows = request.app.state.database.connection.execute("SELECT * FROM inspections ORDER BY created_at DESC").fetchall()
    return [_inspection_from_row(request, row) for row in rows]


@router.get("/inspections/{inspection_id}", response_model=InspectionResponse)
def get_inspection(request: Request, inspection_id: str) -> InspectionResponse:
    row = request.app.state.database.connection.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return _inspection_from_row(request, row)


def _classifications_for_inspection(request: Request, inspection_id: str) -> list[ClassificationResponse]:
    rows = request.app.state.database.connection.execute(
        "SELECT * FROM classifications WHERE inspection_id = ? ORDER BY created_at, id",
        (inspection_id,),
    ).fetchall()
    return [ClassificationResponse(**dict(row)) for row in rows]


@router.post("/inspections/{inspection_id}/classify", response_model=list[ClassificationResponse])
def classify_inspection(request: Request, inspection_id: str) -> list[ClassificationResponse]:
    database = request.app.state.database
    inspection = database.connection.execute("SELECT id FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")

    database.execute("DELETE FROM classifications WHERE inspection_id = ?", (inspection_id,))
    defects = database.connection.execute("SELECT * FROM defects WHERE inspection_id = ? ORDER BY id", (inspection_id,)).fetchall()
    for defect in defects:
        rule = MOCK_CLASSIFICATION_RULES.get(defect["defect_type"])
        if rule is None:
            continue
        database.execute(
            """INSERT INTO classifications
            (id, inspection_id, defect_id, panel, material, gdt_group,
             tolerance_mm, measurement_mm, severity_rank,
             classification_confidence, source, is_mock, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()), inspection_id, defect["id"], rule["panel"], rule["material"],
                rule["gdt_group"], rule["tolerance_mm"], rule["measurement_mm"],
                rule["severity_rank"], defect["confidence"], "mock_rule_engine", 1,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return _classifications_for_inspection(request, inspection_id)


@router.get("/inspections/{inspection_id}/classifications", response_model=list[ClassificationResponse])
def get_classifications(request: Request, inspection_id: str) -> list[ClassificationResponse]:
    inspection = request.app.state.database.connection.execute("SELECT id FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return _classifications_for_inspection(request, inspection_id)


def _decisions_for_inspection(request: Request, inspection_id: str) -> list[DecisionResponse]:
    rows = request.app.state.database.connection.execute(
        "SELECT * FROM decisions WHERE inspection_id = ? ORDER BY created_at, id",
        (inspection_id,),
    ).fetchall()
    return [
        DecisionResponse(
            id=row["id"],
            inspection_id=row["inspection_id"],
            recommendation=row["recommendation"],
            action=row["action"],
            route=row["route"],
            reason_codes=json.loads(row["reason_codes"]),
            explanation=row["explanation"],
            test_drive_allowed=bool(row["test_drive_allowed"]),
            is_mock=bool(row["is_mock"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


def _calculate_decision(classifications: list, defect_count: int) -> tuple[DecisionRecommendation, str, str, list[str], str, bool]:
    if not classifications:
        if defect_count:
            return (
                DecisionRecommendation.HITL_REQUIRED,
                "QC review required",
                "QC Review",
                ["CLASSIFICATION_MISSING"],
                "A detected defect has no classification result.",
                False,
            )
        return (
            DecisionRecommendation.PASS,
            "Release vehicle",
            "Final Line",
            ["NO_DEFECTS"],
            "No classified defects were found.",
            True,
        )

    reason_codes: list[str] = []
    for item in classifications:
        if item["classification_confidence"] < 0.80:
            reason_codes.append("LOW_CLASSIFICATION_CONFIDENCE")
        if item["measurement_mm"] > item["tolerance_mm"]:
            reason_codes.append("MEASUREMENT_OVER_TOLERANCE")
        if item["severity_rank"] in {"P", "S", "A"}:
            reason_codes.append("HIGH_SEVERITY_RANK")
        if item["material"] == "hot_stamped_steel":
            reason_codes.append("HOT_STAMPED_STEEL")

    reason_codes = list(dict.fromkeys(reason_codes))
    if "LOW_CLASSIFICATION_CONFIDENCE" in reason_codes:
        return (DecisionRecommendation.HITL_REQUIRED, "QC review required", "QC Review", reason_codes, "Classification confidence is below the mock review threshold.", False)
    if reason_codes:
        return (DecisionRecommendation.PLAN_B, "HOLD and send to Rework", "Rework Shop", reason_codes, "The mock rules identified a condition that must not proceed to test drive.", False)
    return (DecisionRecommendation.PLAN_A, "Buffing and test drive", "FNS Buffing Station", ["MINOR_DEFECT_WITHIN_TOLERANCE"], "The defect is within mock tolerance and has sufficient confidence for local buffing.", True)


@router.post("/inspections/{inspection_id}/decide", response_model=DecisionResponse)
def decide_inspection(request: Request, inspection_id: str) -> DecisionResponse:
    database = request.app.state.database
    inspection = database.connection.execute("SELECT id FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    classifications = database.connection.execute(
        "SELECT * FROM classifications WHERE inspection_id = ? ORDER BY created_at, id", (inspection_id,)
    ).fetchall()
    defect_count = database.connection.execute(
        "SELECT COUNT(*) AS count FROM defects WHERE inspection_id = ?", (inspection_id,)
    ).fetchone()["count"]
    recommendation, action, route, reasons, explanation, test_drive = _calculate_decision(classifications, defect_count)
    decision_id = str(uuid4())
    database.execute(
        """INSERT INTO decisions
        (id, inspection_id, recommendation, action, route, reason_codes,
         explanation, test_drive_allowed, is_mock, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            decision_id, inspection_id, recommendation.value, action, route,
            json.dumps(reasons), explanation, int(test_drive), 1,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return _decisions_for_inspection(request, inspection_id)[-1]


@router.get("/inspections/{inspection_id}/decisions", response_model=list[DecisionResponse])
def get_decisions(request: Request, inspection_id: str) -> list[DecisionResponse]:
    inspection = request.app.state.database.connection.execute("SELECT id FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return _decisions_for_inspection(request, inspection_id)


def _hitl_reviews_for_inspection(request: Request, inspection_id: str) -> list[HITLReviewResponse]:
    rows = request.app.state.database.connection.execute(
        "SELECT * FROM hitl_reviews WHERE inspection_id = ? ORDER BY created_at, id",
        (inspection_id,),
    ).fetchall()
    return [HITLReviewResponse(**dict(row)) for row in rows]


@router.post("/inspections/{inspection_id}/hitl/reviews", response_model=HITLReviewResponse, status_code=201)
def create_hitl_review(
    request: Request, inspection_id: str, payload: HITLReviewCreate
) -> HITLReviewResponse:
    database = request.app.state.database
    inspection = database.connection.execute("SELECT id FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    decision = database.connection.execute(
        "SELECT * FROM decisions WHERE inspection_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (inspection_id,),
    ).fetchone()
    if decision is None:
        raise HTTPException(status_code=409, detail="Create a decision before submitting a HITL review")

    original = DecisionRecommendation(decision["recommendation"])
    final = original
    if payload.action == HITLAction.OVERRIDE:
        final = payload.final_recommendation
    elif payload.action == HITLAction.REJECT:
        final = DecisionRecommendation.HITL_REQUIRED

    review_id = str(uuid4())
    database.execute(
        """INSERT INTO hitl_reviews
        (id, inspection_id, decision_id, reviewer, action, original_recommendation,
         final_recommendation, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            review_id,
            inspection_id,
            decision["id"],
            payload.reviewer,
            payload.action.value,
            original.value,
            final.value,
            payload.reason.strip() if payload.reason else None,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    return _hitl_reviews_for_inspection(request, inspection_id)[-1]


@router.get("/inspections/{inspection_id}/hitl/reviews", response_model=list[HITLReviewResponse])
def get_hitl_reviews(request: Request, inspection_id: str) -> list[HITLReviewResponse]:
    inspection = request.app.state.database.connection.execute("SELECT id FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return _hitl_reviews_for_inspection(request, inspection_id)


def _agent_facts(request: Request, inspection_id: str) -> dict:
    database = request.app.state.database
    inspection = database.connection.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    decision = database.connection.execute(
        "SELECT * FROM decisions WHERE inspection_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (inspection_id,),
    ).fetchone()
    if inspection is None or decision is None:
        raise ValueError("Inspection or decision is missing")
    defects = [dict(row) for row in database.connection.execute(
        "SELECT * FROM defects WHERE inspection_id = ? ORDER BY id", (inspection_id,)
    ).fetchall()]
    classifications = [dict(row) for row in database.connection.execute(
        "SELECT * FROM classifications WHERE inspection_id = ? ORDER BY created_at, id", (inspection_id,)
    ).fetchall()]
    for defect in defects:
        for key in ("bbox", "location"):
            if defect.get(key):
                defect[key] = json.loads(defect[key])
    return {
        "inspection": {"vin": inspection["vin"], "model": inspection["model"], "station": inspection["station"]},
        "detections": defects,
        "classifications": classifications,
        "decision": {
            "recommendation": decision["recommendation"],
            "action": decision["action"],
            "route": decision["route"],
            "reason_codes": json.loads(decision["reason_codes"]),
            "explanation": decision["explanation"],
            "test_drive_allowed": bool(decision["test_drive_allowed"]),
            "is_mock": bool(decision["is_mock"]),
        },
    }


@router.post("/inspections/{inspection_id}/run-workflow", response_model=WorkflowRunResponse, status_code=201)
def run_mock_workflow(request: Request, inspection_id: str) -> WorkflowRunResponse:
    inspection = request.app.state.database.connection.execute(
        "SELECT * FROM inspections WHERE id = ?", (inspection_id,)
    ).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")

    detections = _inspection_from_row(request, inspection).defects
    agent = MockQCAgent()
    workflow = agent.run(
        inspection_id=inspection_id,
        detections=detections,
        classify=lambda: classify_inspection(request, inspection_id),
        decide=lambda: decide_inspection(request, inspection_id),
    )
    if is_auto_explain_enabled():
        try:
            answer, _ = explain_qc_case(_agent_facts(request, inspection_id), "vi", None)
            workflow = workflow.model_copy(
                update={"agent_explanation": answer, "agent_explanation_status": "COMPLETED"}
            )
        except LLMNotConfiguredError:
            workflow = workflow.model_copy(update={"agent_explanation_status": "NOT_CONFIGURED"})
        except Exception:
            # The deterministic QC workflow must finish even if the optional LLM is unavailable.
            workflow = workflow.model_copy(update={"agent_explanation_status": "UNAVAILABLE"})
    request.app.state.database.execute(
        "INSERT INTO workflow_runs (id, inspection_id, status, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            workflow.id,
            inspection_id,
            workflow.status.value,
            workflow.model_dump_json(),
            workflow.created_at.isoformat(),
        ),
    )
    return workflow


@router.get("/workflows/{workflow_id}", response_model=WorkflowRunResponse)
def get_workflow_run(request: Request, workflow_id: str) -> WorkflowRunResponse:
    row = request.app.state.database.connection.execute(
        "SELECT result_json FROM workflow_runs WHERE id = ?", (workflow_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return WorkflowRunResponse.model_validate_json(row["result_json"])


@router.get("/inspections/{inspection_id}/workflows/latest", response_model=WorkflowRunResponse)
def get_latest_workflow_run(request: Request, inspection_id: str) -> WorkflowRunResponse:
    inspection = request.app.state.database.connection.execute(
        "SELECT id FROM inspections WHERE id = ?", (inspection_id,)
    ).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    row = request.app.state.database.connection.execute(
        "SELECT result_json FROM workflow_runs WHERE inspection_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (inspection_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No workflow run found for inspection")
    return WorkflowRunResponse.model_validate_json(row["result_json"])


@router.post("/inspections/{inspection_id}/agent/explain", response_model=AgentExplainResponse)
def explain_inspection_with_agent(
    request: Request, inspection_id: str, payload: AgentExplainRequest
) -> AgentExplainResponse:
    database = request.app.state.database
    inspection = database.connection.execute("SELECT * FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    decision = database.connection.execute(
        "SELECT * FROM decisions WHERE inspection_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (inspection_id,),
    ).fetchone()
    if decision is None:
        raise HTTPException(status_code=409, detail="Run the workflow before requesting an agent explanation")
    try:
        answer, model = explain_qc_case(_agent_facts(request, inspection_id), payload.language, payload.question)
    except LLMNotConfiguredError as error:
        raise HTTPException(status_code=503, detail="QC explanation LLM is not configured") from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"QC explanation request failed: {error}") from error
    return AgentExplainResponse(
        inspection_id=inspection_id,
        answer=answer,
        model=model,
        language=payload.language,
    )


@router.get("/mock/yolo-detections", response_model=list[YoloImageResult])
def mock_yolo_detections() -> list[YoloImageResult]:
    """Return serialized detections shaped like a YOLO prediction result."""
    return [
        YoloImageResult(
            image_id="mock-img-scratch-001",
            image_width=1920,
            image_height=1080,
            camera_id="cam-front-left",
            model_name="mock-yolo-qc",
            model_version="mock-1.0",
            detections=[YoloDetection(class_id=0, class_name="scratch", confidence=0.96, bbox={"x1": 410, "y1": 235, "x2": 690, "y2": 310})],
        ),
        YoloImageResult(
            image_id="mock-img-dent-001",
            image_width=1920,
            image_height=1080,
            camera_id="cam-rear-right",
            model_name="mock-yolo-qc",
            model_version="mock-1.0",
            detections=[YoloDetection(class_id=1, class_name="dent", confidence=0.91, bbox={"x1": 1020, "y1": 380, "x2": 1325, "y2": 720})],
        ),
        YoloImageResult(
            image_id="mock-img-paint-001",
            image_width=1920,
            image_height=1080,
            camera_id="cam-roof-top",
            model_name="mock-yolo-qc",
            model_version="mock-1.0",
            detections=[YoloDetection(class_id=2, class_name="paint_defect", confidence=0.87, bbox={"x1": 720, "y1": 145, "x2": 940, "y2": 230})],
        ),
        YoloImageResult(
            image_id="mock-img-pass-001",
            image_width=1920,
            image_height=1080,
            camera_id="cam-front-center",
            model_name="mock-yolo-qc",
            model_version="mock-1.0",
            detections=[],
        ),
    ]
