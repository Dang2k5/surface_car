from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from agent.mock_workflow import MockQCAgent

from .qc_policy import evaluate_demo_qc_policy
from .schemas import (
    ClassificationResponse,
    DecisionRecommendation,
    DecisionResponse,
    DefectCreate,
    DefectResponse,
    HITLAction,
    HITLReviewCreate,
    HITLReviewResponse,
    InspectionCreate,
    InspectionResponse,
    InspectionStatus,
    SimulationCaseResponse,
    SimulationRunRequest,
    SimulationRunResponse,
    WorkflowRunResponse,
    YoloDetection,
    YoloImageResult,
)
from .simulation_cases import TRAIN_SIMULATION_CASES, get_simulation_case

router = APIRouter(prefix="/api")


MOCK_CLASSIFICATION_RULES = {
    "scratch": {"panel": "door_panel", "material": "ordinary_steel", "gdt_group": 3, "tolerance_mm": 0.5, "measurement_mm": 0.2, "severity_rank": "C"},
    "dent": {"panel": "quarter_panel", "material": "hot_stamped_steel", "gdt_group": 1, "tolerance_mm": 0.7, "measurement_mm": 1.1, "severity_rank": "P"},
    "paint_defect": {"panel": "hood_class_a_surface", "material": "coated_steel", "gdt_group": 2, "tolerance_mm": 0.3, "measurement_mm": 0.4, "severity_rank": "A"},
}


def _simulation_case_response(case) -> SimulationCaseResponse:
    return SimulationCaseResponse(
        id=case.id,
        image_url=f"/assets/train/{case.filename}",
        filename=case.filename,
        vehicle_id=case.vehicle_id,
        model=case.model,
        defect_type=case.defect_type,
        confidence=case.confidence,
        camera_id=case.camera_id,
        panel=case.panel,
        bbox=case.bbox,
        severity_rank=case.severity_rank,
        visual_note=case.visual_note,
        graph_scenario=case.graph_scenario,
        case_title=case.case_title,
        expected_path=case.expected_path,
        expected_outcome=case.expected_outcome,
        annotation_source="demo_annotation_from_local_train_image",
    )


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
        source_image_url=row["source_image_url"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        defects=response_defects,
    )


