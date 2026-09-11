-- CarePilot v0.1 corrective migration.
--
-- Apply this only when 001_supabase_schema.sql was already executed before
-- MEDIUM-risk demo tickets were added to the allowed ticket-risk values.
-- It does not delete or rewrite ticket rows.

begin;

alter table public.tickets
    drop constraint if exists tickets_risk_check;

alter table public.tickets
    add constraint tickets_risk_check
    check (risk in ('LOW', 'MEDIUM', 'HIGH'));

commit;
