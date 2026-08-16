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
   classification_rule, default_severity, measurement_required, active, created_at, updated_at)
values
  ('SCRATCH01','scratch','scratch','SURFACE_SCRATCH','Vết xước nhỏ','Vết xước đơn đến 50 mm','estimated_width_mm <= 50','C',1,1,now()::text,now()::text),
  ('SCRATCH02','scratch','scratch','SURFACE_SCRATCH','Vết xước trung bình','Vết xước trên 50 đến 150 mm','50 < estimated_width_mm <= 150','C',1,1,now()::text,now()::text),
  ('SCRATCH03','scratch','scratch','SURFACE_SCRATCH','Vết xước dài','Vết xước trên 150 mm','estimated_width_mm > 150','B',1,1,now()::text,now()::text),
  ('SCRATCH04','scratch','scratch','SURFACE_SCRATCH_CLUSTER','Cụm nhiều vết xước','Nhiều vùng xước trên cùng inspection','at least 2 scratch detections','B',1,1,now()::text,now()::text),
  ('SCRATCH05','scratch','scratch','SURFACE_SCRATCH_EDGE','Vết xước vùng mép','Vết xước gần mép vùng quan sát','left/right edge position','B',1,1,now()::text,now()::text),
  ('DENT01','dent','dent','PANEL_DENT','Vết móp nhỏ','Vết móp đơn đến 50 mm','estimated_width_mm <= 50','C',1,1,now()::text,now()::text),
  ('DENT02','dent','dent','PANEL_DENT','Vết móp trung bình','Vết móp trên 50 đến 150 mm','50 < estimated_width_mm <= 150','B',1,1,now()::text,now()::text),
  ('DENT03','dent','dent','PANEL_DENT','Vết móp lớn','Vết móp trên 150 mm','estimated_width_mm > 150','A',1,1,now()::text,now()::text),
  ('DENT04','dent','dent','PANEL_DENT_CREASE','Móp có nếp gấp','Móp kéo dài cần QC xác nhận nếp gấp','bbox aspect ratio >= 2 and QC confirmation','A',1,1,now()::text,now()::text),
  ('DENT05','dent','dent','PANEL_DENT_CLUSTER','Cụm nhiều vết móp','Nhiều vùng móp trên cùng inspection','at least 2 dent detections','A',1,1,now()::text,now()::text)
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
  updated_at = excluded.updated_at;

-- Retain historical references while removing unsupported classes from active QC use.
update public.defect_catalog
set active = 0, updated_at = now()::text
where defect_code in ('PAINT01', 'CRACK01', 'GLASS01', 'LAMP01', 'TIRE01');

-- The browser never accesses these tables directly in this architecture.
-- FastAPI owns database access through its server-side DATABASE_URL.
