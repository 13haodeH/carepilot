import json
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal, engine, ensure_sqlite_dev_schema, get_db, uses_sqlite
from .auth import CurrentUser, ROLE_ADMIN, ROLE_SUPERADMIN, ROLE_USER, get_current_user, require_roles
from .domain import (
    active_policy_version,
    activate_agent_config,
    active_agent_config,
    available_orders_for_customer,
    candidate_policy_version,
    consumer_tickets,
    create_consumer_ticket,
    get_agent_config_or_404,
    get_policy_source_or_404,
    get_policy_version_or_404,
    frozen_fixture_coverage,
    latest_evaluation_run,
    logistics_context,
    order_context,
    project_review_bundle,
    process_ticket,
    publish_policy_version,
    review_ticket,
    rollback_agent_config,
    rollback_policy_version,
    search_active_public_policy,
    run_offline_evaluation,
    run_config_sandbox,
    run_real_evaluation,
    run_policy_regression,
    seed,
    submit_evidence,
    sync_policy_source,
    take_over_ticket,
    upload_evidence_assets,
    EvidenceUpload,
)
from .models import (
    ActionProposal,
    AgentRun,
    AgentConfigVersion,
    AuditEvent,
    ConfigAuditEvent,
    ConfigSandboxRun,
    EvidenceAsset,
    EvaluationRun,
    PolicyAuditEvent,
    PolicyGroundingChunk,
    PolicyRegressionRun,
    PolicySource,
    PolicySourceSnapshot,
    PolicyVersion,
    RealEvaluationRun,
    Ticket,
    ToolExecution,
)
from .public_efficiency import completed_task_ids, create_or_resume_session, participant_assignments, start_task, submit_task, task_out
from .schemas import (
    ActivateConfigRequest,
    AgentConfigCreateRequest,
    AgentConfigDetail,
    AgentConfigOut,
    AgentRunOut,
    AuditEventOut,
    AuthUserOut,
    ConfigAuditEventOut,
    ConsumerTicketOut,
    EvaluationRunOut,
    EvidenceAssetOut,
    FixtureCoverageOut,
    OrderOut,
    SandboxRunOut,
    PolicyAuditEventOut,
    PolicyGroundingChunkOut,
    PolicyGroundingSearchResult,
    PolicyRegressionOut,
    PolicySourceDetail,
    PolicySourceOut,
    PolicySourceSnapshotOut,
    PolicyVersionOut,
    PublishRequest,
    PublicEfficiencyRecordOut,
    PublicEfficiencyRecordRequest,
    PublicEfficiencySessionOut,
    PublicEfficiencySessionRequest,
    PublicEfficiencyStartOut,
    PublicEfficiencyStartRequest,
    RealEvaluationRunOut,
    ReviewRequest,
    RollbackRequest,
    TakeOverRequest,
    TicketCreateRequest,
    TicketDetail,
    TicketSummary,
    ToolExecutionOut,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if uses_sqlite():
        ensure_sqlite_dev_schema()
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="CarePilot API", version="0.1.0", lifespan=lifespan)
cors_allowed_origins = [origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+$",
    allow_methods=["*"],
    allow_headers=["*"],
)


def ticket_summary(ticket: Ticket) -> TicketSummary:
    return TicketSummary(
        id=ticket.id,
        title=ticket.title,
        customer=ticket.customer,
        category=ticket.category,
        scenario=ticket.scenario,
        risk=ticket.risk,
        status=ticket.status,
        order_id=ticket.order_id,
        execution_mode=ticket.execution_mode,
        updated_at=ticket.updated_at,
    )


def consumer_ticket_out(db: Session, ticket: Ticket) -> ConsumerTicketOut:
    proposal = db.scalar(select(ActionProposal).where(ActionProposal.ticket_id == ticket.id).order_by(ActionProposal.id.desc()))
    return ConsumerTicketOut(**ticket_summary(ticket).model_dump(), customer_message=None if not proposal else proposal.customer_message)


