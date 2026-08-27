from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from .auth import CurrentUser, get_current_user, require_role
from .qc_schemas import (
    LotCreate,
    LotProductAllocate,
    LotUpdate,
    ShiftCreate,
    ShiftUpdate,
    StationCreate,
    StationUpdate,
)

router = APIRouter(prefix="/api/catalog", tags=["Shift & lot catalog"])


@router.get("/shifts", response_model=list[dict[str, Any]])
def list_shifts(
    request: Request,
    active_only: bool = True,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return request.app.state.database.list_shifts(active_only=active_only)


@router.post("/shifts", response_model=dict[str, Any], status_code=201)
def create_shift(
    request: Request,
    payload: ShiftCreate,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    try:
        return request.app.state.database.create_shift(payload.model_dump())
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Ca làm việc đã tồn tại.") from error


@router.patch("/shifts/{shift_id}", response_model=dict[str, Any])
def update_shift(
    shift_id: str,
    request: Request,
    payload: ShiftUpdate,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    updated = request.app.state.database.update_shift(
        shift_id.strip().upper(), payload.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy ca làm việc.")
    return updated


@router.get("/lots", response_model=list[dict[str, Any]])
def list_lots(
    request: Request,
    active_only: bool = True,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return request.app.state.database.list_lots(active_only=active_only)


@router.post("/lots", response_model=dict[str, Any], status_code=201)
def create_lot(
    request: Request,
    payload: LotCreate,
    # Unlike shifts/stations (fixed organizational structure, Supervisor-only), any authenticated
    # role may create a lot — QC_OPERATOR is the one on the floor who first sees a new lot start,
    # typically while filling out the inspection form itself.
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    database = request.app.state.database
    if database.get_station(payload.station_id) is None:
        raise HTTPException(status_code=422, detail=f"Không tìm thấy trạm: {payload.station_id}")
    if database.get_shift(payload.shift_id) is None:
        raise HTTPException(status_code=422, detail=f"Không tìm thấy ca: {payload.shift_id}")
    try:
        return database.create_lot(payload.model_dump())
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Lô sản xuất đã tồn tại.") from error


@router.patch("/lots/{lot_id}", response_model=dict[str, Any])
def update_lot(
    lot_id: str,
    request: Request,
    payload: LotUpdate,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    database = request.app.state.database
    if payload.station_id is not None and database.get_station(payload.station_id) is None:
        raise HTTPException(status_code=422, detail=f"Không tìm thấy trạm: {payload.station_id}")
    if payload.shift_id is not None and database.get_shift(payload.shift_id) is None:
        raise HTTPException(status_code=422, detail=f"Không tìm thấy ca: {payload.shift_id}")
    if payload.quantity is not None:
        used = database.count_lot_products(lot_id.strip())
        if payload.quantity < used:
            raise HTTPException(
                status_code=422,
                detail=f"Không thể giảm số lượng xuống dưới {used} (đã sinh {used} mã sản phẩm).",
            )
    updated = database.update_lot(lot_id.strip(), payload.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lô sản xuất.")
    return updated


@router.get("/lots/{lot_id}/products", response_model=list[dict[str, Any]])
def list_lot_products(
    lot_id: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return request.app.state.database.list_lot_products(lot_id.strip())


@router.post("/lots/{lot_id}/products", response_model=dict[str, Any], status_code=201)
def create_lot_product(
    lot_id: str,
    request: Request,
    payload: LotProductAllocate,
    # Same rationale as create_lot: the Inspector allocates the next product code themselves
    # while filling out the inspection form, as the vehicle passes the camera.
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    database = request.app.state.database
    lot = database.get_lot(lot_id.strip())
    if lot is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lô sản xuất.")
    if not lot.get("active"):
        raise HTTPException(status_code=422, detail="Lô đã đóng, không thể sinh thêm mã sản phẩm.")
    used = database.count_lot_products(lot_id.strip())
    quantity = int(lot.get("quantity") or 0)
    if used >= quantity:
        raise HTTPException(
            status_code=422, detail="Lô đã đủ số lượng, không thể sinh thêm mã sản phẩm."
        )
    return database.allocate_lot_product(lot_id.strip(), payload.vehicle_model)


@router.get("/stations/options", response_model=list[dict[str, Any]])
def list_station_options(request: Request) -> list[dict[str, Any]]:
    """Active stations as (id, name) pairs — the only catalog endpoint reachable without a
    token, because the sign-up form has to offer a station before an account exists to
    authenticate with (frontend/src/routes/login.tsx). Deliberately narrower than
    `list_stations`: no timestamps, no inactive stations, nothing beyond the label a new
    inspector picks from."""
    return [
        {"station_id": station["station_id"], "name": station["name"]}
        for station in request.app.state.database.list_stations(active_only=True)
    ]


@router.get("/stations", response_model=list[dict[str, Any]])
def list_stations(
    request: Request,
    active_only: bool = True,
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return request.app.state.database.list_stations(active_only=active_only)


@router.post("/stations", response_model=dict[str, Any], status_code=201)
def create_station(
    request: Request,
    payload: StationCreate,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    try:
        return request.app.state.database.create_station(payload.model_dump())
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Trạm đã tồn tại.") from error


@router.patch("/stations/{station_id}", response_model=dict[str, Any])
def update_station(
    station_id: str,
    request: Request,
    payload: StationUpdate,
    user: CurrentUser = Depends(require_role("QC_SUPERVISOR")),
) -> dict[str, Any]:
    updated = request.app.state.database.update_station(
        station_id.strip(), payload.model_dump(exclude_unset=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy trạm.")
    return updated
