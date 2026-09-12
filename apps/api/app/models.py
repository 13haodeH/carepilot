from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (CheckConstraint("risk IN ('LOW', 'MEDIUM', 'HIGH')", name="tickets_risk_check"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    customer: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    scenario: Mapped[str] = mapped_column(String(60))
    risk: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), index=True)
    evidence_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    request_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(32), default="FIXTURE_SIMULATION")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class ActionProposal(Base):
    __tablename__ = "action_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'AUTO_EXECUTED', 'APPROVED', 'MODIFIED', 'REJECTED', 'TAKEN_OVER')",
            name="action_proposals_status_check",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    rationale: Mapped[str] = mapped_column(Text)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    permission_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_citations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[str] = mapped_column(String(24))
    summary: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    tool_version: Mapped[str] = mapped_column(String(32), default="v1")
    input_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    caller: Mapped[str] = mapped_column(String(48), default="system")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state_impact: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    decision: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str] = mapped_column(String(120), default="demo-operator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class EvidenceAsset(Base):
    __tablename__ = "evidence_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    fixture_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_name_sha256: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(24))
    input_byte_size: Mapped[int] = mapped_column(Integer)
    sanitized_byte_size: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    exif_removed: Mapped[bool] = mapped_column(Boolean)
    analysis_origin: Mapped[str] = mapped_column(String(32))
    evidence_type: Mapped[str] = mapped_column(String(48))
    damage_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    damage_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    packaging_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    missing_parts: Mapped[str | None] = mapped_column(String(160), nullable=True)
    label_match: Mapped[str] = mapped_column(String(32))
    image_quality: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column()
    model_needs_human_review: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    needs_human_review: Mapped[bool] = mapped_column(Boolean)
    review_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_gate_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    vision_run_id: Mapped[str | None] = mapped_column(String(48), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PolicySource(Base):
    __tablename__ = "policy_sources"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    source_type: Mapped[str] = mapped_column(String(32))
    sync_schedule: Mapped[str] = mapped_column(String(80))
    publisher: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_scope: Mapped[str] = mapped_column(String(48), default="SELF_AUTHORED_SIMULATION")
    source_version_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PolicySourceSnapshot(Base):
    __tablename__ = "policy_source_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"), index=True)
    pack_id: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(String(160))
    source_version_label: Mapped[str] = mapped_column(String(200))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    content_checksum: Mapped[str] = mapped_column(String(64))
    source_excerpt: Mapped[str] = mapped_column(Text)
    import_method: Mapped[str] = mapped_column(String(48))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PolicyGroundingChunk(Base):
    __tablename__ = "policy_grounding_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("policy_source_snapshots.id"), index=True)
    chunk_key: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    keywords_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PolicyVersion(Base):
    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"), index=True)
    source_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("policy_source_snapshots.id"), nullable=True, index=True)
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    diff_summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    published_by: Mapped[str | None] = mapped_column(String(120), nullable=True)


