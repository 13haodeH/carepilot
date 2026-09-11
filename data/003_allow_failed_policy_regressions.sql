-- CarePilot v0.1 corrective migration.
--
-- Apply this when 001_supabase_schema.sql was executed before policy
-- regressions could persist a FAILED result. It does not delete or rewrite rows.

begin;

alter table public.policy_regression_runs
    drop constraint if exists policy_regression_runs_status_check;

alter table public.policy_regression_runs
    add constraint policy_regression_runs_status_check
    check (status in ('PENDING', 'PASSED', 'FAILED'));

commit;
