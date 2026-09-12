import hashlib
import hmac
import json
import os
from collections import Counter
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .database import uses_sqlite
from .models import CustomerEfficiencyAssignment, CustomerEfficiencyParticipant, CustomerEfficiencyRecord
from .schemas import (
    PublicEfficiencyRecordRequest,
    PublicEfficiencySessionRequest,
    PublicEfficiencyTaskOut,
)


FIXTURE_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "customer-efficiency-tasks-v1.json"
FIELD_LABELS = {
    "case_summary": "用户遇到的问题",
    "order": "订单信息",
    "logistics": "物流或签收信息",
    "policy": "处理规则",
    "evidence": "用户提供的图片或材料",
    "proposal_risk": "下一步怎么处理",
}


def _plain_text(value: str) -> str:
    return (
        value.replace("人工审核 Proposal", "人工进一步确认")
        .replace("Proposal", "处理建议")
        .replace("replace.propose", "提交处理建议")
        .replace("Evidence", "图片材料")
        .replace("Agent", "系统")
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@lru_cache(maxsize=1)
def fixture_pairs() -> dict[str, dict]:
    fixture = json.loads(FIXTURE_PATH.read_text())
    pairs = fixture.get("pairs", [])
    if len(pairs) != 12 or len({item["pair_id"] for item in pairs}) != 12:
        raise RuntimeError("客服提效题库不完整，拒绝开放实验。")
    return {pair["pair_id"]: pair for pair in pairs}


def pair_for_task_id(task_id: str) -> tuple[dict, str]:
    if task_id.endswith("-M"):
        pair_id, condition = task_id[:-2], "MANUAL"
    elif task_id.endswith("-D"):
        pair_id, condition = task_id[:-2], "DECISION_PACKAGE"
    else:
        raise HTTPException(status_code=404, detail="未找到这道题")
    pair = fixture_pairs().get(pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="未找到这道题")
    return pair, condition


def _source_label(source: dict) -> str:
    return f"查看{FIELD_LABELS[source['field']]}"


def task_out(assignment: CustomerEfficiencyAssignment) -> PublicEfficiencyTaskOut:
    pair, expected_condition = pair_for_task_id(assignment.task_id)
    if assignment.condition != expected_condition:
        raise RuntimeError(f"题目分配条件不一致：{assignment.task_id}")
    decision_package = None
    if assignment.condition == "DECISION_PACKAGE":
        package = pair["decision_package"]
        decision_package = {
            "summary": _plain_text(package["summary"]),
            "fields": [
                {
                    "label": FIELD_LABELS[field],
                    "status": "信息已准备好" if package["field_status"][field] == "READY" else "还缺信息",
                }
                for field in pair["required_information_fields"]
            ],
            "missing_information": [_plain_text(item) for item in package["missing_information"]],
            "policy_citation": _plain_text(package["policy_citation"]),
            "recommendation": _plain_text(package["recommendation"]),
            "system_actions": [_plain_text(item) for item in package["system_actions"]],
        }
    return PublicEfficiencyTaskOut(
        task_id=assignment.task_id,
        pair_id=assignment.pair_id,
        round=assignment.round,
        condition=assignment.condition,
        prompt=_plain_text(pair["prompt"]),
        requires_human_confirmation=bool(pair["requires_human_review"]),
        sources=[{"id": source["id"], "label": _source_label(source), "content": _plain_text(source["content"])} for source in pair["manual_sources"]],
        decision_package=decision_package,
    )


def _validate_study_access(body: PublicEfficiencySessionRequest) -> None:
    if body.study_mode != "PILOT":
        return
    expected_code = os.getenv("EFFICIENCY_PILOT_ACCESS_CODE")
    if not expected_code or not body.pilot_access_code or not hmac.compare_digest(expected_code, body.pilot_access_code):
        raise HTTPException(status_code=403, detail="内部试跑入口不可用")


def _allocation_lock(db: Session) -> None:
    if not uses_sqlite():
        db.execute(text("select pg_advisory_xact_lock(2147192301)"))


def _task_counts(db: Session, study_mode: str) -> tuple[Counter[str], Counter[str], Counter[str]]:
    completed_tasks = Counter(dict(db.execute(
        select(CustomerEfficiencyRecord.task_id, func.count(CustomerEfficiencyRecord.id))
        .where(CustomerEfficiencyRecord.study_mode == study_mode)
        .group_by(CustomerEfficiencyRecord.task_id)
    ).all()))
    assigned_tasks = Counter(dict(db.execute(
        select(CustomerEfficiencyAssignment.task_id, func.count(CustomerEfficiencyAssignment.id))
        .join(CustomerEfficiencyParticipant, CustomerEfficiencyParticipant.id == CustomerEfficiencyAssignment.participant_id)
        .where(CustomerEfficiencyParticipant.study_mode == study_mode)
        .group_by(CustomerEfficiencyAssignment.task_id)
    ).all()))
    completed_conditions = Counter(dict(db.execute(
        select(CustomerEfficiencyRecord.condition, func.count(CustomerEfficiencyRecord.id))
        .where(CustomerEfficiencyRecord.study_mode == study_mode)
        .group_by(CustomerEfficiencyRecord.condition)
    ).all()))
    return completed_tasks, assigned_tasks, completed_conditions


def _condition_order(completed_conditions: Counter[str], participant_id: str) -> list[str]:
    manual_count = completed_conditions["MANUAL"]
    package_count = completed_conditions["DECISION_PACKAGE"]
    if manual_count < package_count:
        first = "MANUAL"
    elif package_count < manual_count:
        first = "DECISION_PACKAGE"
    else:
        first = "MANUAL" if int(hashlib.sha256(participant_id.encode()).hexdigest(), 16) % 2 == 0 else "DECISION_PACKAGE"
    other = "DECISION_PACKAGE" if first == "MANUAL" else "MANUAL"
    return [first, other, first, other, first, other]


def _choose_task_id(
    participant_id: str,
    condition: str,
    excluded_pair_ids: set[str],
    completed_tasks: Counter[str],
    assigned_tasks: Counter[str],
) -> tuple[str, str]:
    suffix = "M" if condition == "MANUAL" else "D"
    candidates = [pair_id for pair_id in fixture_pairs() if pair_id not in excluded_pair_ids]
    if not candidates:
        raise RuntimeError("可分配题目不足")

    def rank(pair_id: str) -> tuple[int, int, str]:
        task_id = f"{pair_id}-{suffix}"
        tie_break = hashlib.sha256(f"{participant_id}:{task_id}".encode()).hexdigest()
        return completed_tasks[task_id], assigned_tasks[task_id], tie_break

    pair_id = min(candidates, key=rank)
    return pair_id, f"{pair_id}-{suffix}"


def _allocate_assignments(db: Session, participant: CustomerEfficiencyParticipant) -> None:
    completed_tasks, assigned_tasks, completed_conditions = _task_counts(db, participant.study_mode)
    used_pair_ids: set[str] = set()
    for round_number, condition in enumerate(_condition_order(completed_conditions, participant.id), start=1):
        pair_id, task_id = _choose_task_id(participant.id, condition, used_pair_ids, completed_tasks, assigned_tasks)
        db.add(CustomerEfficiencyAssignment(
            participant_id=participant.id,
            task_id=task_id,
            pair_id=pair_id,
            condition=condition,
            round=round_number,
        ))
        used_pair_ids.add(pair_id)
        assigned_tasks[task_id] += 1


def create_or_resume_session(db: Session, body: PublicEfficiencySessionRequest) -> CustomerEfficiencyParticipant:
    participant_id = str(body.participant_id)
    participant = db.get(CustomerEfficiencyParticipant, participant_id)
    if participant:
        if participant.study_mode != body.study_mode:
            raise HTTPException(status_code=409, detail="此匿名编号已用于另一类实验，不能混合记录。")
        return participant

    _validate_study_access(body)
    _allocation_lock(db)
    participant = CustomerEfficiencyParticipant(id=participant_id, study_mode=body.study_mode)
    db.add(participant)
    db.flush()
    _allocate_assignments(db, participant)
    return participant


def participant_assignments(db: Session, participant_id: str) -> list[CustomerEfficiencyAssignment]:
    return db.scalars(
        select(CustomerEfficiencyAssignment)
        .where(CustomerEfficiencyAssignment.participant_id == participant_id)
        .order_by(CustomerEfficiencyAssignment.round)
    ).all()


def completed_task_ids(db: Session, participant_id: str) -> list[str]:
    return list(db.scalars(
        select(CustomerEfficiencyRecord.task_id)
        .where(CustomerEfficiencyRecord.participant_id == participant_id)
        .order_by(CustomerEfficiencyRecord.round)
    ).all())


def start_task(db: Session, participant_id: str, task_id: str) -> CustomerEfficiencyAssignment:
    assignment = db.scalar(select(CustomerEfficiencyAssignment).where(
        CustomerEfficiencyAssignment.participant_id == participant_id,
        CustomerEfficiencyAssignment.task_id == task_id,
    ))
    if not assignment:
        raise HTTPException(status_code=404, detail="这道题不属于当前实验。")
    if assignment.completed_at:
        raise HTTPException(status_code=409, detail="这道题已经提交，不能重复计入。")
    if not assignment.started_at:
        assignment.started_at = datetime.now(UTC)
        db.flush()
    return assignment


def submit_task(db: Session, participant_id: str, task_id: str, body: PublicEfficiencyRecordRequest) -> CustomerEfficiencyRecord:
    assignment = db.scalar(select(CustomerEfficiencyAssignment).where(
        CustomerEfficiencyAssignment.participant_id == participant_id,
        CustomerEfficiencyAssignment.task_id == task_id,
    ))
    participant = db.get(CustomerEfficiencyParticipant, participant_id)
    if not assignment or not participant:
        raise HTTPException(status_code=404, detail="未找到当前实验或题目。")
    if db.scalar(select(CustomerEfficiencyRecord).where(CustomerEfficiencyRecord.participant_id == participant_id, CustomerEfficiencyRecord.task_id == task_id)):
        raise HTTPException(status_code=409, detail="这道题已经正式提交，不能重复计入。")
    if not assignment.started_at:
        raise HTTPException(status_code=409, detail="请先点击“开始做题”。")

    pair, expected_condition = pair_for_task_id(task_id)
    if assignment.condition != expected_condition:
        raise HTTPException(status_code=409, detail="题目条件不一致，无法提交。")
    source_ids = [source["id"] for source in pair["manual_sources"]]
    if len(set(body.source_actions)) != len(body.source_actions) or any(source_id not in source_ids for source_id in body.source_actions):
        raise HTTPException(status_code=422, detail="查看记录不符合本题信息来源。")

    is_high_risk = bool(pair["requires_human_review"])
    if is_high_risk and (body.selected_outcome != "WAITING_REVIEW" or not body.high_risk_gate_observed):
        raise HTTPException(status_code=422, detail="这题需要先选择交给人工进一步确认。")
    if not is_high_risk and body.proposal_outcome is not None:
        raise HTTPException(status_code=422, detail="只有需要人工确认的题目才记录处理建议结果。")
    if is_high_risk and assignment.condition == "DECISION_PACKAGE" and body.proposal_outcome is None:
        raise HTTPException(status_code=422, detail="请记录你会怎样处理系统整理的建议。")

    source_by_id = {source["id"]: source for source in pair["manual_sources"]}
    source_fields_viewed = list(dict.fromkeys(source_by_id[source_id]["field"] for source_id in body.source_actions))
    required_fields = pair["required_information_fields"]
    if assignment.condition == "DECISION_PACKAGE":
        ready_fields = [field for field in required_fields if pair["decision_package"]["field_status"][field] == "READY"]
        missing_fields = [field for field in required_fields if pair["decision_package"]["field_status"][field] == "MISSING"]
    else:
        observed_fields = set(source_fields_viewed) | {"proposal_risk"}
        ready_fields = [field for field in required_fields if field in observed_fields]
        missing_fields = [field for field in required_fields if field not in observed_fields]

    started_at = _as_utc(assignment.started_at)
    completed_at = datetime.now(UTC)
    duration_seconds = max(0, round((completed_at - started_at).total_seconds()))
    if body.active_duration_seconds is not None and body.active_duration_seconds > duration_seconds + 5:
        raise HTTPException(status_code=422, detail="实际作答时长不能超过本题已开始的时间。")
    record = CustomerEfficiencyRecord(
        participant_id=participant_id,
        assignment_id=assignment.id,
        study_mode=participant.study_mode,
        task_id=task_id,
        pair_id=assignment.pair_id,
        condition=assignment.condition,
        round=assignment.round,
        category=pair["category"],
        scenario=pair["scenario"],
        risk=pair["risk"],
        selected_outcome=body.selected_outcome,
        outcome_correct=body.selected_outcome == pair["target_outcome"],
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration_seconds,
        active_duration_seconds=min(body.active_duration_seconds, duration_seconds) if body.active_duration_seconds is not None else None,
        source_actions_json=json.dumps(body.source_actions, ensure_ascii=False),
        source_fields_viewed_json=json.dumps(source_fields_viewed, ensure_ascii=False),
        decision_package_ready_fields_json=json.dumps(ready_fields if assignment.condition == "DECISION_PACKAGE" else [], ensure_ascii=False),
        decision_package_missing_fields_json=json.dumps(missing_fields if assignment.condition == "DECISION_PACKAGE" else [], ensure_ascii=False),
        information_completeness_percent=round(100 * len(ready_fields) / len(required_fields), 2),
        high_risk_gate_observed=body.high_risk_gate_observed if is_high_risk else None,
        proposal_outcome=body.proposal_outcome if is_high_risk and assignment.condition == "DECISION_PACKAGE" else None,
        ease_rating_1_to_7=body.ease_rating_1_to_7,
        observer_notes=body.observer_notes.strip(),
    )
    assignment.completed_at = completed_at
    db.add(record)
    db.flush()
    if len(completed_task_ids(db, participant_id)) == 6:
        participant.completed_at = completed_at
    return record
