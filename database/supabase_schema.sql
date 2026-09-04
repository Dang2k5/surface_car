-- Visual QC Agent baseline schema for Supabase PostgreSQL.
-- Run once in Supabase Dashboard > SQL Editor before pointing FastAPI at the project.

create table if not exists public.agent_graph_runs (
  thread_id text primary key,
  inspection_id text not null,
  vehicle_id text not null,
  status text not null,
  state_json text not null,
  updated_at text not null
);

create index if not exists idx_agent_graph_runs_vehicle_updated
  on public.agent_graph_runs (vehicle_id, updated_at desc);

create table if not exists public.defect_catalog (
  defect_code text primary key,
  defect_type text not null,
  cv_label text not null,
  defect_family text not null default '',
  display_name text not null,
  description text not null default '',
  classification_rule text not null default '',
  default_severity text not null default 'UNASSESSED',
  measurement_required integer not null default 0,
  active integer not null default 1,
  created_at text not null,
  updated_at text not null
);

create index if not exists idx_defect_catalog_cv_label
  on public.defect_catalog (cv_label, active);

create table if not exists public.qc_decisions (
  decision_id text primary key,
  thread_id text,
  inspection_id text not null,
  vehicle_id text not null,
  defect_code text not null references public.defect_catalog(defect_code),
  defect_type text not null,
  location text not null default '',
  length_mm double precision,
  severity text not null,
  action text not null,
  disposition text not null,
  reviewer text not null,
  reason text not null,
  notes text not null default '',
  created_at text not null
);

-- Remove context columns retained by earlier MVP revisions.
alter table public.qc_decisions drop column if exists panel;
alter table public.qc_decisions drop column if exists material;

create index if not exists idx_qc_decisions_vehicle_created
  on public.qc_decisions (vehicle_id, created_at desc);

create index if not exists idx_qc_decisions_inspection
  on public.qc_decisions (inspection_id);

alter table public.defect_catalog add column if not exists defect_family text not null default '';
alter table public.defect_catalog add column if not exists classification_rule text not null default '';

insert into public.defect_catalog
  (defect_code, defect_type, cv_label, defect_family, display_name, description,
   classification_rule, default_severity, measurement_required, active, source_id, created_at, updated_at)
values
  ('SCRATCH01','scratch','scratch','SURFACE_SCRATCH','Vết xước nhỏ','Vết xước đơn đến 50 mm','estimated_width_mm <= 50','C',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text),
  ('SCRATCH02','scratch','scratch','SURFACE_SCRATCH','Vết xước trung bình','Vết xước trên 50 đến 150 mm','50 < estimated_width_mm <= 150','C',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text),
  ('SCRATCH03','scratch','scratch','SURFACE_SCRATCH','Vết xước dài','Vết xước trên 150 mm','estimated_width_mm > 150','B',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text),
  ('SCRATCH04','scratch','scratch','SURFACE_SCRATCH_CLUSTER','Cụm nhiều vết xước','Nhiều vùng xước trên cùng inspection','at least 2 scratch detections','B',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text),
  ('SCRATCH05','scratch','scratch','SURFACE_SCRATCH_EDGE','Vết xước vùng mép','Vết xước gần mép vùng quan sát','left/right edge position','B',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text),
  ('DENT01','dent','dent','PANEL_DENT','Vết móp nhỏ','Vết móp đơn đến 50 mm','estimated_width_mm <= 50','C',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text),
  ('DENT02','dent','dent','PANEL_DENT','Vết móp trung bình','Vết móp trên 50 đến 150 mm','50 < estimated_width_mm <= 150','B',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text),
  ('DENT03','dent','dent','PANEL_DENT','Vết móp lớn','Vết móp trên 150 mm','estimated_width_mm > 150','A',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text),
  ('DENT04','dent','dent','PANEL_DENT_CREASE','Móp có nếp gấp','Móp kéo dài cần QC xác nhận nếp gấp','bbox aspect ratio >= 2 and QC confirmation','A',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text),
  ('DENT05','dent','dent','PANEL_DENT_CLUSTER','Cụm nhiều vết móp','Nhiều vùng móp trên cùng inspection','at least 2 dent detections','A',1,1,'FNS-SEVERITY-CRITERIA-INTERNAL',now()::text,now()::text)
