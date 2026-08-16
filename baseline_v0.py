"""Baseline MVP cho Visual QC Agent.

Mục tiêu:
- API /api/inspect tạo dữ liệu giả lập 5 mặt xe.
- Rule Engine đánh giá PASS / FAIL / REVIEW.
- API /api/override phục vụ Human-In-The-Loop cho luồng REVIEW.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Visual QC Agent - Baseline v0",
    description="MVP đầu tiên cho hệ thống kiểm tra lỗi xe bằng AI",
    version="0.1.0",
)

SURFACE_NAMES = ["front", "rear", "left", "right", "roof"]
DEFECT_TYPES = ["Xước", "Móp", "Hỏng sơn"]

# Bộ nhớ tạm lưu Override và Lịch sử Scan
OVERRIDE_STORE: dict[str, dict[str, Any]] = {}
INSPECTION_HISTORY: list[dict[str, Any]] = []


class InspectionRequest(BaseModel):
    seed: int | None = Field(default=None, description="Seed dữ liệu giả lập")
    use_random: bool = Field(default=True, description="Dùng dữ liệu ngẫu nhiên")


class OverrideRequest(BaseModel):
    surface: str = Field(..., description="Mặt xe cần override (front, rear,...)")
    status: str = Field(..., description="Trạng thái mới: PASS hoặc FAIL")
    reason: str | None = Field(default=None, description="Lý do override")


def _generate_bbox() -> list[int]:
    return [random.randint(0, 100), random.randint(0, 100), random.randint(20, 80), random.randint(20, 80)]


def _rule_engine(surface_data: dict[str, Any]) -> dict[str, Any]:
    image_quality = surface_data["image_quality"]
    detections = surface_data.get("detections", [])

    if image_quality < 70:
        return {
            "status": "REVIEW",
            "reason": f"Ảnh chất lượng thấp ({image_quality}%), cần QC kiểm tra thủ công.",
            "quality": image_quality,
        }

    if not detections:
        return {
            "status": "PASS",
            "reason": f"Ảnh chất lượng {image_quality}% và không phát hiện lỗi nào.",
            "quality": image_quality,
        }

    max_confidence = max(det["confidence"] for det in detections)
    max_size = max(det["size_mm"] for det in detections)

    if max_confidence >= 0.8 and max_size >= 2.0:
        status = "FAIL"
        reason = f"Phát hiện lỗi rõ ràng (Confidence={max_confidence:.2f}, Size={max_size:.2f}mm)."
    else:
        status = "REVIEW"
        reason = f"Lỗi nằm ở ranh giới nghi ngờ (Confidence={max_confidence:.2f}, Size={max_size:.2f}mm). Cần QC xác nhận."

    return {"status": status, "reason": reason, "quality": image_quality}


def _build_surface_payload(surface_name: str, seed: int | None = None) -> dict[str, Any]:
    if seed is not None:
        random.seed(seed + SURFACE_NAMES.index(surface_name))

    image_quality = random.randint(60, 100)
    detections: list[dict[str, Any]] = []

    if random.random() < 0.7:
        for _ in range(random.randint(1, 2)):
            detections.append(
                {
                    "type": random.choice(DEFECT_TYPES),
                    "confidence": round(random.uniform(0.5, 0.99), 2),
                    "size_mm": round(random.uniform(1.0, 5.0), 2),
                    "bounding_box": _generate_bbox(),
                }
            )

    surface_data = {"surface": surface_name, "image_quality": image_quality, "detections": detections}
    rule_result = _rule_engine(surface_data)
    
    status = rule_result["status"]
    reason = rule_result["reason"]

    # Ưu tiên Override từ QC nếu có
    if surface_name in OVERRIDE_STORE:
        override = OVERRIDE_STORE[surface_name]
        status = override["status"]
        reason = f"[QC OVERRIDE]: {override['reason']}"

    return {
        "surface": surface_name,
        "image_quality": image_quality,
        "detections": detections,
        "status": status,
        "reason": reason,
        "quality": rule_result["quality"],
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.post("/api/inspect")
async def inspect_vehicle(request: InspectionRequest | None = None) -> dict[str, Any]:
    if request is None:
        request = InspectionRequest()

    # Xóa override cũ khi scan xe mới
    OVERRIDE_STORE.clear()

    surfaces = [_build_surface_payload(name, seed=request.seed) for name in SURFACE_NAMES]
    result = {
        "inspection_id": f"CAR-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "surfaces": surfaces,
    }
    
    INSPECTION_HISTORY.append(result)

    print("\n" + "="*50)
    print(f"🚗 [NEW SCAN] ID: {result['inspection_id']}")
    for s in surfaces:
        print(f"  • {s['surface'].upper()}: {s['status']} | Quality: {s['quality']}%")
    print("="*50 + "\n")

    return result


@app.post("/api/override")
async def override_result(payload: OverrideRequest) -> dict[str, Any]:
    if payload.surface not in SURFACE_NAMES:
        raise HTTPException(status_code=400, detail="surface không hợp lệ")

    OVERRIDE_STORE[payload.surface] = {
        "status": payload.status,
        "reason": payload.reason or f"QC xác nhận {payload.status}",
    }

    # IN LOG XÁC NHẬN RÕ RÀNG RA TERMINAL
    print("\n" + "✍️ "*15)
    print(f"📌 [QC HITL ACTION]")
    print(f"   • Mặt xe: {payload.surface.upper()}")
    print(f"   • Quyết định mới của QC: {payload.status}")
    print(f"   • Lý do: {OVERRIDE_STORE[payload.surface]['reason']}")
    print("✍️ "*15 + "\n")

    return {
        "message": "Override thành công",
        "surface": payload.surface,
        "status": payload.status,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("baseline_v0:app", host="0.0.0.0", port=8000, reload=True)