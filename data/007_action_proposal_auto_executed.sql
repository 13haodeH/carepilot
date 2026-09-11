-- CarePilot v0.2.1: persist the low-risk Proposal produced by a real Agent
-- before its deterministic AUTO_EXECUTE state transition. Apply after 006.
-- This is a constraint-only compatibility migration; it does not alter rows.

begin;

alter table public.action_proposals
    drop constraint if exists action_proposals_status_check;
alter table public.action_proposals
    add constraint action_proposals_status_check
    check (status in ('PENDING', 'AUTO_EXECUTED', 'APPROVED', 'MODIFIED', 'REJECTED', 'TAKEN_OVER'));

commit;