on conflict (defect_code) do update set
  defect_type = excluded.defect_type,
  cv_label = excluded.cv_label,
  defect_family = excluded.defect_family,
  display_name = excluded.display_name,
  description = excluded.description,
  classification_rule = excluded.classification_rule,
  default_severity = excluded.default_severity,
  measurement_required = excluded.measurement_required,
  active = 1,
  source_id = coalesce(public.defect_catalog.source_id, excluded.source_id),
  updated_at = excluded.updated_at;

-- Retain historical references while removing unsupported classes from active QC use.
update public.defect_catalog
set active = 0, updated_at = now()::text
where defect_code in ('PAINT01', 'CRACK01', 'GLASS01', 'LAMP01', 'TIRE01');

-- RBAC: role lookup for Supabase-authenticated requests (API_CONTRACT.md §7.7,
-- backend/app/auth.py get_or_create_profile). FastAPI provisions a row here the first time each
-- Supabase user calls an authenticated endpoint, defaulting role to DEFAULT_QC_ROLE — this table
-- does not need to be pre-populated, only to exist before FastAPI points at this project.
create table if not exists public.profiles (
  user_id text primary key,
  email text,
  full_name text,
  role text not null default 'QC_OPERATOR',
  station_id text,
  created_at text not null,
  updated_at text not null
);

-- Ca làm việc / Lô sản xuất / Trạm QC catalogs (backend/app/catalog_api.py). QC_SUPERVISOR
-- manages these; the inspection form only picks from the active rows. Trạm and Ca are
-- independent catalogs (a shift runs in parallel across multiple stations); a Lô references the
-- specific Trạm+Ca it was produced under, not the other way around.
create table if not exists public.shifts (
  shift_id text primary key,
  name text not null,
  start_time text not null default '',
  end_time text not null default '',
  active integer not null default 1,
  created_at text not null,
  updated_at text not null
);

create table if not exists public.stations (
  station_id text primary key,
  name text not null,
  active integer not null default 1,
  created_at text not null,
  updated_at text not null
);

create table if not exists public.production_lots (
  lot_id text primary key,
  name text not null default '',
  note text not null default '',
  station_id text references public.stations(station_id),
  shift_id text references public.shifts(shift_id),
  product_model text not null default '',
  quantity integer not null default 0,
  active integer not null default 1,
  created_at text not null,
  updated_at text not null
);

alter table public.production_lots add column if not exists station_id text references public.stations(station_id);
alter table public.production_lots add column if not exists shift_id text references public.shifts(shift_id);
alter table public.production_lots add column if not exists name text not null default '';
alter table public.production_lots add column if not exists product_model text not null default '';
alter table public.production_lots add column if not exists quantity integer not null default 0;
alter table public.production_lots drop column if exists vehicle_type;

-- Product codes are allocated one at a time as a vehicle passes the camera during an inspection
-- (see Database.allocate_lot_product in backend/app/database.py), format:
-- <Mã Lô>-<Model sản phẩm>-<STT>, STT starting at 1 and counting up until the lot's quantity is used.
create table if not exists public.lot_products (
  product_code text primary key,
  lot_id text not null references public.production_lots(lot_id),
  seq integer not null,
  vehicle_model text not null,
  created_at text not null
);

alter table public.lot_products add column if not exists vehicle_model text not null default '';
alter table public.lot_products drop column if exists vehicle_type;

-- The browser never accesses these tables directly in this architecture.
-- FastAPI owns database access through its server-side DATABASE_URL.
