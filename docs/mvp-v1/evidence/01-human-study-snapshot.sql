-- CarePilot MVP1 human-study snapshot (read only)
-- Scope: completed anonymous participants only. No identity, order, image, key, insert, update or delete.
-- Snapshot referenced by docs/mvp-v1/01-human-study-report-2026-09-12.md.

-- 1) Population, six-task completeness and latest completion time by collection batch.
with completed_participants as (
    select id, study_mode, completed_at
    from public.customer_efficiency_participants
    where completed_at is not null
), per_participant as (
    select c.study_mode, c.id, count(r.id) as submitted_records
    from completed_participants c
    left join public.customer_efficiency_records r on r.participant_id = c.id
    group by c.study_mode, c.id
)
select
    c.study_mode,
    count(*) as completed_participants,
    sum(p.submitted_records) as submitted_records,
    count(*) filter (where p.submitted_records = 6) as six_task_participants,
    count(*) filter (where p.submitted_records <> 6) as non_six_task_participants,
    max(c.completed_at) as latest_completed_at
from completed_participants c
join per_participant p using (study_mode, id)
group by c.study_mode
order by c.study_mode;

-- 2) Main descriptive metrics by condition across all completed participants.
with completed_participants as (
    select id
    from public.customer_efficiency_participants
    where completed_at is not null
), base as (
    select
        r.*,
        jsonb_array_length(r.source_actions_json::jsonb) as source_opens
    from public.customer_efficiency_records r
    join completed_participants c on c.id = r.participant_id
)
select
    condition,
    count(*) as tasks,
    count(distinct participant_id) as participants,
    sum(outcome_correct::int) as correct_tasks,
    round(100.0 * avg(outcome_correct::int), 1) as correct_pct,
    round(avg(source_opens), 2) as mean_source_opens,
    round(percentile_cont(0.5) within group (order by source_opens)::numeric, 1) as median_source_opens,
    round(avg(information_completeness_percent), 1) as mean_information_completeness_pct,
    round(percentile_cont(0.5) within group (order by information_completeness_percent)::numeric, 1) as median_information_completeness_pct,
    round(avg(duration_seconds), 1) as mean_wall_clock_seconds,
    round(percentile_cont(0.5) within group (order by duration_seconds)::numeric, 1) as median_wall_clock_seconds,
    round(avg(ease_rating_1_to_7), 2) as mean_ease_rating
from base
group by condition
order by condition;

-- 3) High-risk human control and Decision Package outcomes.
with completed_participants as (
    select id
    from public.customer_efficiency_participants
    where completed_at is not null
)
select
    r.condition,
    count(*) filter (where r.risk = 'HIGH') as high_risk_tasks,
    count(*) filter (where r.risk = 'HIGH' and r.high_risk_gate_observed) as observed_human_gates
from public.customer_efficiency_records r
join completed_participants c on c.id = r.participant_id
group by r.condition
order by r.condition;

with completed_participants as (
    select id
    from public.customer_efficiency_participants
    where completed_at is not null
)
select
    r.proposal_outcome,
    count(*) as tasks,
    round(
        100.0 * count(*) / sum(count(*)) over (),
        1
    ) as pct_of_high_risk_decision_packages
from public.customer_efficiency_records r
join completed_participants c on c.id = r.participant_id
where r.risk = 'HIGH' and r.condition = 'DECISION_PACKAGE'
group by r.proposal_outcome
order by r.proposal_outcome;
