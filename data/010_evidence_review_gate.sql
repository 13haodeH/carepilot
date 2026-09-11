-- CarePilot v0.2.2: retain the visual model's review judgement separately
-- from the deterministic evidence-sufficiency gate. Apply after 001 through 009.
-- Existing records are intentionally not backfilled: their raw model judgement
-- was not stored separately at creation time.

begin;

alter table public.evidence_assets
    add column if not exists model_needs_human_review boolean,
    add column if not exists review_gate_reasons_json text not null default '[]';

comment on column public.evidence_assets.model_needs_human_review is
    'Raw visual-model review judgement. Null for records created before v0.2.2 or fixture-only evidence.';
comment on column public.evidence_assets.review_gate_reasons_json is
    'JSON array of deterministic evidence-sufficiency reasons added after the visual model observation.';

commit;