def ticket_detail(db: Session, ticket: Ticket) -> TicketDetail:
    proposal = db.scalar(select(ActionProposal).where(ActionProposal.ticket_id == ticket.id))
    tools = db.scalars(
        select(ToolExecution).where(ToolExecution.ticket_id == ticket.id).order_by(ToolExecution.created_at)
    ).all()
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.ticket_id == ticket.id).order_by(AuditEvent.created_at)
    ).all()
    evidence_assets = db.scalars(
        select(EvidenceAsset).where(EvidenceAsset.ticket_id == ticket.id).order_by(EvidenceAsset.created_at)
    ).all()
    runs = db.scalars(
        select(AgentRun).where(AgentRun.ticket_id == ticket.id).order_by(AgentRun.created_at.desc())
    ).all()
    return TicketDetail(
        **ticket_summary(ticket).model_dump(),
        request_text=ticket.request_text,
        order_context=order_context(ticket.order_id),
        logistics_context=logistics_context(ticket.order_id),
        proposal=None if not proposal else {
            "action": proposal.action,
            "status": proposal.status,
            "rationale": proposal.rationale,
            "customer_message": proposal.customer_message,
            "confidence": proposal.confidence,
            "permission_decision": proposal.permission_decision,
            "policy_citations": json.loads(proposal.policy_citations_json or "[]"),
        },
        evidence_assets=[EvidenceAssetOut(
            id=item.id,
            fixture_id=item.fixture_id,
            content_type=item.content_type,
            input_byte_size=item.input_byte_size,
            sanitized_byte_size=item.sanitized_byte_size,
            exif_removed=item.exif_removed,
            analysis_origin=item.analysis_origin,
            evidence_type=item.evidence_type,
            damage_type=item.damage_type,
            damage_location=item.damage_location,
            packaging_status=item.packaging_status,
            missing_parts=item.missing_parts,
            label_match=item.label_match,
            image_quality=item.image_quality,
            confidence=item.confidence,
            model_needs_human_review=item.model_needs_human_review,
            needs_human_review=item.needs_human_review,
            review_reason=item.review_reason,
            review_gate_reasons=json.loads(item.review_gate_reasons_json or "[]"),
            model_id=item.model_id,
            prompt_version=item.prompt_version,
            vision_run_id=item.vision_run_id,
            created_at=item.created_at,
        ) for item in evidence_assets],
        tool_executions=[ToolExecutionOut(
            tool_name=item.tool_name, outcome=item.outcome, summary=item.summary,
            tool_version=item.tool_version, input_json=item.input_json, output_json=item.output_json,
            caller=item.caller, state_impact=item.state_impact, created_at=item.created_at,
        ) for item in tools],
        audit_events=[AuditEventOut(event_type=item.event_type, summary=item.summary, created_at=item.created_at) for item in events],
        agent_runs=[AgentRunOut(
            id=item.id, execution_mode=item.execution_mode, stage=item.stage, status=item.status,
            model_id=item.model_id, prompt_version=item.prompt_version, input_json=item.input_json,
            output_json=item.output_json, tool_calls=json.loads(item.tool_calls_json or "[]"),
            policy_evidence=json.loads(item.policy_evidence_json or "[]"), latency_ms=item.latency_ms,
            input_tokens=item.input_tokens, output_tokens=item.output_tokens, cost_usd=item.cost_usd,
            failure_type=item.failure_type, failure_detail=item.failure_detail, created_at=item.created_at,
            completed_at=item.completed_at,
        ) for item in runs],
    )


def get_ticket_or_404(db: Session, ticket_id: str) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="未找到这张工单")
    return ticket


def policy_version_out(version: PolicyVersion | None) -> PolicyVersionOut | None:
    if not version:
        return None
    return PolicyVersionOut(
        id=version.id,
        version=version.version,
        status=version.status,
        diff_summary=version.diff_summary,
        created_at=version.created_at,
        published_by=version.published_by,
        source_snapshot_id=version.source_snapshot_id,
    )


def policy_snapshot_out(snapshot: PolicySourceSnapshot) -> PolicySourceSnapshotOut:
    return PolicySourceSnapshotOut(
        id=snapshot.id,
        pack_id=snapshot.pack_id,
        source_url=snapshot.source_url,
        publisher=snapshot.publisher,
        source_version_label=snapshot.source_version_label,
        source_published_at=snapshot.source_published_at,
        retrieved_at=snapshot.retrieved_at,
        content_checksum=snapshot.content_checksum,
        source_excerpt=snapshot.source_excerpt,
        import_method=snapshot.import_method,
    )


