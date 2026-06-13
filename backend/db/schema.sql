-- =============================================================================
-- Synkris Voice Agent — Supabase schema (Phase 2)
-- =============================================================================
-- Source-of-truth split:
--   * Google Calendar owns appointment TIME (free/busy + the booking event).
--   * Supabase owns everything else (config, customers, bookings refs, call logs).
--   * Never store a fact twice: a booking row REFERENCES a Google Calendar event
--     (gcal_event_id); it does not replace it.
--
-- Conventions:
--   * UUID primary keys (gen_random_uuid(), core since PG13 / available on Supabase).
--   * All timestamps are timestamptz (stored UTC). The slot engine converts to the
--     practice timezone from config — we never store wall-clock local times here.
--   * Audit columns: created_at, updated_at (auto), updated_by (set by the app).
--   * RLS is enabled on every table. The backend connects with the service_role key,
--     which BYPASSES RLS — so with no policies the tables are closed to anon/public
--     by default, which is what we want until the Phase 5 dashboard needs per-tenant
--     policies for authenticated users.
-- =============================================================================

-- ---- updated_at trigger helper --------------------------------------------------
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;


-- ---- 1. tenants -----------------------------------------------------------------
-- One row per practice. The whole Contract-1 config lives in `config` as JSONB
-- (it's already a single validated document; the slot engine consumes it as a dict,
-- so normalising practitioners/treatments/hours into tables would just be rebuilt
-- into the same dict on every read). The dashboard edits this JSON in Phase 5.
create table tenants (
  id           uuid primary key default gen_random_uuid(),
  phone_number text not null unique,             -- dialled number -> tenant (get_tenant)
  name         text not null,
  pms          text not null default 'gcal'
                 check (pms in ('mock', 'gcal')), -- Contract 3 backend selector
  config       jsonb not null,                    -- full Contract-1 config document
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  updated_by   text
);

create trigger tenants_updated_at before update on tenants
  for each row execute function set_updated_at();


-- ---- 2. customers ---------------------------------------------------------------
-- Returning-customer lookup. Google Calendar has no patient concept, so the caller's
-- identity lives here. Dental identity = last_name + dob (case-insensitive); the
-- index is non-unique on purpose (collisions are possible — find-or-create dedupes
-- in the app, we don't want create_patient to fail on a clash).
-- NOTE: holds PII; once real patients are used this table is in scope for the
-- compliance gate (encryption at rest, retention, SAR/deletion). Fake data until then.
create table customers (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references tenants(id) on delete cascade,
  first_name  text not null,
  last_name   text not null,
  dob         date not null,
  phone       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index customers_identity_idx
  on customers (tenant_id, lower(last_name), dob);

create trigger customers_updated_at before update on customers
  for each row execute function set_updated_at();


-- ---- 3. bookings ----------------------------------------------------------------
-- A reference to a Google Calendar event, plus our own metadata. The calendar event
-- is the source of truth for the time; starts_at/ends_at here are a CACHE so
-- "your upcoming appointments" (lookup_patient) is one Supabase query, not N calendar
-- reads. If they ever diverge, the calendar wins.
-- practitioner_id / treatment_key are opaque strings matching the config (they live in
-- tenants.config, so no FK here).
create table bookings (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references tenants(id) on delete cascade,
  customer_id     uuid not null references customers(id) on delete restrict,
  gcal_calendar_id text not null,          -- which practitioner/resource calendar
  gcal_event_id    text not null,          -- THE Google Calendar event (source of truth)
  practitioner_id  text not null,          -- config practitioner id
  treatment_key    text not null,          -- config treatment key
  starts_at        timestamptz not null,   -- cached from the calendar event
  ends_at          timestamptz not null,
  status           text not null default 'booked'
                     check (status in ('booked', 'cancelled')),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create unique index bookings_gcal_event_idx on bookings (gcal_event_id);
create index bookings_customer_idx on bookings (customer_id, starts_at);
create index bookings_tenant_upcoming_idx
  on bookings (tenant_id, starts_at) where status = 'booked';

create trigger bookings_updated_at before update on bookings
  for each row execute function set_updated_at();


-- ---- 4. call_logs ---------------------------------------------------------------
-- One row per call, for the dashboard (Phase 5) and audit. A deferred retention job
-- deletes old rows per tenants.config -> retention.{transcripts_days, call_logs_days}.
create table call_logs (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenants(id) on delete cascade,
  retell_call_id text,
  from_number   text,
  to_number     text,
  intent        text,                       -- primary function used, optional
  outcome       text,                       -- short status summary
  transcript    text,
  recording_url text,
  booking_id    uuid references bookings(id) on delete set null,  -- if it produced a booking
  started_at    timestamptz,
  ended_at      timestamptz,
  created_at    timestamptz not null default now()
);

create index call_logs_tenant_time_idx on call_logs (tenant_id, created_at);


-- ---- 5. Row Level Security ------------------------------------------------------
-- Enable on all tables. Backend uses service_role (bypasses RLS). No anon policies
-- yet — add per-tenant policies in Phase 5 when the dashboard authenticates users.
alter table tenants    enable row level security;
alter table customers  enable row level security;
alter table bookings   enable row level security;
alter table call_logs  enable row level security;


-- ---- 5b. Grants -----------------------------------------------------------------
-- The backend connects as the API role `service_role`, which must have table
-- privileges (it bypasses RLS, but still needs the GRANT). Supabase usually applies
-- these automatically; on some projects tables made in the SQL editor don't get them,
-- so we grant explicitly. anon/authenticated also get privileges but stay gated by
-- RLS (no policies above = denied) until Phase 5.
grant usage on schema public to service_role, anon, authenticated;
grant all privileges on all tables in schema public to service_role, anon, authenticated;
alter default privileges in schema public
  grant all privileges on tables to service_role, anon, authenticated;


-- ---- 6. Seed the demo practice (optional) ---------------------------------------
-- Loads the current seed_config.json as the demo tenant. Paste the JSON in place of
-- '<<config>>'. The phone_number must equal practice.phone so get_tenant resolves it.
--
-- insert into tenants (id, phone_number, name, pms, config) values (
--   '00000000-0000-0000-0000-000000000001',
--   '+441162345678',
--   'Bright Smiles Dental',
--   'mock',
--   '<<paste seed_config.json here>>'::jsonb
-- );
