import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  Badge,
  Btn,
  EmptyState,
  PageHeader,
  Panel,
  Table,
  Td,
  Th,
  Tr,
} from "@/components/supervisor/ui";
import {
  useCreateLot,
  useCreateShift,
  useCreateStation,
  useLots,
  useShifts,
  useStations,
  useUpdateLot,
  useUpdateShift,
  useUpdateStation,
} from "@/lib/queries";

export const Route = createFileRoute("/supervisor/catalogs")({
  head: () => ({
    meta: [{ title: "Ca, Lô & Trạm QC — QC Supervisor" }],
  }),
  component: Catalogs,
});

function isActive(value: boolean | number): boolean {
  return value === true || value === 1;
}

const editableInputClass =
  "h-7 w-full min-w-0 rounded-sm border border-info/40 bg-surface px-1.5 text-xs text-foreground";

function ShiftsPanel() {
  const shiftsQuery = useShifts(false);
  const createShift = useCreateShift();
  const updateShift = useUpdateShift();

  const [shiftId, setShiftId] = useState("");
  const [name, setName] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [error, setError] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editStart, setEditStart] = useState("");
  const [editEnd, setEditEnd] = useState("");

  const shifts = shiftsQuery.data ?? [];

  async function handleCreate() {
    setError("");
    if (!shiftId.trim() || !name.trim()) {
      setError("Cần nhập mã ca và tên ca.");
      return;
    }
    try {
      await createShift.mutateAsync({
        shift_id: shiftId.trim(),
        name: name.trim(),
        ...(startTime ? { start_time: startTime } : {}),
        ...(endTime ? { end_time: endTime } : {}),
      });
      setShiftId("");
      setName("");
      setStartTime("");
      setEndTime("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tạo ca thất bại.");
    }
  }

  function startEdit(s: (typeof shifts)[number]) {
    setEditingId(s.shift_id);
    setEditName(s.name);
    setEditStart(s.start_time);
    setEditEnd(s.end_time);
  }

  async function saveEdit(shiftIdToSave: string) {
    if (!editName.trim()) return;
    await updateShift.mutateAsync({
      shiftId: shiftIdToSave,
      payload: { name: editName.trim(), start_time: editStart, end_time: editEnd },
    });
    setEditingId(null);
  }

  return (
    <Panel title="Ca làm việc">
      <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-5">
        <input
          value={shiftId}
          onChange={(e) => setShiftId(e.target.value)}
          placeholder="Mã ca"
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 font-mono text-xs text-foreground placeholder:text-muted-foreground"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Tên hiển thị"
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 text-xs text-foreground placeholder:text-muted-foreground"
        />
        <input
          type="time"
          value={startTime}
          onChange={(e) => setStartTime(e.target.value)}
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 text-xs text-foreground"
        />
        <input
          type="time"
          value={endTime}
          onChange={(e) => setEndTime(e.target.value)}
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 text-xs text-foreground"
        />
        <Btn variant="solid" onClick={handleCreate} disabled={createShift.isPending}>
          {createShift.isPending ? "Đang thêm…" : "+ Thêm ca"}
        </Btn>
      </div>
      {error ? <p className="mb-3 text-[11px] text-destructive">{error}</p> : null}

      {shiftsQuery.isPending ? (
        <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
          Đang tải…
        </div>
      ) : shifts.length === 0 ? (
        <EmptyState title="Chưa có ca nào" description="Thêm ca làm việc đầu tiên ở trên." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Mã ca</Th>
              <Th>Tên</Th>
              <Th>Giờ bắt đầu</Th>
              <Th>Giờ kết thúc</Th>
              <Th>Trạng thái</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {shifts.map((s) => {
              const editing = editingId === s.shift_id;
              return (
                <Tr key={s.shift_id}>
                  <Td className="num">{s.shift_id}</Td>
                  <Td>
                    {editing ? (
                      <input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className={editableInputClass}
                      />
                    ) : (
                      s.name
                    )}
                  </Td>
                  <Td className="num">
                    {editing ? (
                      <input
                        type="time"
                        value={editStart}
                        onChange={(e) => setEditStart(e.target.value)}
                        className={editableInputClass}
                      />
                    ) : (
                      s.start_time || "—"
                    )}
                  </Td>
                  <Td className="num">
                    {editing ? (
                      <input
                        type="time"
                        value={editEnd}
                        onChange={(e) => setEditEnd(e.target.value)}
                        className={editableInputClass}
                      />
                    ) : (
                      s.end_time || "—"
                    )}
                  </Td>
                  <Td>
                    <Badge tone={isActive(s.active) ? "pass" : "neutral"}>
                      {isActive(s.active) ? "Đang dùng" : "Đã tắt"}
                    </Badge>
                  </Td>
                  <Td>
                    {editing ? (
                      <div className="flex gap-1.5">
                        <Btn
                          variant="solid"
                          size="xs"
                          disabled={updateShift.isPending}
                          onClick={() => void saveEdit(s.shift_id)}
                        >
                          Lưu
                        </Btn>
                        <Btn variant="outline" size="xs" onClick={() => setEditingId(null)}>
                          Hủy
                        </Btn>
                      </div>
                    ) : (
                      <div className="flex gap-1.5">
                        <Btn variant="outline" size="xs" onClick={() => startEdit(s)}>
                          Sửa
                        </Btn>
                        <Btn
                          variant={isActive(s.active) ? "danger" : "success"}
                          size="xs"
                          disabled={updateShift.isPending}
                          onClick={() =>
                            updateShift.mutate({
                              shiftId: s.shift_id,
                              payload: { active: !isActive(s.active) },
                            })
                          }
                        >
                          {isActive(s.active) ? "Tắt" : "Bật lại"}
                        </Btn>
                      </div>
                    )}
                  </Td>
                </Tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}

function LotsPanel() {
  const lotsQuery = useLots(false);
  const stationsQuery = useStations(false);
  const shiftsQuery = useShifts(false);
  const createLot = useCreateLot();
  const updateLot = useUpdateLot();

  const [lotId, setLotId] = useState("");
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [stationId, setStationId] = useState("");
  const [shiftId, setShiftId] = useState("");
  const [productModel, setProductModel] = useState("");
  const [quantity, setQuantity] = useState("");
  const [error, setError] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editNote, setEditNote] = useState("");
  const [editStationId, setEditStationId] = useState("");
  const [editShiftId, setEditShiftId] = useState("");
  const [editProductModel, setEditProductModel] = useState("");
  const [editQuantity, setEditQuantity] = useState("");

  const lots = lotsQuery.data ?? [];
  const stations = stationsQuery.data ?? [];
  const shifts = shiftsQuery.data ?? [];
  const stationById = new Map(stations.map((s) => [s.station_id, s]));
  const shiftById = new Map(shifts.map((s) => [s.shift_id, s]));

  async function handleCreate() {
    setError("");
    const quantityNum = Number(quantity);
    if (!lotId.trim() || !name.trim() || !stationId || !shiftId) {
      setError("Cần nhập mã lô, tên lô và chọn Trạm + Ca sản xuất ra lô này.");
      return;
    }
    if (!productModel.trim()) {
      setError("Cần nhập Model sản phẩm.");
      return;
    }
    if (!quantity || !Number.isInteger(quantityNum) || quantityNum < 1) {
      setError("Cần nhập Số lượng (số nguyên >= 1).");
      return;
    }
    try {
      await createLot.mutateAsync({
        lot_id: lotId.trim(),
        name: name.trim(),
        station_id: stationId,
        shift_id: shiftId,
        product_model: productModel.trim(),
        quantity: quantityNum,
        ...(note.trim() ? { note: note.trim() } : {}),
      });
      setLotId("");
      setName("");
      setNote("");
      setProductModel("");
      setQuantity("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tạo lô thất bại.");
    }
  }

  function startEdit(l: (typeof lots)[number]) {
    setEditingId(l.lot_id);
    setEditName(l.name);
    setEditNote(l.note);
    setEditStationId(l.station_id ?? "");
    setEditShiftId(l.shift_id ?? "");
    setEditProductModel(l.product_model);
    setEditQuantity(String(l.quantity ?? 0));
  }

  async function saveEdit(lotIdToSave: string) {
    if (!editStationId || !editShiftId || !editName.trim() || !editProductModel.trim()) return;
    const quantityNum = Number(editQuantity);
    await updateLot.mutateAsync({
      lotId: lotIdToSave,
      payload: {
        name: editName.trim(),
        note: editNote,
        station_id: editStationId,
        shift_id: editShiftId,
        product_model: editProductModel.trim(),
        ...(Number.isInteger(quantityNum) && quantityNum >= 1 ? { quantity: quantityNum } : {}),
      },
    });
    setEditingId(null);
  }

  return (
    <Panel title="Lô sản xuất">
      <div className="mb-4 grid grid-cols-1 gap-2 md:grid-cols-4">
        <input
          value={lotId}
          onChange={(e) => setLotId(e.target.value)}
          placeholder="Mã lô"
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 font-mono text-xs text-foreground placeholder:text-muted-foreground"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Tên lô"
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 text-xs text-foreground placeholder:text-muted-foreground"
        />
        <select
          value={stationId}
          onChange={(e) => setStationId(e.target.value)}
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 text-xs text-foreground"
        >
          <option value="">Trạm sản xuất</option>
          {stations.map((s) => (
            <option key={s.station_id} value={s.station_id}>
              {s.name}
            </option>
          ))}
        </select>
        <select
          value={shiftId}
          onChange={(e) => setShiftId(e.target.value)}
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 text-xs text-foreground"
        >
          <option value="">Ca sản xuất</option>
          {shifts.map((s) => (
            <option key={s.shift_id} value={s.shift_id}>
              {s.name}
            </option>
          ))}
        </select>
        <input
          value={productModel}
          onChange={(e) => setProductModel(e.target.value)}
          placeholder="Model sản phẩm"
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 font-mono text-xs text-foreground placeholder:text-muted-foreground"
        />
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Ghi chú (tùy chọn)"
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 text-xs text-foreground placeholder:text-muted-foreground"
        />
        <input
          type="number"
          min={1}
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="Số lượng"
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 font-mono text-xs text-foreground placeholder:text-muted-foreground"
        />
        <Btn variant="solid" onClick={handleCreate} disabled={createLot.isPending}>
          {createLot.isPending ? "Đang thêm…" : "+ Thêm lô"}
        </Btn>
      </div>
      {error ? <p className="mb-3 text-[11px] text-destructive">{error}</p> : null}

      {lotsQuery.isPending ? (
        <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
          Đang tải…
        </div>
      ) : lots.length === 0 ? (
        <EmptyState title="Chưa có lô nào" description="Thêm lô sản xuất đầu tiên ở trên." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Mã lô</Th>
              <Th>Tên lô</Th>
              <Th>Trạm</Th>
              <Th>Ca</Th>
              <Th>Model sản phẩm</Th>
              <Th>Số lượng</Th>
              <Th>Ghi chú</Th>
              <Th>Trạng thái</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {lots.map((l) => {
              const editing = editingId === l.lot_id;
              return (
                <Tr key={l.lot_id}>
                  <Td className="num">{l.lot_id}</Td>
                  <Td>
                    {editing ? (
                      <input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className={editableInputClass}
                      />
                    ) : (
                      l.name || "—"
                    )}
                  </Td>
                  <Td>
                    {editing ? (
                      <select
                        value={editStationId}
                        onChange={(e) => setEditStationId(e.target.value)}
                        className={editableInputClass}
                      >
                        {stations.map((s) => (
                          <option key={s.station_id} value={s.station_id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                    ) : l.station_id ? (
                      (stationById.get(l.station_id)?.name ?? l.station_id)
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td>
                    {editing ? (
                      <select
                        value={editShiftId}
                        onChange={(e) => setEditShiftId(e.target.value)}
                        className={editableInputClass}
                      >
                        {shifts.map((s) => (
                          <option key={s.shift_id} value={s.shift_id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                    ) : l.shift_id ? (
                      (shiftById.get(l.shift_id)?.name ?? l.shift_id)
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td className="num">
                    {editing ? (
                      <input
                        value={editProductModel}
                        onChange={(e) => setEditProductModel(e.target.value)}
                        className={editableInputClass}
                      />
                    ) : (
                      l.product_model || "—"
                    )}
                  </Td>
                  <Td className="num">
                    {editing ? (
                      <input
                        type="number"
                        min={l.quantity}
                        value={editQuantity}
                        onChange={(e) => setEditQuantity(e.target.value)}
                        className={editableInputClass}
                      />
                    ) : (
                      (l.quantity ?? 0)
                    )}
                  </Td>
                  <Td>
                    {editing ? (
                      <input
                        value={editNote}
                        onChange={(e) => setEditNote(e.target.value)}
                        className={editableInputClass}
                      />
                    ) : (
                      l.note || "—"
                    )}
                  </Td>
                  <Td>
                    <Badge tone={isActive(l.active) ? "pass" : "neutral"}>
                      {isActive(l.active) ? "Đang mở" : "Đã đóng"}
                    </Badge>
                  </Td>
                  <Td>
                    {editing ? (
                      <div className="flex gap-1.5">
                        <Btn
                          variant="solid"
                          size="xs"
                          disabled={updateLot.isPending}
                          onClick={() => void saveEdit(l.lot_id)}
                        >
                          Lưu
                        </Btn>
                        <Btn variant="outline" size="xs" onClick={() => setEditingId(null)}>
                          Hủy
                        </Btn>
                      </div>
                    ) : (
                      <div className="flex gap-1.5">
                        <Btn variant="outline" size="xs" onClick={() => startEdit(l)}>
                          Sửa
                        </Btn>
                        <Btn
                          variant={isActive(l.active) ? "danger" : "success"}
                          size="xs"
                          disabled={updateLot.isPending}
                          onClick={() =>
                            updateLot.mutate({
                              lotId: l.lot_id,
                              payload: { active: !isActive(l.active) },
                            })
                          }
                        >
                          {isActive(l.active) ? "Đóng" : "Mở lại"}
                        </Btn>
                      </div>
                    )}
                  </Td>
                </Tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}

function StationsPanel() {
  const stationsQuery = useStations(false);
  const createStation = useCreateStation();
  const updateStation = useUpdateStation();

  const [stationId, setStationId] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const stations = stationsQuery.data ?? [];

  async function handleCreate() {
    setError("");
    if (!stationId.trim() || !name.trim()) {
      setError("Cần nhập mã trạm và tên trạm.");
      return;
    }
    try {
      await createStation.mutateAsync({
        station_id: stationId.trim(),
        name: name.trim(),
      });
      setStationId("");
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tạo trạm thất bại.");
    }
  }

  function startEdit(s: (typeof stations)[number]) {
    setEditingId(s.station_id);
    setEditName(s.name);
  }

  async function saveEdit(stationIdToSave: string) {
    if (!editName.trim()) return;
    await updateStation.mutateAsync({
      stationId: stationIdToSave,
      payload: { name: editName.trim() },
    });
    setEditingId(null);
  }

  return (
    <Panel title="Trạm QC">
      <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-4">
        <input
          value={stationId}
          onChange={(e) => setStationId(e.target.value)}
          placeholder="Mã trạm"
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 font-mono text-xs text-foreground placeholder:text-muted-foreground"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Tên hiển thị"
          className="h-8 rounded-sm border border-border bg-surface-2 px-2 text-xs text-foreground placeholder:text-muted-foreground"
        />
        <Btn variant="solid" onClick={handleCreate} disabled={createStation.isPending}>
          {createStation.isPending ? "Đang thêm…" : "+ Thêm trạm"}
        </Btn>
      </div>
      {error ? <p className="mb-3 text-[11px] text-destructive">{error}</p> : null}

      {stationsQuery.isPending ? (
        <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
          Đang tải…
        </div>
      ) : stations.length === 0 ? (
        <EmptyState title="Chưa có trạm nào" description="Thêm trạm QC đầu tiên ở trên." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Mã trạm</Th>
              <Th>Tên</Th>
              <Th>Trạng thái</Th>
              <Th></Th>
            </tr>
          </thead>
          <tbody>
            {stations.map((s) => {
              const editing = editingId === s.station_id;
              return (
                <Tr key={s.station_id}>
                  <Td className="num">{s.station_id}</Td>
                  <Td>
                    {editing ? (
                      <input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        className={editableInputClass}
                      />
                    ) : (
                      s.name
                    )}
                  </Td>
                  <Td>
                    <Badge tone={isActive(s.active) ? "pass" : "neutral"}>
                      {isActive(s.active) ? "Đang dùng" : "Đã tắt"}
                    </Badge>
                  </Td>
                  <Td>
                    {editing ? (
                      <div className="flex gap-1.5">
                        <Btn
                          variant="solid"
                          size="xs"
                          disabled={updateStation.isPending}
                          onClick={() => void saveEdit(s.station_id)}
                        >
                          Lưu
                        </Btn>
                        <Btn variant="outline" size="xs" onClick={() => setEditingId(null)}>
                          Hủy
                        </Btn>
                      </div>
                    ) : (
                      <div className="flex gap-1.5">
                        <Btn variant="outline" size="xs" onClick={() => startEdit(s)}>
                          Sửa
                        </Btn>
                        <Btn
                          variant={isActive(s.active) ? "danger" : "success"}
                          size="xs"
                          disabled={updateStation.isPending}
                          onClick={() =>
                            updateStation.mutate({
                              stationId: s.station_id,
                              payload: { active: !isActive(s.active) },
                            })
                          }
                        >
                          {isActive(s.active) ? "Tắt" : "Bật lại"}
                        </Btn>
                      </div>
                    )}
                  </Td>
                </Tr>
              );
            })}
          </tbody>
        </Table>
      )}
    </Panel>
  );
}

function Catalogs() {
  return (
    <div className="space-y-6">
      <PageHeader title="Ca, Lô & Trạm QC" />

      {/* Trạm và Ca là cấu trúc tổ chức cố định — Lô tham chiếu tới chúng khi được tạo, nên
       * hai catalog này phải tồn tại trước. Tách khỏi Lô vì tần suất thay đổi khác hẳn nhau. */}
      <section className="space-y-3">
        <div className="label-caps border-b border-border pb-1.5">Cấu hình nền tảng</div>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <StationsPanel />
          <ShiftsPanel />
        </div>
      </section>

      <section className="space-y-3">
        <div className="label-caps border-b border-border pb-1.5">Vận hành hàng ngày</div>
        <LotsPanel />
      </section>
    </div>
  );
}