def policy_source_out(db: Session, source: PolicySource) -> PolicySourceOut:
    return PolicySourceOut(
        id=source.id,
        title=source.title,
        source_type=source.source_type,
        sync_schedule=source.sync_schedule,
        publisher=source.publisher,
        source_url=source.source_url,
        source_scope=source.source_scope,
        source_version_label=source.source_version_label,
        source_published_at=source.source_published_at,
        current_checksum=source.current_checksum,
        last_synced_at=source.last_synced_at,
        last_verified_at=source.last_verified_at,
        active_version=policy_version_out(active_policy_version(db, source.id)),
        candidate_version=policy_version_out(candidate_policy_version(db, source.id)),
    )


def policy_source_detail(db: Session, source: PolicySource) -> PolicySourceDetail:
    versions = db.scalars(
        select(PolicyVersion)
        .where(PolicyVersion.source_id == source.id)
        .order_by(PolicyVersion.id.desc())
    ).all()
    regressions = db.scalars(
        select(PolicyRegressionRun)
        .join(PolicyVersion, PolicyRegressionRun.policy_version_id == PolicyVersion.id)
        .where(PolicyVersion.source_id == source.id)
        .order_by(PolicyRegressionRun.id.desc())
    ).all()
    events = db.scalars(
        select(PolicyAuditEvent)
        .where(PolicyAuditEvent.source_id == source.id)
        .order_by(PolicyAuditEvent.id.desc())
    ).all()
    snapshots = db.scalars(
        select(PolicySourceSnapshot)
        .where(PolicySourceSnapshot.source_id == source.id)
        .order_by(PolicySourceSnapshot.id.desc())
    ).all()
    latest_snapshot = snapshots[0] if snapshots else None
    chunks = [] if not latest_snapshot else db.scalars(
        select(PolicyGroundingChunk)
        .where(PolicyGroundingChunk.snapshot_id == latest_snapshot.id)
        .order_by(PolicyGroundingChunk.id)
    ).all()
    return PolicySourceDetail(
        **policy_source_out(db, source).model_dump(),
        versions=[policy_version_out(item) for item in versions],
        regressions=[PolicyRegressionOut(id=item.id, status=item.status, summary=item.summary, completed_at=item.completed_at) for item in regressions],
        audit_events=[PolicyAuditEventOut(event_type=item.event_type, summary=item.summary, created_at=item.created_at) for item in events],
        snapshots=[policy_snapshot_out(item) for item in snapshots],
        grounding_chunks=[PolicyGroundingChunkOut(id=item.id, chunk_key=item.chunk_key, category=item.category, title=item.title, content=item.content) for item in chunks],
    )


def agent_config_out(config: AgentConfigVersion) -> AgentConfigOut:
    return AgentConfigOut(
        id=config.id,
        version=config.version,
        status=config.status,
        model_name=config.model_name,
        prompt_version=config.prompt_version,
        tool_allowlist=config.tool_allowlist.split("|"),
        risk_boundary=config.risk_boundary,
        activated_by=config.activated_by,
        created_at=config.created_at,
    )


def agent_config_detail(db: Session, config: AgentConfigVersion) -> AgentConfigDetail:
    versions = db.scalars(select(AgentConfigVersion).order_by(AgentConfigVersion.id.desc())).all()
    sandbox_runs = db.scalars(
        select(ConfigSandboxRun)
        .where(ConfigSandboxRun.config_version_id == config.id)
        .order_by(ConfigSandboxRun.id.desc())
    ).all()
    audit_events = db.scalars(
        select(ConfigAuditEvent)
        .where(ConfigAuditEvent.config_version_id == config.id)
        .order_by(ConfigAuditEvent.id.desc())
    ).all()
    return AgentConfigDetail(
        **agent_config_out(config).model_dump(),
        versions=[agent_config_out(item) for item in versions],
        sandbox_runs=[SandboxRunOut(id=item.id, scenario_id=item.scenario_id, status=item.status, summary=item.summary, completed_at=item.completed_at) for item in sandbox_runs],
        audit_events=[ConfigAuditEventOut(event_type=item.event_type, summary=item.summary, created_at=item.created_at) for item in audit_events],
    )