class PolicyRegressionRun(Base):
    __tablename__ = "policy_regression_runs"
    __table_args__ = (CheckConstraint("status IN ('PENDING', 'PASSED', 'FAILED')", name="policy_regression_runs_status_check"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_version_id: Mapped[int] = mapped_column(ForeignKey("policy_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PolicyAuditEvent(Base):
    __tablename__ = "policy_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"), index=True)
    policy_version_id: Mapped[int | None] = mapped_column(ForeignKey("policy_versions.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AgentConfigVersion(Base):
    __tablename__ = "agent_config_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    model_name: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(80))
    tool_allowlist: Mapped[str] = mapped_column(Text)
    risk_boundary: Mapped[str] = mapped_column(Text)
    activated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ConfigSandboxRun(Base):
    __tablename__ = "config_sandbox_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_version_id: Mapped[int] = mapped_column(ForeignKey("agent_config_versions.id"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConfigAuditEvent(Base):
    __tablename__ = "config_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_version_id: Mapped[int] = mapped_column(ForeignKey("agent_config_versions.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fixture_set: Mapped[str] = mapped_column(String(120))
    execution_mode: Mapped[str] = mapped_column(String(40))
    sample_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    manual_avg_minutes: Mapped[float] = mapped_column()
    agent_avg_minutes: Mapped[float] = mapped_column()
    proposal_modification_rate: Mapped[float] = mapped_column()
    policy_top3_hit_rate: Mapped[float] = mapped_column()
    tool_failure_rate: Mapped[float] = mapped_column()
    p95_latency_seconds: Mapped[float] = mapped_column()
    avg_cost_usd: Mapped[float] = mapped_column()
    bad_cases_json: Mapped[str] = mapped_column(Text)
    source_note: Mapped[str] = mapped_column(Text)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"), index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    model_id: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(80))
    input_json: Mapped[str] = mapped_column(Text)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls_json: Mapped[str] = mapped_column(Text, default="[]")
    policy_evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    failure_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RealEvaluationRun(Base):
    __tablename__ = "real_evaluation_runs"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    fixture_set: Mapped[str] = mapped_column(String(120))
    execution_mode: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(80))
    policy_snapshot: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32))
    sample_size: Mapped[int] = mapped_column(Integer)
    metrics_json: Mapped[str] = mapped_column(Text)
    bad_cases_json: Mapped[str] = mapped_column(Text)
    source_note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class DemoOrderEntitlement(Base):
    __tablename__ = "demo_order_entitlements"

    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class CustomerEfficiencyParticipant(Base):
    __tablename__ = "customer_efficiency_participants"
    __table_args__ = (
        CheckConstraint("study_mode IN ('PILOT', 'FORMAL')", name="customer_efficiency_participants_mode_check"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    study_mode: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerEfficiencyAssignment(Base):
    __tablename__ = "customer_efficiency_assignments"
    __table_args__ = (
        CheckConstraint("condition IN ('MANUAL', 'DECISION_PACKAGE')", name="customer_efficiency_assignments_condition_check"),
        UniqueConstraint("participant_id", "task_id", name="customer_efficiency_assignments_participant_task_unique"),
        UniqueConstraint("participant_id", "round", name="customer_efficiency_assignments_participant_round_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[str] = mapped_column(ForeignKey("customer_efficiency_participants.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(String(32), index=True)
    pair_id: Mapped[str] = mapped_column(String(24))
    condition: Mapped[str] = mapped_column(String(24))
    round: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class CustomerEfficiencyRecord(Base):
    __tablename__ = "customer_efficiency_records"
    __table_args__ = (
        CheckConstraint("condition IN ('MANUAL', 'DECISION_PACKAGE')", name="customer_efficiency_records_condition_check"),
        CheckConstraint("selected_outcome IN ('RESOLVED', 'NEED_INFO', 'WAITING_REVIEW')", name="customer_efficiency_records_outcome_check"),
        CheckConstraint("proposal_outcome IS NULL OR proposal_outcome IN ('ADOPTED', 'MODIFIED', 'REJECTED', 'TAKEN_OVER')", name="customer_efficiency_records_proposal_check"),
        UniqueConstraint("participant_id", "task_id", name="customer_efficiency_records_participant_task_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    participant_id: Mapped[str] = mapped_column(ForeignKey("customer_efficiency_participants.id", ondelete="CASCADE"), index=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("customer_efficiency_assignments.id", ondelete="CASCADE"), unique=True)
    study_mode: Mapped[str] = mapped_column(String(16), index=True)
    task_id: Mapped[str] = mapped_column(String(32), index=True)
    pair_id: Mapped[str] = mapped_column(String(24))
    condition: Mapped[str] = mapped_column(String(24))
    round: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(60))
    scenario: Mapped[str] = mapped_column(String(80))
    risk: Mapped[str] = mapped_column(String(16))
    selected_outcome: Mapped[str] = mapped_column(String(32))
    outcome_correct: Mapped[bool] = mapped_column(Boolean)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    active_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    source_fields_viewed_json: Mapped[str] = mapped_column(Text, default="[]")
    decision_package_ready_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    decision_package_missing_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    information_completeness_percent: Mapped[float] = mapped_column(Float)
    high_risk_gate_observed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    proposal_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ease_rating_1_to_7: Mapped[int] = mapped_column(Integer)
    observer_notes: Mapped[str] = mapped_column(Text, default="")
