from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


TicketStatus = Literal["NEW", "PROCESSING", "NEED_INFO", "WAITING_REVIEW", "RESOLVED", "FAILED"]
ReviewDecision = Literal["APPROVE", "MODIFY", "REJECT"]


class TicketSummary(BaseModel):
    id: str
    title: str
    customer: str
    category: str
    scenario: str
    risk: str
    status: TicketStatus
    order_id: str | None = None
    execution_mode: str
    updated_at: datetime


class ConsumerTicketOut(TicketSummary):
    customer_message: str | None


class ToolExecutionOut(BaseModel):
    tool_name: str
    outcome: str
    summary: str
    tool_version: str
    input_json: str | None
    output_json: str | None
    caller: str
    state_impact: str | None
    created_at: datetime


class AuditEventOut(BaseModel):
    event_type: str
    summary: str
    created_at: datetime


class ProposalOut(BaseModel):
    action: str
    status: str
    rationale: str
    customer_message: str | None
    confidence: float | None
    permission_decision: str | None
    policy_citations: list[dict[str, object]]


class EvidenceAssetOut(BaseModel):
    id: int
    fixture_id: str | None
    content_type: str
    input_byte_size: int
    sanitized_byte_size: int
    exif_removed: bool
    analysis_origin: str
    evidence_type: str
    damage_type: str | None
    damage_location: str | None
    packaging_status: str | None
    missing_parts: str | None
    label_match: str
    image_quality: str
    confidence: float
    model_needs_human_review: bool | None
    needs_human_review: bool
    review_reason: str | None
    review_gate_reasons: list[str]
    model_id: str | None
    prompt_version: str | None
    vision_run_id: str | None
    created_at: datetime


class AgentRunOut(BaseModel):
    id: str
    execution_mode: str
    stage: str
    status: str
    model_id: str
    prompt_version: str
    input_json: str
    output_json: str | None
    tool_calls: list[dict]
    policy_evidence: list[dict]
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    failure_type: str | None
    failure_detail: str | None
    created_at: datetime
    completed_at: datetime | None


class TicketDetail(TicketSummary):
    request_text: str | None
    order_context: dict | None
    logistics_context: dict | None
    proposal: ProposalOut | None
    evidence_assets: list[EvidenceAssetOut]
    tool_executions: list[ToolExecutionOut]
    audit_events: list[AuditEventOut]
    agent_runs: list[AgentRunOut]


class ReviewRequest(BaseModel):
    decision: ReviewDecision
    note: str | None = Field(default=None, max_length=500)
    modified_action: str | None = Field(default=None, max_length=80)
    modified_rationale: str | None = Field(default=None, max_length=1200)


class TakeOverRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class TicketCreateRequest(BaseModel):
    order_id: str = Field(min_length=3, max_length=48)
    request_text: str = Field(min_length=8, max_length=2000)


class OrderOut(BaseModel):
    id: str
    title: str
    category: str
    amount: float
    delivered_at: str
    status: str


class PolicyVersionOut(BaseModel):
    id: int
    version: str
    status: str
    diff_summary: str
    created_at: datetime
    published_by: str | None
    source_snapshot_id: int | None


class PolicyRegressionOut(BaseModel):
    id: int
    status: str
    summary: str
    completed_at: datetime | None


class PolicyAuditEventOut(BaseModel):
    event_type: str
    summary: str
    created_at: datetime


class PolicySourceOut(BaseModel):
    id: str
    title: str
    source_type: str
    sync_schedule: str
    publisher: str | None
    source_url: str | None
    source_scope: str
    source_version_label: str | None
    source_published_at: datetime | None
    current_checksum: str | None
    last_synced_at: datetime | None
    last_verified_at: datetime | None
    active_version: PolicyVersionOut | None
    candidate_version: PolicyVersionOut | None


class PolicySourceSnapshotOut(BaseModel):
    id: int
    pack_id: str
    source_url: str
    publisher: str
    source_version_label: str
    source_published_at: datetime | None
    retrieved_at: datetime
    content_checksum: str
    source_excerpt: str
    import_method: str


class PolicyGroundingChunkOut(BaseModel):
    id: int
    chunk_key: str
    category: str
    title: str
    content: str


class PolicyGroundingSearchResult(BaseModel):
    source_id: str
    source_title: str
    source_url: str
    source_version_label: str
    content_checksum: str
    chunk_key: str
    category: str
    title: str
    content: str
    score: int


class PolicySourceDetail(PolicySourceOut):
    versions: list[PolicyVersionOut]
    regressions: list[PolicyRegressionOut]
    audit_events: list[PolicyAuditEventOut]
    snapshots: list[PolicySourceSnapshotOut]
    grounding_chunks: list[PolicyGroundingChunkOut]


