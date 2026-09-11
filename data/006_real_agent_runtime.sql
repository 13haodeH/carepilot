-- CarePilot v0.2: real server-side Agent Runtime, persistent local demo auth,
-- and real-model evaluation records. Apply after 001 through 005.
-- Do not execute this file alone on an empty Supabase schema: it ALTERs
-- public.tickets and other tables created by 001.
--
-- This migration creates no browser-readable policy and contains no API key.
-- The FastAPI server alone may access these tables with DATABASE_URL.

begin;

alter table public.tickets
    add column if not exists customer_id varchar(48),
    add column if not exists order_id varchar(48),
    add column if not exists request_text text,
    add column if not exists execution_mode varchar(32) not null default 'FIXTURE_SIMULATION';

alter table public.action_proposals
    add column if not exists customer_message text,
    add column if not exists confidence double precision,
    add column if not exists permission_decision varchar(32),
    add column if not exists policy_citations_json text,
    add column if not exists agent_run_id varchar(48);

alter table public.tool_executions
    add column if not exists tool_version varchar(32) not null default 'v1',
    add column if not exists input_json text,
    add column if not exists output_json text,
    add column if not exists caller varchar(48) not null default 'system',
    add column if not exists started_at timestamptz,
    add column if not exists completed_at timestamptz,
    add column if not exists state_impact varchar(64);

alter table public.evidence_assets
    add column if not exists model_id varchar(120),
    add column if not exists prompt_version varchar(80),
    add column if not exists vision_run_id varchar(48);

-- 005 permitted Candidate imports only. v0.2 also records the reviewed
-- baseline that is available for the first real Agent run.
alter table public.policy_source_snapshots
    drop constraint if exists policy_source_snapshots_import_method_check;
alter table public.policy_source_snapshots
    add constraint policy_source_snapshots_import_method_check
    check (import_method in ('CURATED_PUBLIC_PACK', 'CURATED_PUBLIC_BASELINE'));

create table if not exists public.agent_runs (
    id varchar(48) primary key,
    ticket_id varchar(32) not null references public.tickets(id),
    execution_mode varchar(32) not null check (execution_mode in ('REAL_AGENT_RUN', 'FIXTURE_SIMULATION')),
    stage varchar(32) not null check (stage in ('RESOLUTION', 'VISION_EVIDENCE')),
    status varchar(32) not null check (status in ('RUNNING', 'COMPLETED', 'FAILED')),
    model_id varchar(120) not null,
    prompt_version varchar(80) not null,
    input_json text not null,
    output_json text,
    tool_calls_json text not null default '[]',
    policy_evidence_json text not null default '[]',
    latency_ms integer,
    input_tokens integer,
    output_tokens integer,
    cost_usd double precision,
    failure_type varchar(80),
    failure_detail text,
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists public.real_evaluation_runs (
    id varchar(48) primary key,
    fixture_set varchar(120) not null,
    execution_mode varchar(32) not null check (execution_mode = 'REAL_AGENT_RUN'),
    model_id varchar(120) not null,
    prompt_version varchar(80) not null,
    policy_snapshot varchar(160) not null,
    status varchar(32) not null check (status in ('RUNNING', 'COMPLETED', 'FAILED')),
    sample_size integer not null check (sample_size > 0),
    metrics_json text not null,
    bad_cases_json text not null,
    source_note text not null,
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

-- Demo-only local sign-in. These credentials are seeded by the API and are not
-- a replacement for production identity integration.
create table if not exists public.app_users (
    id varchar(48) primary key,
    email varchar(160) not null unique,
    display_name varchar(120) not null,
    role varchar(32) not null check (role in ('CONSUMER', 'OPS', 'ADMIN')),
    password_salt varchar(64) not null,
    password_hash varchar(128) not null,
    created_at timestamptz not null default now()
);

create table if not exists public.app_sessions (
    id varchar(80) primary key,
    user_id varchar(48) not null references public.app_users(id),
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);

create index if not exists tickets_customer_id_idx on public.tickets (customer_id);
create index if not exists tickets_order_id_idx on public.tickets (order_id);
create index if not exists action_proposals_agent_run_id_idx on public.action_proposals (agent_run_id);
create index if not exists evidence_assets_vision_run_id_idx on public.evidence_assets (vision_run_id);
create index if not exists agent_runs_ticket_id_idx on public.agent_runs (ticket_id, created_at desc);
create index if not exists agent_runs_execution_mode_idx on public.agent_runs (execution_mode, status);
create index if not exists real_evaluation_runs_created_at_idx on public.real_evaluation_runs (created_at desc);
create index if not exists app_users_role_idx on public.app_users (role);
create index if not exists app_sessions_user_id_idx on public.app_sessions (user_id, expires_at);

alter table public.agent_runs enable row level security;
alter table public.real_evaluation_runs enable row level security;
alter table public.app_users enable row level security;
alter table public.app_sessions enable row level security;
revoke all privileges on table public.agent_runs, public.real_evaluation_runs, public.app_users, public.app_sessions from anon, authenticated;
grant all privileges on table public.agent_runs, public.real_evaluation_runs, public.app_users, public.app_sessions to service_role;

comment on table public.agent_runs is 'Each real model or vision call: model, prompt, input/output, tool calls, policy evidence, latency, tokens, and cost.';
comment on table public.real_evaluation_runs is 'Frozen evaluation runs that invoke a real configured model; not fixture simulation.';

commit;
