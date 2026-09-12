-- CarePilot v1.1: keep wall-clock and foreground active-time measures separate.
-- Historical records intentionally remain NULL because foreground time was not collected.

begin;

alter table public.customer_efficiency_records
    add column if not exists active_duration_seconds integer;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'customer_efficiency_records_active_duration_check'
    ) then
        alter table public.customer_efficiency_records
            add constraint customer_efficiency_records_active_duration_check
            check (active_duration_seconds is null or active_duration_seconds >= 0);
    end if;
end $$;

comment on column public.customer_efficiency_records.active_duration_seconds is
    'Foreground browser time reported by the public experiment page. NULL means this field was not collected for the historical record.';

commit;