class PublishRequest(BaseModel):
    reviewer: str = Field(min_length=2, max_length=120)


class RollbackRequest(BaseModel):
    reviewer: str = Field(min_length=2, max_length=120)


class AgentConfigOut(BaseModel):
    id: int
    version: str
    status: str
    model_name: str
    prompt_version: str
    tool_allowlist: list[str]
    risk_boundary: str
    activated_by: str | None
    created_at: datetime


class SandboxRunOut(BaseModel):
    id: int
    scenario_id: str
    status: str
    summary: str
    completed_at: datetime | None


class ConfigAuditEventOut(BaseModel):
    event_type: str
    summary: str
    created_at: datetime


class AgentConfigDetail(AgentConfigOut):
    versions: list[AgentConfigOut]
    sandbox_runs: list[SandboxRunOut]
    audit_events: list[ConfigAuditEventOut]


class ActivateConfigRequest(BaseModel):
    reviewer: str = Field(min_length=2, max_length=120)


class AgentConfigCreateRequest(BaseModel):
    version: str = Field(min_length=3, max_length=32)
    model_name: str = Field(min_length=3, max_length=120)
    prompt_version: str = Field(min_length=3, max_length=80)
    tool_allowlist: list[str] = Field(min_length=3, max_length=8)
    risk_boundary: str = Field(min_length=12, max_length=800)


class BadCaseOut(BaseModel):
    category: str
    count: int
    next_action: str


class FixtureCoverageOut(BaseModel):
    categories: dict[str, int]
    image_case_count: int
    high_risk_case_count: int
    exception_case_count: int


class EvaluationRunOut(BaseModel):
    id: int
    fixture_set: str
    execution_mode: str
    sample_size: int
    status: str
    manual_avg_minutes: float
    agent_avg_minutes: float
    proposal_modification_rate: float
    policy_top3_hit_rate: float
    tool_failure_rate: float
    p95_latency_seconds: float
    avg_cost_usd: float
    bad_cases: list[BadCaseOut]
    fixture_coverage: FixtureCoverageOut
    source_note: str
    completed_at: datetime


class RealEvaluationRunOut(BaseModel):
    id: str
    fixture_set: str
    execution_mode: str
    model_id: str
    prompt_version: str
    policy_snapshot: str
    status: str
    sample_size: int
    metrics: dict
    bad_cases: list[dict]
    source_note: str
    created_at: datetime
    completed_at: datetime | None


class AuthUserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str


PublicStudyMode = Literal["PILOT", "FORMAL"]
PublicStudyCondition = Literal["MANUAL", "DECISION_PACKAGE"]
PublicStudyOutcome = Literal["RESOLVED", "NEED_INFO", "WAITING_REVIEW"]
PublicProposalOutcome = Literal["ADOPTED", "MODIFIED", "REJECTED", "TAKEN_OVER"]


class PublicEfficiencySessionRequest(BaseModel):
    participant_id: UUID
    study_mode: PublicStudyMode = "FORMAL"
    pilot_access_code: str | None = Field(default=None, max_length=200)


class PublicEfficiencyStartRequest(BaseModel):
    participant_id: UUID


class PublicEfficiencyRecordRequest(BaseModel):
    participant_id: UUID
    selected_outcome: PublicStudyOutcome
    source_actions: list[str] = Field(default_factory=list, max_length=8)
    high_risk_gate_observed: bool = False
    proposal_outcome: PublicProposalOutcome | None = None
    active_duration_seconds: int | None = Field(default=None, ge=0)
    ease_rating_1_to_7: int = Field(ge=1, le=7)
    observer_notes: str = Field(default="", max_length=500)


class PublicEfficiencySourceOut(BaseModel):
    id: str
    label: str
    content: str


class PublicEfficiencyDecisionPackageOut(BaseModel):
    summary: str
    fields: list[dict[str, str]]
    missing_information: list[str]
    policy_citation: str
    recommendation: str
    system_actions: list[str]


class PublicEfficiencyTaskOut(BaseModel):
    task_id: str
    pair_id: str
    round: int
    condition: PublicStudyCondition
    prompt: str
    requires_human_confirmation: bool
    sources: list[PublicEfficiencySourceOut]
    decision_package: PublicEfficiencyDecisionPackageOut | None = None


class PublicEfficiencySessionOut(BaseModel):
    participant_id: str
    study_mode: PublicStudyMode
    completed_task_ids: list[str]
    tasks: list[PublicEfficiencyTaskOut]


class PublicEfficiencyStartOut(BaseModel):
    task_id: str
    started_at: datetime


class PublicEfficiencyRecordOut(BaseModel):
    completed_task_ids: list[str]
    experiment_completed: bool
