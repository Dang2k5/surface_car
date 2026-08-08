from __future__ import annotations

from dataclasses import dataclass

from .schemas import DefectType


@dataclass(frozen=True)
class SimulationCase:
    """A transparent mock annotation layered over a local train image.

    The supplied image folder has no label file in this repository. The defect
    type, confidence, bbox, and QC context below are demo annotations inferred
    for simulation only, not ground-truth model labels.
    """

    id: str
    filename: str
    vehicle_id: str
    model: str
    defect_type: DefectType
    confidence: float
    camera_id: str
    panel: str
    bbox: dict[str, int]
    severity_rank: str
    visual_note: str
    graph_scenario: str
    case_title: str
    expected_path: str
    expected_outcome: str


TRAIN_SIMULATION_CASES: tuple[SimulationCase, ...] = (
    SimulationCase(
        id="train-128-dent",
        filename="128_PNG.rf.837e038ddb823b1807f5dcd8e2642e16.jpg",
        vehicle_id="VN8921-2026",
        model="SUV EV",
        defect_type=DefectType.DENT,
        confidence=0.91,
        camera_id="cam-hood-left",
        panel="hood_outer",
        bbox={"x1": 300, "y1": 150, "x2": 510, "y2": 355},
        severity_rank="P",
        visual_note="Visible circular deformation/reflection anomaly on painted panel.",
        graph_scenario="high_confidence",
        case_title="Móp rõ ràng — xác nhận tự động",
        expected_path="Detect → Assess → Recommend → Save",
        expected_outcome="Giữ xe và chuyển Body Repair đánh giá kỹ thuật",
    ),
    SimulationCase(
        id="train-1-dent",
        filename="1_PNG.rf.75e27f4917aefc9662a0551a5e274b0e.jpg",
        vehicle_id="VN9011-2026",
        model="SUV EV",
        defect_type=DefectType.DENT,
        confidence=0.88,
        camera_id="cam-door-left",
        panel="front_door_outer",
        bbox={"x1": 325, "y1": 245, "x2": 565, "y2": 525},
        severity_rank="P",
        visual_note="Broad distortion is visible across the rear door panel.",
        graph_scenario="high_confidence",
        case_title="Móp cửa trước — xác nhận tự động",
        expected_path="Detect → Assess → Recommend → Save",
        expected_outcome="Giữ xe và chuyển Body Repair đánh giá kỹ thuật",
    ),
    SimulationCase(
        id="train-21-scratch",
        filename="21_PNG.rf.cc6bbeaaba838656af9d4945bddc1129.jpg",
        vehicle_id="VN9012-2026",
        model="Sedan HEV",
        defect_type=DefectType.SCRATCH,
        confidence=0.68,
        camera_id="cam-headlamp-right",
        panel="front_fender_outer",
        bbox={"x1": 225, "y1": 185, "x2": 500, "y2": 395},
        severity_rank="C",
        visual_note="Multiple superficial scuff marks are visible near the lamp edge.",
        graph_scenario="medium_confirmed",
        case_title="Xước nhẹ — xác minh rồi xác nhận",
        expected_path="Detect → Assess → Verify → Assess → Recommend",
        expected_outcome="Đánh bóng có kiểm soát và kiểm tra lại",
    ),
    SimulationCase(
        id="train-255-dent",
        filename="255_PNG.rf.59081b738bd1a5c3d8044e659652eb6b.jpg",
        vehicle_id="VN9013-2026",
        model="Hatchback EV",
        defect_type=DefectType.DENT,
        confidence=0.63,
        camera_id="cam-quarter-left",
        panel="rear_quarter_outer",
        bbox={"x1": 80, "y1": 125, "x2": 350, "y2": 465},
        severity_rank="UNCONFIRMED",
        visual_note="Subtle reflection distortion requires repeated verification.",
        graph_scenario="verify_uncertain",
        case_title="Biến dạng phản quang — xác minh hai lần",
        expected_path="Detect → Assess → Verify ×2 → HITL",
        expected_outcome="Tạm dừng để QC xác nhận trực tiếp",
    ),
    SimulationCase(
        id="train-261-clear",
        filename="261_PNG.rf.31581225cadafc5c822224c2b410aa2c.jpg",
        vehicle_id="VN9014-2026",
        model="SUV ICE",
        defect_type=DefectType.PAINT_DEFECT,
        confidence=0.98,
        camera_id="cam-door-right",
        panel="front_door_outer",
        bbox={"x1": 1, "y1": 1, "x2": 2, "y2": 2},
        severity_rank="NONE",
        visual_note="No repeatable scratch, dent, or paint anomaly is confirmed in the panel view.",
        graph_scenario="no_defect",
        case_title="Bề mặt cửa không xác nhận lỗi — PASS",
        expected_path="Detect → Assess → Save",
        expected_outcome="Cho xe đi tiếp tới cổng chất lượng kế tiếp",
    ),
    SimulationCase(
        id="train-381-uncertain",
        filename="381_PNG.rf.f784ccf8abea3697a0bcf966c7878fed.jpg",
        vehicle_id="VN9015-2026",
        model="Sedan EV",
        defect_type=DefectType.DENT,
        confidence=0.34,
        camera_id="cam-wheel-arch-right",
        panel="rear_quarter_outer",
        bbox={"x1": 95, "y1": 105, "x2": 390, "y2": 365},
        severity_rank="UNCONFIRMED",
        visual_note="Low-contrast wheel-arch reflection cannot be classified safely by the first pass.",
        graph_scenario="low_confidence",
        case_title="Tín hiệu vòm bánh mơ hồ — chuyển QC",
        expected_path="Detect → Assess → HITL",
        expected_outcome="Tạm dừng do confidence dưới ngưỡng an toàn",
    ),
    SimulationCase(
        id="train-389-dent",
        filename="389_PNG.rf.9682c970a1b56c3d5835dcaa0ea4ab8d.jpg",
        vehicle_id="VN9016-2026",
        model="Crossover EV",
        defect_type=DefectType.DENT,
        confidence=0.95,
        camera_id="cam-wheel-arch-left",
        panel="front_fender_outer",
        bbox={"x1": 225, "y1": 165, "x2": 455, "y2": 415},
        severity_rank="P",
        visual_note="Sharp inward deformation is visible above the wheel opening.",
        graph_scenario="high_confidence",
        case_title="Móp vè bánh rõ ràng — giữ xe",
        expected_path="Detect → Assess → Recommend → Save",
        expected_outcome="Giữ xe và chuyển Body Repair đánh giá kỹ thuật",
    ),
    SimulationCase(
        id="train-860-dent",
        filename="860_PNG.rf.ca1d732b3c2bd06ec17a12d8b97ab46a.jpg",
        vehicle_id="VN9017-2026",
        model="Sedan ICE",
        defect_type=DefectType.DENT,
        confidence=0.92,
        camera_id="cam-door-handle-right",
        panel="front_door_outer",
        bbox={"x1": 365, "y1": 200, "x2": 610, "y2": 485},
        severity_rank="P",
        visual_note="Localized door skin dent is visible beside the handle and shut line.",
        graph_scenario="high_confidence",
        case_title="Móp sát tay nắm cửa — giữ xe",
        expected_path="Detect → Assess → Recommend → Save",
        expected_outcome="Giữ xe và chuyển Body Repair đánh giá kỹ thuật",
    ),
)


def get_simulation_case(case_id: str) -> SimulationCase | None:
    return next((case for case in TRAIN_SIMULATION_CASES if case.id == case_id), None)
