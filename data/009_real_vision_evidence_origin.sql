-- CarePilot v0.2.1: persist real visual-model outcomes separately from fixtures.
-- Apply after 001 through 008. This only widens a CHECK constraint; it does
-- not alter, delete, or backfill existing Evidence records.

begin;

alter table public.evidence_assets
    drop constraint if exists evidence_assets_analysis_origin_check;

alter table public.evidence_assets
    add constraint evidence_assets_analysis_origin_check
    check (analysis_origin in (
        'FIXTURE_ANNOTATION',
        'UNASSESSED',
        'REAL_VISION_MODEL',
        'REAL_VISION_FAILED'
    ));

commit;