def evaluation_run_out(run: EvaluationRun) -> EvaluationRunOut:
    return EvaluationRunOut(
        id=run.id,
        fixture_set=run.fixture_set,
        execution_mode=run.execution_mode,
        sample_size=run.sample_size,
        status=run.status,
        manual_avg_minutes=run.manual_avg_minutes,
        agent_avg_minutes=run.agent_avg_minutes,
        proposal_modification_rate=run.proposal_modification_rate,
        policy_top3_hit_rate=run.policy_top3_hit_rate,
        tool_failure_rate=run.tool_failure_rate,
        p95_latency_seconds=run.p95_latency_seconds,
        avg_cost_usd=run.avg_cost_usd,
        bad_cases=json.loads(run.bad_cases_json),
        fixture_coverage=FixtureCoverageOut(**frozen_fixture_coverage(run.fixture_set)),
        source_note=run.source_note,
        completed_at=run.completed_at,
    )


def real_evaluation_run_out(run: RealEvaluationRun) -> RealEvaluationRunOut:
    return RealEvaluationRunOut(
        id=run.id,
        fixture_set=run.fixture_set,
        execution_mode=run.execution_mode,
        model_id=run.model_id,
        prompt_version=run.prompt_version,
        policy_snapshot=run.policy_snapshot,
        status=run.status,
        sample_size=run.sample_size,
        metrics=json.loads(run.metrics_json),
        bad_cases=json.loads(run.bad_cases_json),
        source_note=run.source_note,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@app.get("/health")
def health():
    return {"status": "ok", "storage": "sqlite-dev-fallback" if engine.url.drivername.startswith("sqlite") else "database-url"}


def user_out(user) -> AuthUserOut:
    return AuthUserOut(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


def ensure_ticket_access(ticket: Ticket, user: CurrentUser) -> None:
    if user.role == ROLE_USER and ticket.customer_id != user.id:
        raise HTTPException(status_code=403, detail="只能操作自己的工单")
    if user.role not in {ROLE_USER, ROLE_ADMIN, ROLE_SUPERADMIN}:
        raise HTTPException(status_code=403, detail="你没有操作这张工单的权限")

@app.get("/api/auth/me", response_model=AuthUserOut)
def auth_me(user: CurrentUser = Depends(get_current_user)):
    return user_out(user)


def public_efficiency_session_out(db: Session, participant) -> PublicEfficiencySessionOut:
    assignments = participant_assignments(db, participant.id)
    return PublicEfficiencySessionOut(
        participant_id=participant.id,
        study_mode=participant.study_mode,
        completed_task_ids=completed_task_ids(db, participant.id),
        tasks=[task_out(assignment) for assignment in assignments],
    )


@app.post("/api/public-efficiency/sessions", response_model=PublicEfficiencySessionOut)
def public_efficiency_session(body: PublicEfficiencySessionRequest, db: Session = Depends(get_db)):
    participant = create_or_resume_session(db, body)
    db.commit()
    return public_efficiency_session_out(db, participant)


@app.post("/api/public-efficiency/tasks/{task_id}/start", response_model=PublicEfficiencyStartOut)
def public_efficiency_start(task_id: str, body: PublicEfficiencyStartRequest, db: Session = Depends(get_db)):
    assignment = start_task(db, str(body.participant_id), task_id)
    db.commit()
    return PublicEfficiencyStartOut(task_id=assignment.task_id, started_at=assignment.started_at)


@app.post("/api/public-efficiency/tasks/{task_id}/records", response_model=PublicEfficiencyRecordOut)
def public_efficiency_record(task_id: str, body: PublicEfficiencyRecordRequest, db: Session = Depends(get_db)):
    participant_id = str(body.participant_id)
    submit_task(db, participant_id, task_id, body)
    completed_ids = completed_task_ids(db, participant_id)
    db.commit()
    return PublicEfficiencyRecordOut(completed_task_ids=completed_ids, experiment_completed=len(completed_ids) == 6)


@app.get("/api/orders", response_model=list[OrderOut])
def list_consumer_orders(user: CurrentUser = Depends(require_roles(ROLE_USER)), db: Session = Depends(get_db)):
    orders = [OrderOut(**order) for order in available_orders_for_customer(db, user.id)]
    db.commit()
    return orders


@app.get("/api/consumer/tickets", response_model=list[ConsumerTicketOut])
def list_consumer_tickets(user: CurrentUser = Depends(require_roles(ROLE_USER)), db: Session = Depends(get_db)):
    return [consumer_ticket_out(db, ticket) for ticket in consumer_tickets(db, user)]


@app.get("/api/tickets", response_model=list[TicketSummary])
def list_tickets(_: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    return [ticket_summary(ticket) for ticket in db.scalars(select(Ticket).order_by(Ticket.updated_at.desc())).all()]


@app.post("/api/tickets", response_model=TicketDetail, status_code=201)
def create_ticket(body: TicketCreateRequest, user: CurrentUser = Depends(require_roles(ROLE_USER)), db: Session = Depends(get_db)):
    ticket = create_consumer_ticket(db, user, body.order_id, body.request_text)
    db.commit()
    db.refresh(ticket)
    return ticket_detail(db, ticket)


@app.get("/api/tickets/{ticket_id}", response_model=TicketDetail)
def get_ticket(ticket_id: str, _: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    return ticket_detail(db, get_ticket_or_404(db, ticket_id))


@app.post("/api/tickets/{ticket_id}/process", response_model=TicketDetail)
def process(ticket_id: str, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"), user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = get_ticket_or_404(db, ticket_id)
    ensure_ticket_access(ticket, user)
    ticket = process_ticket(db, ticket, idempotency_key)
    db.commit()
    db.refresh(ticket)
    return ticket_detail(db, ticket)


@app.post("/api/tickets/{ticket_id}/submit-evidence", response_model=TicketDetail)
def evidence(ticket_id: str, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ticket = get_ticket_or_404(db, ticket_id)
    ensure_ticket_access(ticket, user)
    ticket = submit_evidence(db, ticket)
    db.commit()
    db.refresh(ticket)
    return ticket_detail(db, ticket)


@app.post("/api/tickets/{ticket_id}/evidence-files", response_model=TicketDetail, status_code=201)
async def upload_evidence(ticket_id: str, files: list[UploadFile] = File(...), user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if len(files) > 4:
        raise HTTPException(status_code=409, detail="每张工单最多可上传 4 张图片")
    uploads = []
    for file in files:
        content = await file.read(8 * 1024 * 1024 + 1)
        await file.close()
        uploads.append(EvidenceUpload(filename=file.filename, declared_content_type=file.content_type, content=content))
    ticket = get_ticket_or_404(db, ticket_id)
    ensure_ticket_access(ticket, user)
    ticket = upload_evidence_assets(db, ticket, uploads)
    db.commit()
    db.refresh(ticket)
    return ticket_detail(db, ticket)


@app.post("/api/tickets/{ticket_id}/review", response_model=TicketDetail)
def review(ticket_id: str, body: ReviewRequest, user: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    ticket = review_ticket(
        db, get_ticket_or_404(db, ticket_id), body.decision, body.note,
        f"{user.display_name}（{user.email or user.id}）", body.modified_action, body.modified_rationale,
    )
    db.commit()
    db.refresh(ticket)
    return ticket_detail(db, ticket)


@app.post("/api/tickets/{ticket_id}/take-over", response_model=TicketDetail)
def take_over(ticket_id: str, body: TakeOverRequest, user: CurrentUser = Depends(require_roles(ROLE_ADMIN, ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    ticket = take_over_ticket(db, get_ticket_or_404(db, ticket_id), body.note, f"{user.display_name}（{user.email or user.id}）")
    db.commit()
    db.refresh(ticket)
    return ticket_detail(db, ticket)


@app.get("/api/policy-sources", response_model=list[PolicySourceOut])
def list_policy_sources(_: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    return [policy_source_out(db, source) for source in db.scalars(select(PolicySource).order_by(PolicySource.id)).all()]


@app.get("/api/policy-sources/{source_id}", response_model=PolicySourceDetail)
def get_policy_source(source_id: str, _: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    return policy_source_detail(db, get_policy_source_or_404(db, source_id))


@app.get("/api/policy-grounding/search", response_model=list[PolicyGroundingSearchResult])
def policy_grounding_search(q: str, category: str | None = None, _: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    return search_active_public_policy(db, q, category)


@app.post("/api/policy-sources/{source_id}/sync", response_model=PolicySourceDetail)
def sync_policy(source_id: str, _: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    source = get_policy_source_or_404(db, source_id)
    sync_policy_source(db, source)
    db.commit()
    return policy_source_detail(db, source)


@app.get("/api/policy-versions/{version_id}/diff", response_model=PolicyVersionOut)
def policy_diff(version_id: int, _: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    return policy_version_out(get_policy_version_or_404(db, version_id))


@app.post("/api/policy-versions/{version_id}/regression", response_model=PolicySourceDetail)
def policy_regression(version_id: int, _: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    version = get_policy_version_or_404(db, version_id)
    run_policy_regression(db, version)
    db.commit()
    return policy_source_detail(db, get_policy_source_or_404(db, version.source_id))


@app.post("/api/policy-versions/{version_id}/publish", response_model=PolicySourceDetail)
def policy_publish(version_id: int, body: PublishRequest, user: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    version = get_policy_version_or_404(db, version_id)
    publish_policy_version(db, version, user.email or user.id)
    db.commit()
    return policy_source_detail(db, get_policy_source_or_404(db, version.source_id))


@app.post("/api/policy-versions/{version_id}/rollback", response_model=PolicySourceDetail)
def policy_rollback(version_id: int, body: RollbackRequest, user: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    version = get_policy_version_or_404(db, version_id)
    rollback_policy_version(db, version, user.email or user.id)
    db.commit()
    return policy_source_detail(db, get_policy_source_or_404(db, version.source_id))


@app.get("/api/agent-configs", response_model=list[AgentConfigOut])
def list_agent_configs(_: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    return [agent_config_out(item) for item in db.scalars(select(AgentConfigVersion).order_by(AgentConfigVersion.id.desc())).all()]


@app.post("/api/agent-configs", response_model=AgentConfigDetail, status_code=201)
def create_agent_config(body: AgentConfigCreateRequest, _: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    config = AgentConfigVersion(
        version=body.version,
        status="DRAFT",
        model_name=body.model_name,
        prompt_version=body.prompt_version,
        tool_allowlist="|".join(body.tool_allowlist),
        risk_boundary=body.risk_boundary,
    )
    db.add(config)
    db.flush()
    from .domain import config_audit
    config_audit(db, config.id, "config.draft_created", "管理员创建了新的 Agent 配置草稿")
    db.commit()
    return agent_config_detail(db, config)


@app.get("/api/agent-configs/{config_id}", response_model=AgentConfigDetail)
def get_agent_config(config_id: int, _: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    return agent_config_detail(db, get_agent_config_or_404(db, config_id))


@app.post("/api/agent-configs/{config_id}/sandbox", response_model=AgentConfigDetail)
def config_sandbox(config_id: int, _: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    config = get_agent_config_or_404(db, config_id)
    run_config_sandbox(db, config)
    db.commit()
    return agent_config_detail(db, config)


@app.post("/api/agent-configs/{config_id}/activate", response_model=AgentConfigDetail)
def config_activate(config_id: int, body: ActivateConfigRequest, user: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    config = get_agent_config_or_404(db, config_id)
    activate_agent_config(db, config, user.email or user.id)
    db.commit()
    return agent_config_detail(db, config)


@app.post("/api/agent-configs/{config_id}/rollback", response_model=AgentConfigDetail)
def config_rollback(config_id: int, body: ActivateConfigRequest, user: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    config = get_agent_config_or_404(db, config_id)
    rollback_agent_config(db, config, user.email or user.id)
    db.commit()
    return agent_config_detail(db, config)


@app.get("/api/evaluations/latest", response_model=EvaluationRunOut)
def get_latest_evaluation(_: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    run = latest_evaluation_run(db)
    if not run:
        raise HTTPException(status_code=404, detail="暂无离线评测记录")
    return evaluation_run_out(run)


@app.post("/api/evaluations/run", response_model=EvaluationRunOut)
def run_evaluation(_: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    run = run_offline_evaluation()
    db.add(run)
    db.commit()
    db.refresh(run)
    return evaluation_run_out(run)


@app.get("/api/evaluations/real/latest", response_model=RealEvaluationRunOut)
def latest_real_evaluation(_: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    run = db.scalar(select(RealEvaluationRun).order_by(RealEvaluationRun.created_at.desc()))
    if not run:
        raise HTTPException(status_code=404, detail="暂无真实模型评测记录")
    return real_evaluation_run_out(run)


@app.post("/api/evaluations/real/run", response_model=RealEvaluationRunOut)
def run_real_agent_evaluation(_: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    run = run_real_evaluation(db)
    db.commit()
    db.refresh(run)
    return real_evaluation_run_out(run)


@app.get("/api/project-review-bundle")
def download_project_review_bundle(_: CurrentUser = Depends(require_roles(ROLE_SUPERADMIN)), db: Session = Depends(get_db)):
    payload = jsonable_encoder(project_review_bundle(db))
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="carepilot-project-review-v0.1.json"'},
    )