def _create_inspection(
    request: Request,
    payload: InspectionCreate,
    *,
    auto_run: bool = True,
    source_image_url: str | None = None,
) -> InspectionResponse:
    database = request.app.state.database
    inspection_id = str(uuid4())
    created_at = datetime.now(UTC).isoformat()
    database.execute(
        """INSERT INTO inspections
        (id, vin, model, station, source_image_url, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            inspection_id,
            payload.vin,
            payload.model,
            payload.station,
            source_image_url,
            InspectionStatus.OPEN.value,
            created_at,
        ),
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
    if auto_run:
        run_mock_workflow(request, inspection_id)
    return inspection


@router.post("/mock/seed", response_model=list[InspectionResponse])
def seed_mock_data(request: Request, reset: bool = False) -> list[InspectionResponse]:
    """Reset and create only image-backed train simulation records."""
    database = request.app.state.database
    if reset:
        database.execute("DELETE FROM hitl_reviews")
        database.execute("DELETE FROM workflow_runs")
        database.execute("DELETE FROM decisions")
        database.execute("DELETE FROM classifications")
        database.execute("DELETE FROM defects")
        database.execute("DELETE FROM inspections")
    existing = database.connection.execute(
        "SELECT COUNT(*) AS count FROM inspections WHERE source_image_url IS NOT NULL"
    ).fetchone()["count"]
    if existing:
        rows = database.connection.execute(
            """SELECT * FROM inspections i
            WHERE source_image_url IS NOT NULL
              AND EXISTS (SELECT 1 FROM decisions d WHERE d.inspection_id = i.id)
            ORDER BY created_at"""
        ).fetchall()
        return [_inspection_from_row(request, row) for row in rows]
    return [
        run_train_image_simulation(request, case.id, None).inspection
        for case in TRAIN_SIMULATION_CASES
    ]


@router.get("/simulations/cases", response_model=list[SimulationCaseResponse])
def list_simulation_cases() -> list[SimulationCaseResponse]:
    """Expose local train images with explicitly mock annotations for demo use."""
    return [_simulation_case_response(case) for case in TRAIN_SIMULATION_CASES]


@router.post("/simulations/{case_id}/run", response_model=SimulationRunResponse, status_code=201)
def run_train_image_simulation(
    request: Request, case_id: str, payload: SimulationRunRequest | None = None
) -> SimulationRunResponse:
    """Simulate the detector payload for a selected local image, then orchestrate it."""
    case = get_simulation_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Simulation case not found")
    inspection = _create_inspection(
        request,
        InspectionCreate(
            vin=case.vehicle_id,
            model=case.model,
            station="FNS Line - HA",
            defects=[
                DefectCreate(
                    defect_type=case.defect_type,
                    class_id={"scratch": 0, "dent": 1, "paint_defect": 2}[case.defect_type.value],
                    confidence=case.confidence,
                    camera_id=case.camera_id,
                    bbox=case.bbox,
                    image_width=640,
                    image_height=640,
                    model_name="mock-yolo-qc-train-image",
                    model_version="demo-annotation-1.0",
                    severity_rank=case.severity_rank,
                )
            ],
        ),
        auto_run=False,
        source_image_url=f"/assets/train/{case.filename}",
    )
    workflow = run_mock_workflow(
        request,
        inspection.id,
        fail_at_step=payload.fail_at_step if payload else None,
    )
    return SimulationRunResponse(
        case=_simulation_case_response(case),
        inspection=inspection,
        workflow=workflow,
    )


@router.post("/inspections", response_model=InspectionResponse, status_code=201)
def create_inspection(request: Request, payload: InspectionCreate) -> InspectionResponse:
    return _create_inspection(request, payload)


@router.get("/inspections", response_model=list[InspectionResponse])
def list_inspections(request: Request) -> list[InspectionResponse]:
    rows = request.app.state.database.connection.execute(
        """SELECT * FROM inspections i
        WHERE source_image_url IS NOT NULL
          AND EXISTS (SELECT 1 FROM decisions d WHERE d.inspection_id = i.id)
        ORDER BY created_at DESC"""
    ).fetchall()
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
                datetime.now(UTC).isoformat(),
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
            action_code=row["action_code"],
            action=row["action"],
            route=row["route"],
            reason_codes=json.loads(row["reason_codes"]),
            policy_refs=json.loads(row["policy_refs"]),
            method_steps=json.loads(row["method_steps"]),
            explanation=row["explanation"],
            test_drive_allowed=bool(row["test_drive_allowed"]),
            is_mock=bool(row["is_mock"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in rows
    ]


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
    outcome = evaluate_demo_qc_policy(classifications, defect_count)
    decision_id = str(uuid4())
    database.execute(
        """INSERT INTO decisions
        (id, inspection_id, recommendation, action_code, action, route, reason_codes,
         policy_refs, method_steps, explanation, test_drive_allowed, is_mock, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            decision_id, inspection_id, outcome.recommendation.value, outcome.action_code,
            outcome.action, outcome.route, json.dumps(outcome.reason_codes),
            json.dumps(outcome.policy_refs), json.dumps(outcome.method_steps),
            outcome.explanation, int(outcome.test_drive_allowed), 1,
            datetime.now(UTC).isoformat(),
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
        final = DecisionRecommendation.MANUAL_VISUAL_REINSPECTION

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
            datetime.now(UTC).isoformat(),
        ),
    )
    return _hitl_reviews_for_inspection(request, inspection_id)[-1]


@router.get("/inspections/{inspection_id}/hitl/reviews", response_model=list[HITLReviewResponse])
def get_hitl_reviews(request: Request, inspection_id: str) -> list[HITLReviewResponse]:
    inspection = request.app.state.database.connection.execute("SELECT id FROM inspections WHERE id = ?", (inspection_id,)).fetchone()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return _hitl_reviews_for_inspection(request, inspection_id)


@router.post("/inspections/{inspection_id}/run-workflow", response_model=WorkflowRunResponse, status_code=201)
def run_mock_workflow(
    request: Request, inspection_id: str, fail_at_step: str | None = None
) -> WorkflowRunResponse:
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
        fail_at_step=fail_at_step,
    )
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
