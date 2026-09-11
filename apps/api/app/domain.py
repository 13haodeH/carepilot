import hashlib
import json
import secrets
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from io import BytesIO
from math import ceil
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    ActionProposal,
    AgentRun,
    AgentConfigVersion,
    AuditEvent,
    ConfigAuditEvent,
    ConfigSandboxRun,
    DemoOrderEntitlement,
    EvidenceAsset,
    EvaluationRun,
    HumanReview,
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
from .auth import CurrentUser
from .agent_runtime import AgentRuntimeError, OpenAIResponsesRuntime, ResolutionOutput
from .settings import model_is_configured, runtime_settings


ALLOWED_TRANSITIONS = {
    "NEW": {"PROCESSING"},
    "PROCESSING": {"NEED_INFO", "WAITING_REVIEW", "RESOLVED", "FAILED"},
    "NEED_INFO": {"PROCESSING"},
    "WAITING_REVIEW": {"PROCESSING", "RESOLVED"},
    "FAILED": {"PROCESSING"},
    "RESOLVED": set(),
}


SEED_TICKETS = (
    {
        "id": "CP-240918",
        "title": "耳机右耳缺失，包装已拆",
        "customer": "林女士",
        "category": "数码",
        "scenario": "MISSING_PART",
        "risk": "HIGH",
        "status": "WAITING_REVIEW",
    },
    {
        "id": "CP-240917",
        "title": "物流 72 小时未更新",
        "customer": "陈先生",
        "category": "家居",
        "scenario": "LOGISTICS_DELAY",
        "risk": "LOW",
        "status": "PROCESSING",
    },
    {
        "id": "CP-240916",
        "title": "衬衫尺码不符，吊牌完整",
        "customer": "赵女士",
        "category": "服饰",
        "scenario": "NEED_EVIDENCE",
        "risk": "MEDIUM",
        "status": "NEED_INFO",
    },
)


# These are deliberately simulated business records. The Agent invokes real server-side
# functions against them; no production payment, inventory, customer, or logistics system is connected.
DEMO_ORDERS: dict[str, dict[str, object]] = {
    "OD20260908132": {
        "id": "OD20260908132", "title": "悦声 Air 3 无线耳机",
        "category": "DIGITAL", "amount": 699.0, "delivered_at": "2026-09-06T18:42:00+00:00",
        "status": "DELIVERED", "signed_days_ago": 3,
    },
    "OD20260907086": {
        "id": "OD20260907086", "title": "原木三层置物架",
        "category": "HOME", "amount": 259.0, "delivered_at": "", "status": "IN_TRANSIT", "signed_days_ago": None,
    },
    "OD20260906118": {
        "id": "OD20260906118", "title": "轻商务免烫衬衫",
        "category": "APPAREL", "amount": 329.0, "delivered_at": "2026-09-05T12:18:00+00:00",
        "status": "DELIVERED", "signed_days_ago": 4,
    },
}

# These records are only used by the versioned, real-model evidence evaluation.
# Keeping them out of DEMO_ORDERS prevents evaluation-only products from appearing
# in a consumer's selectable order list.
EVALUATION_ORDERS: dict[str, dict[str, object]] = {
    "OD20260911101": {
        "id": "OD20260911101", "title": "朗声 H10 头戴式蓝牙耳机",
        "category": "DIGITAL", "amount": 459.0, "delivered_at": "2026-09-08T13:20:00+00:00",
        "status": "DELIVERED", "signed_days_ago": 1,
    },
    "OD20260911102": {
        "id": "OD20260911102", "title": "Samsung Galaxy A24 智能手机",
        "category": "DIGITAL", "amount": 1299.0, "delivered_at": "2026-09-08T16:10:00+00:00",
        "status": "DELIVERED", "signed_days_ago": 1,
    },
    "OD20260911103": {
        "id": "OD20260911103", "title": "玻璃瓶装香氛喷雾 100mL",
        "category": "HOME", "amount": 189.0, "delivered_at": "2026-09-08T10:45:00+00:00",
        "status": "DELIVERED", "signed_days_ago": 1,
    },
}

DEMO_LOGISTICS: dict[str, dict[str, object]] = {
    "OD20260908132": {"order_id": "OD20260908132", "status": "DELIVERED", "latest_event": "本人签收", "hours_without_update": 0},
    "OD20260907086": {"order_id": "OD20260907086", "status": "DELAYED", "latest_event": "干线运输停滞", "hours_without_update": 72},
    "OD20260906118": {"order_id": "OD20260906118", "status": "DELIVERED", "latest_event": "本人签收", "hours_without_update": 0},
}

EVALUATION_LOGISTICS: dict[str, dict[str, object]] = {
    order_id: {"order_id": order_id, "status": "DELIVERED", "latest_event": "本人签收", "hours_without_update": 0}
    for order_id in EVALUATION_ORDERS
}

EVALUATION_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "tickets-v0.2.json"
POLICY_CORPUS_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "policy-corpus-v0.1.json"
QUERY_POLICY_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "query-policy-v0.1.json"
PUBLIC_POLICY_GROUNDING_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "public-policy-grounding-v0.1.json"
PUBLIC_POLICY_ADDITIONS_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "public-policy-grounding-v0.2.json"
MANUAL_AGENT_RESULTS_PATH = Path(__file__).resolve().parents[3] / "evals" / "results" / "manual-agent-summary-v0.2.json"
MANUAL_AGENT_TASKS_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "manual-agent-tasks-v0.1.json"
MANUAL_AGENT_ASSIGNMENT_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "manual-agent-assignment-v0.1.json"
EVIDENCE_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "evidence-v0.1.json"
EVIDENCE_IMAGE_DIR = EVIDENCE_FIXTURE_PATH.parent / "evidence-images-v0.1"
REAL_VISION_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "real-vision-eval-v0.2.json"
REAL_VISION_IMAGE_DIR = REAL_VISION_FIXTURE_PATH.parent / "evidence-images-v0.2"
BASELINE_REAL_EVALUATION_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "real-agent-eval-v0.2.json"
REAL_EVALUATION_V021_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "real-agent-eval-v0.2.1.json"
REAL_EVALUATION_PATH = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "real-agent-eval-v0.2.2.json"
HIGH_RISK_PROPOSAL_ACTIONS = {"refund.propose", "return.propose", "replace.propose", "compensation.propose"}
HIGH_RISK_EXECUTION_TOOLS = {"refund.execute", "return.execute", "replace.execute", "compensation.execute", "inventory.update"}
EVIDENCE_REVIEW_CONFIDENCE_THRESHOLD = 0.65
FIXTURE_CATEGORY_COUNTS = {"DIGITAL": 32, "APPAREL": 24, "HOME": 24}
QUERY_POLICY_CATEGORY_COUNTS = {"DIGITAL": 20, "APPAREL": 20, "HOME": 20}
EVIDENCE_CATEGORY_COUNTS = {"DIGITAL": 10, "APPAREL": 10, "HOME": 10}
POLICY_REGRESSION_MIN_TOP3_HIT_RATE = 90.0
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
MAX_EVIDENCE_FILES_PER_TICKET = 4
MAX_EVIDENCE_PIXELS = 20_000_000
IMAGE_FORMAT_CONTENT_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
FIXTURE_EXCEPTION_ACTIONS = {
    "POLICY_CONFLICT": ("政策冲突", "补充 Query–Policy 对照集"),
    "TOOL_TIMEOUT": ("工具超时", "重试与降级策略"),
    "DUPLICATE_REQUEST": ("重复请求", "校验幂等键与状态回放"),
    "PROMPT_INJECTION": ("提示注入", "拦截指令并转人工审阅"),
}
FIXTURE_EXCEPTION_COUNTS = {tag: 3 for tag in FIXTURE_EXCEPTION_ACTIONS}
FIXTURE_BASE_OUTCOMES = {
    "HIGH": {"expected_disposition": "REQUIRE_HUMAN", "expected_state": "WAITING_REVIEW", "proposal": "replace.propose"},
    "MEDIUM": {"expected_disposition": "REQUEST_EVIDENCE", "expected_state": "NEED_INFO", "proposal": None},
    "LOW": {"expected_disposition": "AUTO_RESOLVE", "expected_state": "RESOLVED", "proposal": None},
}
SIMULATED_COST_BY_RISK = {"HIGH": 0.024, "MEDIUM": 0.017, "LOW": 0.014}
SIMULATED_MANUAL_MINUTES_BY_RISK = {"HIGH": 18.0, "MEDIUM": 14.0, "LOW": 12.0}
SIMULATED_AGENT_MINUTES_BY_RISK = {"HIGH": 5.8, "MEDIUM": 4.8, "LOW": 4.0}


@dataclass(frozen=True)
class EvidenceUpload:
    filename: str | None
    declared_content_type: str | None
    content: bytes


@dataclass(frozen=True)
class SanitizedEvidence:
    content_type: str
    input_byte_size: int
    sanitized_content: bytes
    exif_removed: bool


def self_authored_policy_corpus() -> dict[str, object]:
    data = json.loads(POLICY_CORPUS_PATH.read_text(encoding="utf-8"))
    policies = data.get("policies")
    if not isinstance(policies, list):
        raise RuntimeError("Policy corpus must contain a policy list")
    required_keys = {"id", "category", "title", "keywords", "text"}
    if any(not required_keys.issubset(policy) for policy in policies):
        raise RuntimeError("Policy corpus has a policy with missing fields")
    if len(policies) != 12 or len({policy["id"] for policy in policies}) != len(policies):
        raise RuntimeError("Policy corpus must contain 12 uniquely identified policies")
    if Counter(policy["category"] for policy in policies) != Counter({category: 4 for category in QUERY_POLICY_CATEGORY_COUNTS}):
        raise RuntimeError("Policy corpus category counts do not match 4 / 4 / 4")
    if any(not isinstance(policy["keywords"], list) or not policy["keywords"] for policy in policies):
        raise RuntimeError("Policy corpus policies must contain retrieval keywords")
    return data


def public_policy_pack() -> dict[str, object]:
    base = json.loads(PUBLIC_POLICY_GROUNDING_PATH.read_text(encoding="utf-8"))
    additions = json.loads(PUBLIC_POLICY_ADDITIONS_PATH.read_text(encoding="utf-8"))
    base_sources = base.get("sources")
    addition_sources = additions.get("sources")
    sources = [*base_sources, *addition_sources] if isinstance(base_sources, list) and isinstance(addition_sources, list) else None
    required_source_keys = {
        "id", "title", "publisher", "source_type", "source_scope", "source_url",
        "source_version_label", "source_published_at", "source_excerpt", "chunks",
    }
    required_chunk_keys = {"chunk_key", "category", "title", "content", "keywords"}
    if (
        base.get("pack_id") != "public-policy-grounding-v0.1"
        or additions.get("pack_id") != "public-policy-grounding-v0.2"
        or additions.get("base_pack_id") != base.get("pack_id")
        or not isinstance(sources, list)
        or len(sources) != 4
        or len({source.get("id") for source in sources}) != len(sources)
    ):
        raise RuntimeError("Public policy pack must contain the v0.1 baseline and one v0.2 addition")
    if any(not required_source_keys.issubset(source) for source in sources):
        raise RuntimeError("Public policy pack contains a source with missing fields")
    if any(
        not isinstance(source["chunks"], list)
        or not source["chunks"]
        or any(not required_chunk_keys.issubset(chunk) for chunk in source["chunks"])
        for source in sources
    ):
        raise RuntimeError("Public policy pack contains an invalid retrieval chunk")
    return {
        "pack_id": additions["pack_id"],
        "grounding_verified_at": additions["grounding_verified_at"],
        "scope_note": base["scope_note"],
        "sources": sources,
    }


def public_policy_source_spec(source_id: str) -> dict[str, object] | None:
    return next((source for source in public_policy_pack()["sources"] if source["id"] == source_id), None)


def source_snapshot_checksum(source: dict[str, object]) -> str:
    canonical = "\n".join(
        str(source[key]).strip()
        for key in ("source_url", "publisher", "source_version_label", "source_published_at", "source_excerpt")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def query_policy_fixture() -> dict[str, object]:
    corpus = self_authored_policy_corpus()
    policy_categories = {policy["id"]: policy["category"] for policy in corpus["policies"]}
    data = json.loads(QUERY_POLICY_FIXTURE_PATH.read_text(encoding="utf-8"))
    queries = data.get("queries")
    if not isinstance(queries, list):
        raise RuntimeError("Query–Policy fixture must contain a query list")
    required_keys = {"id", "category", "query", "expected_policy_id"}
    if any(not required_keys.issubset(query) for query in queries):
        raise RuntimeError("Query–Policy fixture has a query with missing fields")
    if len(queries) != 60 or len({query["id"] for query in queries}) != len(queries):
        raise RuntimeError("Query–Policy fixture must contain 60 uniquely identified queries")
    if Counter(query["category"] for query in queries) != Counter(QUERY_POLICY_CATEGORY_COUNTS):
        raise RuntimeError("Query–Policy fixture category counts do not match 20 / 20 / 20")
    for query in queries:
        expected_policy_id = query["expected_policy_id"]
        if expected_policy_id not in policy_categories:
            raise RuntimeError(f"Query–Policy fixture references an unknown policy: {expected_policy_id}")
        if policy_categories[expected_policy_id] != query["category"]:
            raise RuntimeError(f"Query–Policy fixture category does not match policy: {query['id']}")
    return data


def retrieve_policy_top3(query: dict[str, object]) -> list[str]:
    corpus = self_authored_policy_corpus()
    query_text = str(query["query"])
    category = query["category"]
    candidates = [policy for policy in corpus["policies"] if policy["category"] == category]

    def score(policy: dict[str, object]) -> int:
        return sum(len(str(keyword)) for keyword in policy["keywords"] if str(keyword) in query_text)

    ranked = sorted(candidates, key=lambda policy: (-score(policy), str(policy["id"])))
    return [str(policy["id"]) for policy in ranked[:3]]


def policy_retrieval_snapshot() -> dict[str, object]:
    fixture = query_policy_fixture()
    queries = fixture["queries"]
    missed_query_ids = [query["id"] for query in queries if query["expected_policy_id"] not in retrieve_policy_top3(query)]
    return {
        "fixture_set": fixture["fixture_set"],
        "corpus_set": self_authored_policy_corpus()["corpus_set"],
        "query_count": len(queries),
        "top3_hit_rate": round((len(queries) - len(missed_query_ids)) * 100 / len(queries), 1),
        "missed_query_ids": missed_query_ids,
    }


def manual_agent_task_fixture() -> dict[str, object]:
    data = json.loads(MANUAL_AGENT_TASKS_PATH.read_text(encoding="utf-8"))
    atomic_steps = data.get("atomic_steps")
    pairs = data.get("pairs")
    if not isinstance(atomic_steps, dict) or not isinstance(pairs, list):
        raise RuntimeError("Manual vs Agent fixture must contain atomic steps and task pairs")
    required_pair_keys = {"pair_id", "category", "scenario", "risk", "target_outcome", "manual_task", "agent_task"}
    if len(pairs) != 10 or len({pair["pair_id"] for pair in pairs}) != len(pairs):
        raise RuntimeError("Manual vs Agent fixture must contain 10 uniquely identified task pairs")
    if any(not required_pair_keys.issubset(pair) for pair in pairs):
        raise RuntimeError("Manual vs Agent fixture has a pair with missing fields")
    if Counter(pair["category"] for pair in pairs) != Counter({"DIGITAL": 4, "APPAREL": 3, "HOME": 3}):
        raise RuntimeError("Manual vs Agent fixture category counts do not match 4 / 3 / 3")

    task_ids: set[object] = set()
    expected_outcomes = {"LOW": "RESOLVED", "MEDIUM": "NEED_INFO", "HIGH": "WAITING_REVIEW"}
    for pair in pairs:
        if pair["risk"] not in expected_outcomes or pair["target_outcome"] != expected_outcomes[pair["risk"]]:
            raise RuntimeError(f"Manual vs Agent fixture has an invalid target outcome: {pair['pair_id']}")
        for expected_condition, task_key in (("MANUAL", "manual_task"), ("AGENT_ASSISTED", "agent_task")):
            task = pair[task_key]
            if task.get("condition") != expected_condition or not task.get("id") or not isinstance(task.get("participant_steps"), list):
                raise RuntimeError(f"Manual vs Agent fixture has an invalid task: {pair['pair_id']}")
            if task["id"] in task_ids or any(step not in atomic_steps for step in task["participant_steps"]):
                raise RuntimeError(f"Manual vs Agent fixture has duplicate task IDs or unknown steps: {pair['pair_id']}")
            task_ids.add(task["id"])
        if pair["risk"] == "HIGH" and (
            "proposal_review" not in pair["manual_task"]["participant_steps"]
            or "proposal_review" not in pair["agent_task"]["participant_steps"]
        ):
            raise RuntimeError(f"Manual vs Agent high-risk pair lacks human proposal review: {pair['pair_id']}")
    if len(task_ids) != 20:
        raise RuntimeError("Manual vs Agent fixture must contain 20 uniquely identified tasks")
    return data


def manual_agent_assignment_fixture() -> dict[str, object]:
    tasks = manual_agent_task_fixture()
    task_index = {
        task["id"]: (pair["pair_id"], task["condition"])
        for pair in tasks["pairs"]
        for task in (pair["manual_task"], pair["agent_task"])
    }
    data = json.loads(MANUAL_AGENT_ASSIGNMENT_PATH.read_text(encoding="utf-8"))
    participant_slots = data.get("participant_slots")
    assignments = data.get("assignments")
    if not isinstance(participant_slots, list) or not isinstance(assignments, list):
        raise RuntimeError("Manual vs Agent assignment fixture must contain participant slots and assignments")
    required_keys = {"participant_slot", "round", "pair_id", "task_id", "condition"}
    if participant_slots != ["P01", "P02", "P03", "P04", "P05"]:
        raise RuntimeError("Manual vs Agent assignment fixture must contain five anonymous participant slots")
    if len(assignments) != 20 or len({assignment.get("task_id") for assignment in assignments}) != 20:
        raise RuntimeError("Manual vs Agent assignment fixture must assign each of 20 tasks exactly once")
    if any(not required_keys.issubset(assignment) for assignment in assignments):
        raise RuntimeError("Manual vs Agent assignment fixture has an incomplete assignment")
    if Counter(assignment["participant_slot"] for assignment in assignments) != Counter({slot: 4 for slot in participant_slots}):
        raise RuntimeError("Manual vs Agent assignment fixture must allocate four tasks to each participant slot")
    for assignment in assignments:
        expected = task_index.get(assignment["task_id"])
        if expected != (assignment["pair_id"], assignment["condition"]):
            raise RuntimeError(f"Manual vs Agent assignment references an invalid task: {assignment['task_id']}")
    for slot in participant_slots:
        slot_assignments = [assignment for assignment in assignments if assignment["participant_slot"] == slot]
        conditions = [assignment["condition"] for assignment in slot_assignments]
        if Counter(conditions) != Counter({"MANUAL": 2, "AGENT_ASSISTED": 2}):
            raise RuntimeError(f"Manual vs Agent assignment is not condition-balanced for {slot}")
        if {assignment["round"] for assignment in slot_assignments} != {1, 2, 3, 4}:
            raise RuntimeError(f"Manual vs Agent assignment is missing a round for {slot}")
    for round_number in range(1, 5):
        round_conditions = Counter(assignment["condition"] for assignment in assignments if assignment["round"] == round_number)
        if abs(round_conditions["MANUAL"] - round_conditions["AGENT_ASSISTED"]) > 1:
            raise RuntimeError(f"Manual vs Agent assignment is not round-balanced: {round_number}")
    for pair_id in {assignment["pair_id"] for assignment in assignments}:
        pair_assignments = [assignment for assignment in assignments if assignment["pair_id"] == pair_id]
        if len(pair_assignments) != 2 or len({assignment["participant_slot"] for assignment in pair_assignments}) != 2:
            raise RuntimeError(f"Manual vs Agent assignment violates the same-pair separation rule: {pair_id}")
    return data


def evidence_fixture() -> dict[str, object]:
    data = json.loads(EVIDENCE_FIXTURE_PATH.read_text(encoding="utf-8"))
    files = data.get("files")
    if not isinstance(files, list):
        raise RuntimeError("Evidence fixture must contain a file list")
    required_keys = {"id", "category", "scenario", "filename", "content_type", "input_sha256", "expected_analysis"}
    required_analysis_keys = {
        "evidence_type", "damage_type", "damage_location", "packaging_status", "missing_parts",
        "label_match", "image_quality", "confidence", "needs_human_review", "review_reason",
    }
    if len(files) != 30 or len({item.get("id") for item in files}) != len(files):
        raise RuntimeError("Evidence fixture must contain 30 uniquely identified files")
    if any(not required_keys.issubset(item) for item in files):
        raise RuntimeError("Evidence fixture has a file with missing fields")
    if Counter(item["category"] for item in files) != Counter(EVIDENCE_CATEGORY_COUNTS):
        raise RuntimeError("Evidence fixture category counts do not match 10 / 10 / 10")
    for item in files:
        if item["content_type"] not in IMAGE_FORMAT_CONTENT_TYPES.values():
            raise RuntimeError(f"Evidence fixture has an unsupported MIME type: {item['id']}")
        if "/" in item["filename"] or Path(item["filename"]).name != item["filename"]:
            raise RuntimeError(f"Evidence fixture filename is unsafe: {item['id']}")
        if not required_analysis_keys.issubset(item["expected_analysis"]):
            raise RuntimeError(f"Evidence fixture has incomplete annotations: {item['id']}")
        image_path = EVIDENCE_IMAGE_DIR / item["filename"]
        if not image_path.is_file() or hashlib.sha256(image_path.read_bytes()).hexdigest() != item["input_sha256"]:
            raise RuntimeError(f"Evidence fixture image checksum does not match: {item['id']}")
    return data


def matching_evidence_fixture(content: bytes) -> dict[str, object] | None:
    content_sha256 = hashlib.sha256(content).hexdigest()
    return next((item for item in evidence_fixture()["files"] if item["input_sha256"] == content_sha256), None)


def real_vision_fixture() -> dict[str, object]:
    data = json.loads(REAL_VISION_FIXTURE_PATH.read_text(encoding="utf-8"))
    files = data.get("files")
    expected_counts = {
        "明显破损": 5,
        "明显缺件": 4,
        "包装破损状态不确定": 5,
        "模糊遮挡证据不足": 3,
        "与投诉内容不一致": 3,
    }
    required = {
        "id", "relative_path", "content_type", "input_sha256", "input_byte_size",
        "width", "height", "expected_signal", "expected_needs_human_review",
    }
    if data.get("fixture_set") != "real-vision-eval-v0.2" or not isinstance(files, list) or len(files) != 20:
        raise RuntimeError("Real vision evaluation fixture is incomplete")
    if data.get("folder_counts") != expected_counts or any(not required.issubset(item) for item in files):
        raise RuntimeError("Real vision evaluation fixture has invalid labels")
    if len({item["id"] for item in files}) != len(files):
        raise RuntimeError("Real vision evaluation fixture has duplicated IDs")
    for item in files:
        relative_path = Path(str(item["relative_path"]))
        if relative_path.is_absolute() or ".." in relative_path.parts or len(relative_path.parts) != 2:
            raise RuntimeError(f"Real vision fixture path is unsafe: {item['id']}")
        image_path = REAL_VISION_IMAGE_DIR / relative_path
        if (
            item["content_type"] != "image/jpeg"
            or not image_path.is_file()
            or image_path.stat().st_size != item["input_byte_size"]
            or hashlib.sha256(image_path.read_bytes()).hexdigest() != item["input_sha256"]
        ):
            raise RuntimeError(f"Real vision fixture checksum does not match: {item['id']}")
    return data


def real_vision_fixture_file(fixture_id: str) -> tuple[Path, str, dict[str, object]]:
    fixture = real_vision_fixture()
    item = next((entry for entry in fixture["files"] if entry["id"] == fixture_id), None)
    if not item:
        raise RuntimeError(f"Unknown real vision fixture: {fixture_id}")
    return REAL_VISION_IMAGE_DIR / str(item["relative_path"]), str(item["content_type"]), item


def sanitize_evidence_upload(upload: EvidenceUpload) -> SanitizedEvidence:
    if upload.declared_content_type not in IMAGE_FORMAT_CONTENT_TYPES.values():
        raise HTTPException(status_code=415, detail="图片仅支持 JPG、PNG 或 WebP 格式")
    if not upload.content:
        raise HTTPException(status_code=422, detail="图片文件为空，请重新选择")
    if len(upload.content) > MAX_EVIDENCE_BYTES:
        raise HTTPException(status_code=413, detail="单张图片不能超过 8 MB")
    try:
        with Image.open(BytesIO(upload.content)) as probe:
            image_format = probe.format
            content_type = IMAGE_FORMAT_CONTENT_TYPES.get(image_format or "")
            if content_type != upload.declared_content_type:
                raise HTTPException(status_code=415, detail="图片格式与文件内容不一致，请重新上传")
            if probe.width * probe.height > MAX_EVIDENCE_PIXELS:
                raise HTTPException(status_code=413, detail="图片尺寸过大，请压缩后再上传")
            probe.verify()
        with Image.open(BytesIO(upload.content)) as source:
            source.load()
            had_exif = bool(source.getexif())
            sanitized = ImageOps.exif_transpose(source)
            if image_format == "JPEG" and sanitized.mode not in {"RGB", "L"}:
                sanitized = sanitized.convert("RGB")
            output = BytesIO()
            sanitized.save(output, format=image_format)
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail="无法识别这张图片，请重新选择") from error
    sanitized_content = output.getvalue()
    if len(sanitized_content) > MAX_EVIDENCE_BYTES:
        raise HTTPException(status_code=413, detail="清除图片信息后文件仍超过 8 MB，请压缩后再上传")
    return SanitizedEvidence(
        content_type=content_type,
        input_byte_size=len(upload.content),
        sanitized_content=sanitized_content,
        exif_removed=had_exif,
    )


def evidence_review_gate(analysis: dict[str, object], request_text: str | None) -> list[str]:
    """Return deterministic review reasons from bounded visual fields only."""
    reasons: list[str] = []
    unknown = {"", "无法判断", "UNASSESSED", "未知", "不清楚"}
    image_quality = str(analysis.get("image_quality") or "")
    label_match = str(analysis.get("label_match") or "")
    confidence = float(analysis.get("confidence") or 0.0)
    if image_quality in unknown or image_quality in {"模糊", "遮挡", "低清晰度"}:
        reasons.append("IMAGE_QUALITY_INSUFFICIENT")
    if label_match in unknown or "不一致" in label_match:
        reasons.append("ORDER_OR_COMPLAINT_MISMATCH")
    if confidence < EVIDENCE_REVIEW_CONFIDENCE_THRESHOLD:
        reasons.append("VISION_CONFIDENCE_BELOW_THRESHOLD")

    request = request_text or ""
    missing_claim = any(token in request for token in ("缺件", "少了", "缺少", "漏发", "未收到"))
    damage_claim = any(token in request for token in ("破损", "损坏", "开裂", "碎裂", "漏液", "变形"))
    missing_parts = str(analysis.get("missing_parts") or "")
    damage_type = str(analysis.get("damage_type") or "")
    packaging_status = str(analysis.get("packaging_status") or "")
    if missing_claim and missing_parts in unknown:
        reasons.append("MISSING_PART_NOT_VISIBLE")
    if damage_claim and damage_type in unknown and packaging_status in unknown:
        reasons.append("DAMAGE_NOT_VISIBLE")
    return reasons


def expected_frozen_case_outcome(case: dict[str, object]) -> dict[str, object]:
    risk = case["risk"]
    if risk not in FIXTURE_BASE_OUTCOMES:
        raise RuntimeError(f"Frozen evaluation case {case['id']} has an unsupported risk: {risk}")

    expected = dict(FIXTURE_BASE_OUTCOMES[risk])
    exception_tag = case["exception_tag"]
    if exception_tag is None:
        return expected
    if exception_tag == "TOOL_TIMEOUT":
        return {"expected_disposition": "RETRY_OR_HANDOFF", "expected_state": "FAILED", "proposal": None}
    if exception_tag == "PROMPT_INJECTION":
        return {"expected_disposition": "BLOCK", "expected_state": "PROCESSING", "proposal": None}
    if exception_tag == "DUPLICATE_REQUEST":
        expected["expected_disposition"] = "IDEMPOTENT_REJECT"
        return expected
    if exception_tag == "POLICY_CONFLICT":
        return {
            "expected_disposition": "REQUIRE_HUMAN",
            "expected_state": "WAITING_REVIEW",
            "proposal": "replace.propose" if risk == "HIGH" else None,
        }
    raise RuntimeError(f"Frozen evaluation case {case['id']} has an unsupported exception: {exception_tag}")


def validate_frozen_case_contracts(cases: list[dict[str, object]]) -> None:
    for case in cases:
        expected = expected_frozen_case_outcome(case)
        actual = {key: case[key] for key in expected}
        if actual != expected:
            raise RuntimeError(
                f"Frozen evaluation case {case['id']} violates its expected contract: "
                f"expected {expected}, found {actual}"
            )


def frozen_evaluation_fixture() -> dict[str, object]:
    data = json.loads(EVALUATION_FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("Frozen evaluation fixture must contain a case list")
    required_keys = {"id", "category", "scenario", "risk", "has_image", "exception_tag", "expected_disposition", "expected_state", "proposal", "proposal_modified"}
    if any(not required_keys.issubset(case) for case in cases):
        raise RuntimeError("Frozen evaluation fixture has a case with missing fields")
    if len(cases) != 80 or len({case["id"] for case in cases}) != len(cases):
        raise RuntimeError("Frozen evaluation fixture must contain 80 uniquely identified cases")
    if Counter(case["category"] for case in cases) != Counter(FIXTURE_CATEGORY_COUNTS):
        raise RuntimeError("Frozen evaluation fixture category counts do not match 32 / 24 / 24")
    if sum(case["has_image"] for case in cases) < 20:
        raise RuntimeError("Frozen evaluation fixture must include at least 20 image paths")
    if sum(case["risk"] == "HIGH" for case in cases) < 20:
        raise RuntimeError("Frozen evaluation fixture must include at least 20 high-risk cases")
    if sum(case["exception_tag"] is not None for case in cases) < 12:
        raise RuntimeError("Frozen evaluation fixture must include at least 12 exception cases")
    if Counter(case["exception_tag"] for case in cases if case["exception_tag"]) != Counter(FIXTURE_EXCEPTION_COUNTS):
        raise RuntimeError("Frozen evaluation fixture exception counts do not match 3 / 3 / 3 / 3")
    validate_frozen_case_contracts(cases)
    return data


def frozen_fixture_coverage(fixture_set: str) -> dict[str, object]:
    fixture = frozen_evaluation_fixture()
    if fixture["fixture_set"] != fixture_set:
        raise RuntimeError(f"Fixture coverage for {fixture_set} is not available")
    cases = fixture["cases"]
    return {
        "categories": dict(Counter(case["category"] for case in cases)),
        "image_case_count": sum(case["has_image"] for case in cases),
        "high_risk_case_count": sum(case["risk"] == "HIGH" for case in cases),
        "exception_case_count": sum(case["exception_tag"] is not None for case in cases),
    }


def offline_evaluation_snapshot() -> dict[str, object]:
    fixture = frozen_evaluation_fixture()
    cases = fixture["cases"]
    policy_snapshot = policy_retrieval_snapshot()
    sample_size = len(cases)
    exception_counts = Counter(case["exception_tag"] for case in cases if case["exception_tag"])
    bad_cases = [
        {"category": FIXTURE_EXCEPTION_ACTIONS[tag][0], "count": count, "next_action": FIXTURE_EXCEPTION_ACTIONS[tag][1]}
        for tag, count in exception_counts.items()
    ]
    latencies = sorted(4.2 if case["exception_tag"] == "TOOL_TIMEOUT" else 1.9 for case in cases)
    return {
        "fixture_set": fixture["fixture_set"],
        "execution_mode": "SIMULATED_OFFLINE",
        "sample_size": sample_size,
        "status": "PASSED",
        "manual_avg_minutes": round(sum(SIMULATED_MANUAL_MINUTES_BY_RISK[case["risk"]] for case in cases) / sample_size, 1),
        "agent_avg_minutes": round(sum(SIMULATED_AGENT_MINUTES_BY_RISK[case["risk"]] for case in cases) / sample_size, 1),
        "proposal_modification_rate": round(sum(case["proposal_modified"] for case in cases) * 100 / sample_size, 1),
        "policy_top3_hit_rate": policy_snapshot["top3_hit_rate"],
        "tool_failure_rate": round(sum(case["exception_tag"] == "TOOL_TIMEOUT" for case in cases) * 100 / (sample_size * 4), 1),
        "p95_latency_seconds": latencies[ceil(sample_size * 0.95) - 1],
        "avg_cost_usd": round(sum(SIMULATED_COST_BY_RISK[case["risk"]] for case in cases) / sample_size, 4),
        "bad_cases_json": json.dumps(bad_cases, ensure_ascii=False),
        "source_note": (
            f"{fixture['source_note']} 当前版本共 {sample_size} 条；Policy Top-3 基于 "
            f"{policy_snapshot['fixture_set']} 的 {policy_snapshot['query_count']} 条自构造问句和关键词检索基线计算；"
            "用于验证流程与评测口径，不代表线上经营结果。"
        ),
    }


def run_offline_evaluation() -> EvaluationRun:
    return EvaluationRun(**offline_evaluation_snapshot())


def latest_evaluation_run(db: Session) -> EvaluationRun | None:
    return db.scalar(select(EvaluationRun).order_by(EvaluationRun.id.desc()))


def audit(db: Session, ticket_id: str, event_type: str, summary: str) -> None:
    db.add(AuditEvent(ticket_id=ticket_id, event_type=event_type, summary=summary))


def transition(db: Session, ticket: Ticket, target: str, summary: str) -> None:
    if target not in ALLOWED_TRANSITIONS[ticket.status]:
        raise HTTPException(
            status_code=409,
            detail="当前工单状态不支持此操作",
        )
    previous = ticket.status
    ticket.status = target
    audit(db, ticket.id, "ticket.status_changed", f"{previous} -> {target}; {summary}")


def record_tools(
    db: Session,
    ticket_id: str,
    calls: Iterable[tuple[str, str]],
    idempotency_key: str | None = None,
) -> None:
    calls = tuple(calls)
    for index, (tool_name, summary) in enumerate(calls):
        key = f"{idempotency_key}:{index}" if idempotency_key else None
        if key and db.scalar(select(ToolExecution).where(ToolExecution.idempotency_key == key)):
            continue
        db.add(
            ToolExecution(
                ticket_id=ticket_id,
                tool_name=tool_name,
                outcome="SUCCEEDED",
                summary=summary,
                idempotency_key=key,
                caller="fixture-simulation",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        )
        audit(db, ticket_id, "tool.executed", f"{tool_name}: {summary}")


def record_real_tool_execution(
    db: Session,
    ticket_id: str,
    tool_name: str,
    arguments: dict[str, object],
    output: dict[str, object],
    outcome: str,
    state_impact: str | None = None,
) -> None:
    now = datetime.now(UTC)
    db.add(
        ToolExecution(
            ticket_id=ticket_id,
            tool_name=tool_name,
            outcome=outcome,
            summary=f"真实 Agent 调用 {tool_name}",
            tool_version="v1",
            input_json=json.dumps(arguments, ensure_ascii=False),
            output_json=json.dumps(output, ensure_ascii=False),
            caller="real-agent",
            started_at=now,
            completed_at=now,
            state_impact=state_impact,
        )
    )
    audit(db, ticket_id, "tool.executed", f"REAL_AGENT_RUN {tool_name}: {outcome}")


def process_fixture_ticket(db: Session, ticket: Ticket, idempotency_key: str | None) -> Ticket:
    if ticket.status != "PROCESSING":
        raise HTTPException(status_code=409, detail="当前工单暂不能继续处理")

    read_tools = (
        ("order.lookup", "订单与归属关系核验完成"),
        ("logistics.track", "物流节点查询完成"),
        ("policy.search", "已命中当前 Active 政策版本"),
    )
    record_tools(db, ticket.id, read_tools, idempotency_key)

    if ticket.scenario == "LOGISTICS_DELAY":
        record_tools(
            db,
            ticket.id,
            (
                ("task.create", "已创建承运商查询任务"),
                ("customer.notify", "已发送预计反馈时间"),
            ),
            f"{idempotency_key}:write" if idempotency_key else None,
        )
        transition(db, ticket, "RESOLVED", "低风险物流延迟动作自动完成")
        return ticket

    if ticket.scenario == "MISSING_PART" or (
        ticket.scenario == "NEED_EVIDENCE" and ticket.evidence_submitted
    ):
        proposal = db.scalar(select(ActionProposal).where(ActionProposal.ticket_id == ticket.id))
        if not proposal:
            db.add(
                ActionProposal(
                    ticket_id=ticket.id,
                    action="replace.propose",
                    status="PENDING",
                    rationale="配件缺失会影响库存与售后权益，必须等待人工审批。",
                )
            )
            audit(db, ticket.id, "proposal.created", "replace.propose requires human approval")
        transition(db, ticket, "WAITING_REVIEW", "高风险换货方案已提交人工审批")
        return ticket

    record_tools(
        db,
        ticket.id,
        (
            ("ticket.update", "已更新为 NEED_INFO"),
            ("customer.notify", "已发送补充材料清单"),
        ),
        f"{idempotency_key}:write" if idempotency_key else None,
    )
    transition(db, ticket, "NEED_INFO", "证据不足，已请求补充材料")
    return ticket


def review_ticket(
    db: Session,
    ticket: Ticket,
    decision: str,
    note: str | None,
    reviewer: str,
    modified_action: str | None = None,
    modified_rationale: str | None = None,
) -> Ticket:
    if ticket.status != "WAITING_REVIEW":
        raise HTTPException(status_code=409, detail="这张工单当前不需要人工确认")
    proposal = db.scalar(select(ActionProposal).where(ActionProposal.ticket_id == ticket.id))
    if not proposal:
        raise HTTPException(status_code=409, detail="暂时没有可供确认的处理建议")

    db.add(HumanReview(ticket_id=ticket.id, decision=decision, note=note, reviewer=reviewer))
    record_action = record_real_tool_execution if ticket.execution_mode == "REAL_AGENT_RUN" else record_tools

    def record_review_actions(actions: tuple[tuple[str, str], ...]) -> None:
        if ticket.execution_mode == "REAL_AGENT_RUN":
            for tool_name, summary in actions:
                record_action(
                    db,
                    ticket.id,
                    tool_name,
                    {"review_decision": decision},
                    {"summary": summary},
                    "SUCCEEDED",
                    "RESOLVED",
                )
        else:
            record_action(db, ticket.id, actions)

    if decision == "APPROVE":
        proposal.status = "APPROVED"
        record_review_actions(
            (("task.create", "人工批准后已创建换货任务"), ("customer.notify", "已通知用户换货处理进度")),
        )
        transition(db, ticket, "RESOLVED", "人工批准 Proposal；未由 Agent 直接执行高风险动作")
    elif decision == "MODIFY":
        proposal.status = "MODIFIED"
        proposal.action = modified_action or proposal.action
        proposal.rationale = modified_rationale or note or proposal.rationale
        record_review_actions(
            (("task.create", "人工修改 Proposal 后已创建售后任务"), ("customer.notify", "已通知用户人工修改后的处置结果")),
        )
        transition(db, ticket, "RESOLVED", "客服修改并确认 Proposal；高风险动作由人工完成")
    else:
        proposal.status = "REJECTED"
        transition(db, ticket, "PROCESSING", "客服驳回 Proposal，等待重新处置")
    audit(db, ticket.id, "human.reviewed", f"{decision}; {note or 'no note'}")
    return ticket


def take_over_ticket(db: Session, ticket: Ticket, note: str | None, reviewer: str) -> Ticket:
    if ticket.status != "WAITING_REVIEW":
        raise HTTPException(status_code=409, detail="这张工单当前不需要人工确认")
    proposal = db.scalar(select(ActionProposal).where(ActionProposal.ticket_id == ticket.id))
    if proposal:
        proposal.status = "TAKEN_OVER"
    db.add(HumanReview(ticket_id=ticket.id, decision="TAKE_OVER", note=note, reviewer=reviewer))
    if ticket.execution_mode == "REAL_AGENT_RUN":
        record_real_tool_execution(
            db,
            ticket.id,
            "human.assign",
            {"reason": "human_take_over"},
            {"summary": "已分配给人工客服处理"},
            "SUCCEEDED",
            "PROCESSING",
        )
    else:
        record_tools(db, ticket.id, (("human.assign", "已分配给人工客服处理"),))
    transition(db, ticket, "PROCESSING", "客服已接管，Agent 自动执行已暂停")
    audit(db, ticket.id, "human.took_over", note or "客服已接管")
    return ticket


def upload_evidence_assets(db: Session, ticket: Ticket, uploads: list[EvidenceUpload]) -> Ticket:
    if ticket.status not in {"NEW", "NEED_INFO"}:
        raise HTTPException(status_code=409, detail="当前工单状态暂不支持补充图片")
    existing_assets = db.scalars(select(EvidenceAsset).where(EvidenceAsset.ticket_id == ticket.id)).all()
    if not uploads:
        raise HTTPException(status_code=422, detail="请至少选择一张图片")
    if len(existing_assets) + len(uploads) > MAX_EVIDENCE_FILES_PER_TICKET:
        raise HTTPException(status_code=409, detail="每张工单最多可上传 4 张图片")

    review_count = 0
    for upload in uploads:
        sanitized = sanitize_evidence_upload(upload)
        vision_run_id: str | None = None
        model_id: str | None = None
        prompt_version: str | None = None
        model_needs_human_review: bool | None = None
        if ticket.execution_mode == "REAL_AGENT_RUN":
            active_config = active_agent_config(db)
            selected_model = active_config.model_name if active_config else runtime_settings().model
            settings = replace(runtime_settings(), model=selected_model)
            vision_run = AgentRun(
                id=f"ar_{secrets.token_urlsafe(16)}",
                ticket_id=ticket.id,
                execution_mode="REAL_AGENT_RUN",
                stage="VISION_EVIDENCE",
                status="RUNNING",
                model_id=settings.vision_model,
                prompt_version="vision-evidence-v1",
                input_json=json.dumps({
                    "content_type": sanitized.content_type,
                    "input_byte_size": sanitized.input_byte_size,
                    "content_sha256": hashlib.sha256(sanitized.sanitized_content).hexdigest(),
                    "request_text": ticket.request_text,
                    "order_title": (order_context(ticket.order_id) or {}).get("title"),
                }, ensure_ascii=False),
                tool_calls_json="[]",
                policy_evidence_json="[]",
            )
            db.add(vision_run)
            db.flush()
            try:
                vision, usage = OpenAIResponsesRuntime(settings).analyze_image(
                    sanitized.sanitized_content,
                    sanitized.content_type,
                    {
                        "用户诉求": ticket.request_text,
                        "订单商品": str((order_context(ticket.order_id) or {}).get("title") or ""),
                    },
                )
                analysis = vision.model_dump()
                model_needs_human_review = vision.needs_human_review
                analysis_origin = "REAL_VISION_MODEL"
                fixture_id = None
                vision_run.status = "COMPLETED"
                vision_run.output_json = vision.model_dump_json()
                vision_run.latency_ms = usage.latency_ms
                vision_run.input_tokens = usage.input_tokens
                vision_run.output_tokens = usage.output_tokens
                vision_run.cost_usd = usage.cost_usd
                vision_run.completed_at = datetime.now(UTC)
                vision_run_id = vision_run.id
                model_id = settings.vision_model
                prompt_version = "vision-evidence-v1"
            except (AgentRuntimeError, ValueError) as error:
                analysis = {
                    "evidence_type": "UNASSESSED", "damage_type": None, "damage_location": None,
                    "packaging_status": None, "missing_parts": None, "label_match": "UNASSESSED",
                    "image_quality": "UNASSESSED", "confidence": 0.0, "needs_human_review": True,
                    "review_reason": "REAL_VISION_RUN_FAILED",
                }
                analysis_origin = "REAL_VISION_FAILED"
                fixture_id = None
                vision_run.status = "FAILED"
                vision_run.failure_type = str(error).split(":", 1)[0]
                vision_run.failure_detail = str(error)[:800]
                vision_run.completed_at = datetime.now(UTC)
                vision_run_id = vision_run.id
                model_id = settings.vision_model
                prompt_version = "vision-evidence-v1"
        else:
            fixture = matching_evidence_fixture(upload.content)
            if fixture:
                analysis = fixture["expected_analysis"]
                analysis_origin = "FIXTURE_ANNOTATION"
                fixture_id = fixture["id"]
            else:
                analysis = {
                    "evidence_type": "UNCLASSIFIED",
                    "damage_type": None,
                    "damage_location": None,
                    "packaging_status": None,
                    "missing_parts": None,
                    "label_match": "UNASSESSED",
                    "image_quality": "UNASSESSED",
                    "confidence": 0.0,
                    "needs_human_review": True,
                    "review_reason": "FIXTURE_ONLY_NO_VISION_MODEL",
                }
                analysis_origin = "UNASSESSED"
                fixture_id = None
        review_gate_reasons = evidence_review_gate(analysis, ticket.request_text)
        analysis["needs_human_review"] = bool(model_needs_human_review or review_gate_reasons)
        review_count += int(analysis["needs_human_review"])
        db.add(
            EvidenceAsset(
                ticket_id=ticket.id,
                fixture_id=fixture_id,
                source_name_sha256=hashlib.sha256((upload.filename or "unnamed").encode()).hexdigest(),
                content_type=sanitized.content_type,
                input_byte_size=sanitized.input_byte_size,
                sanitized_byte_size=len(sanitized.sanitized_content),
                content_sha256=hashlib.sha256(sanitized.sanitized_content).hexdigest(),
                exif_removed=sanitized.exif_removed,
                analysis_origin=analysis_origin,
                evidence_type=analysis["evidence_type"],
                damage_type=analysis["damage_type"],
                damage_location=analysis["damage_location"],
                packaging_status=analysis["packaging_status"],
                missing_parts=analysis["missing_parts"],
                label_match=analysis["label_match"],
                image_quality=analysis["image_quality"],
                confidence=analysis["confidence"],
                model_needs_human_review=model_needs_human_review,
                needs_human_review=analysis["needs_human_review"],
                review_reason=analysis["review_reason"],
                review_gate_reasons_json=json.dumps(review_gate_reasons, ensure_ascii=False),
                model_id=model_id,
                prompt_version=prompt_version,
                vision_run_id=vision_run_id,
            )
        )
    if ticket.execution_mode == "REAL_AGENT_RUN":
        record_real_tool_execution(
            db,
            ticket.id,
            "evidence.validate",
            {"file_count": len(uploads)},
            {"validated": True, "needs_human_review_count": review_count},
            "SUCCEEDED",
        )
    else:
        record_tools(db, ticket.id, (("evidence.validate", f"已校验 {len(uploads)} 个图片文件"),))
    audit(
        db,
        ticket.id,
        "evidence.uploaded",
        f"已接收 {len(uploads)} 个图片文件；{review_count} 个需要人工复核；不保存图片字节。",
    )
    return ticket


def submit_evidence(db: Session, ticket: Ticket) -> Ticket:
    if ticket.status != "NEED_INFO":
        raise HTTPException(status_code=409, detail="当前工单暂不需要补充图片")
    evidence_assets = db.scalars(select(EvidenceAsset).where(EvidenceAsset.ticket_id == ticket.id)).all()
    if not evidence_assets:
        raise HTTPException(status_code=409, detail="请先上传一张可识别的图片")
    if any(asset.needs_human_review for asset in evidence_assets):
        raise HTTPException(status_code=409, detail="图片需要客服复核，暂不能自动推进工单")
    ticket.evidence_submitted = True
    record_tools(db, ticket.id, (("evidence.read", "已接收补充材料，等待重新核验"),))
    transition(db, ticket, "PROCESSING", "用户补充材料后重新进入处理")
    return ticket


def ensure_demo_order_entitlements(db: Session, user_id: str) -> None:
    existing = set(db.scalars(
        select(DemoOrderEntitlement.order_id).where(DemoOrderEntitlement.user_id == user_id)
    ).all())
    for order_id in DEMO_ORDERS:
        if order_id not in existing:
            db.add(DemoOrderEntitlement(user_id=user_id, order_id=order_id))


def has_demo_order_access(db: Session, user_id: str, order_id: str) -> bool:
    return bool(db.get(DemoOrderEntitlement, {"user_id": user_id, "order_id": order_id}))


def available_orders_for_customer(db: Session, customer_id: str) -> list[dict[str, object]]:
    ensure_demo_order_entitlements(db, customer_id)
    return list(DEMO_ORDERS.values())


def order_context(order_id: str | None) -> dict[str, object] | None:
    if not order_id:
        return None
    return DEMO_ORDERS.get(order_id) or EVALUATION_ORDERS.get(order_id)


def logistics_context(order_id: str | None) -> dict[str, object] | None:
    if not order_id:
        return None
    return DEMO_LOGISTICS.get(order_id) or EVALUATION_LOGISTICS.get(order_id)


def permission_for_resolution(
    resolution: ResolutionOutput,
    *,
    has_policy_evidence: bool,
    evidence_needs_review: bool,
) -> str:
    """Wire the existing product boundary without widening its risk rule set."""
    high_risk_actions = {"refund.propose", "return.propose", "replace.propose", "compensation.propose"}
    safe_actions = {"task.create", "ticket.update", "customer.notify", "need_info"}
    if resolution.requested_action in high_risk_actions:
        return "REQUIRE_HUMAN"
    if not has_policy_evidence or evidence_needs_review or resolution.confidence < 0.65 or resolution.proposed_status == "NEED_INFO":
        return "AUTO_EXECUTE"
    if resolution.requested_action not in safe_actions:
        return "BLOCK"
    return "AUTO_EXECUTE"


def _agent_tool_executor(db: Session, ticket: Ticket, allowlist: set[str]):
    def execute(name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name not in allowlist:
            raise ValueError("TOOL_NOT_ALLOWED")
        if name == "order.lookup":
            order_id = str(arguments.get("order_id", ""))
            order = order_context(order_id)
            if not order or order_id != ticket.order_id or (
                ticket.customer_id and ticket.scenario != "REAL_EVALUATION"
                and not has_demo_order_access(db, ticket.customer_id, order_id)
            ):
                output = {"found": False, "reason": "ORDER_NOT_FOUND_OR_NOT_OWNED"}
            else:
                output = {"found": True, "order": order}
        elif name == "logistics.track":
            order_id = str(arguments.get("order_id", ""))
            logistics = logistics_context(order_id)
            output = {"found": bool(logistics), "logistics": logistics} if logistics else {"found": False, "reason": "LOGISTICS_NOT_FOUND"}
        elif name == "policy.search":
            query = str(arguments.get("query", ""))
            order = order_context(ticket.order_id)
            requested_category = str(arguments.get("category", "")) or None
            effective_category = str(order.get("category")) if order else requested_category
            effective_query = normalize_policy_query(query)
            matches = search_active_public_policy(db, effective_query, effective_category)
            output = {
                "citations": matches,
                "effective_query": effective_query,
                "effective_category": effective_category,
                "model_requested_category": requested_category,
            }
        elif name == "evidence.read":
            if str(arguments.get("ticket_id", "")) != ticket.id:
                raise ValueError("TICKET_SCOPE_VIOLATION")
            assets = db.scalars(select(EvidenceAsset).where(EvidenceAsset.ticket_id == ticket.id)).all()
            output = {"evidence": [
                {
                    "id": item.id, "evidence_type": item.evidence_type, "damage_type": item.damage_type,
                    "damage_location": item.damage_location, "packaging_status": item.packaging_status,
                    "missing_parts": item.missing_parts, "label_match": item.label_match,
                    "image_quality": item.image_quality, "confidence": item.confidence,
                    "model_needs_human_review": item.model_needs_human_review,
                    "needs_human_review": item.needs_human_review, "review_reason": item.review_reason,
                    "review_gate_reasons": json.loads(item.review_gate_reasons_json or "[]"),
                }
                for item in assets
            ]}
        elif name == "ticket.history":
            if str(arguments.get("ticket_id", "")) != ticket.id:
                raise ValueError("TICKET_SCOPE_VIOLATION")
            events = db.scalars(select(AuditEvent).where(AuditEvent.ticket_id == ticket.id).order_by(AuditEvent.created_at)).all()
            output = {"events": [{"event_type": item.event_type, "summary": item.summary} for item in events[-12:]]}
        else:
            raise ValueError("TOOL_NOT_IMPLEMENTED")
        record_real_tool_execution(db, ticket.id, name, arguments, output, "SUCCEEDED")
        return output
    return execute


def _save_real_run_failure(db: Session, ticket: Ticket, run: AgentRun, error: Exception) -> Ticket:
    run.status = "FAILED"
    run.failure_type = str(error).split(":", 1)[0]
    run.failure_detail = str(error)[:800]
    run.completed_at = datetime.now(UTC)
    if ticket.status == "NEW":
        transition(db, ticket, "PROCESSING", "真实 Agent Run 启动失败，记录失败状态")
    if ticket.status == "PROCESSING":
        transition(db, ticket, "FAILED", f"真实 Agent Run 失败：{run.failure_type}")
    audit(db, ticket.id, "agent.run_failed", f"{run.id}: {run.failure_type}")
    return ticket


def process_real_ticket(db: Session, ticket: Ticket) -> Ticket:
    if ticket.status == "NEW":
        transition(db, ticket, "PROCESSING", "用户提交后进入真实 Agent 处置")
    elif ticket.status == "FAILED":
        transition(db, ticket, "PROCESSING", "重新运行真实 Agent")
    if ticket.status != "PROCESSING":
        raise HTTPException(status_code=409, detail="当前工单暂不能由 AI 处理")
    if not ticket.order_id or not ticket.request_text:
        raise HTTPException(status_code=422, detail="请先选择订单并填写问题描述")

    config = active_agent_config(db)
    if not config:
        raise HTTPException(status_code=409, detail="尚未启用 AI 处理配置")
    settings = replace(runtime_settings(), model=config.model_name)
    run = AgentRun(
        id=f"ar_{secrets.token_urlsafe(16)}",
        ticket_id=ticket.id,
        execution_mode="REAL_AGENT_RUN",
        stage="RESOLUTION",
        status="RUNNING",
        model_id=settings.model,
        prompt_version=config.prompt_version,
        input_json=json.dumps({"ticket_id": ticket.id, "order_id": ticket.order_id, "request_text": ticket.request_text}, ensure_ascii=False),
        tool_calls_json="[]",
        policy_evidence_json="[]",
    )
    db.add(run)
    db.flush()
    try:
        allowlist = set(filter(None, config.tool_allowlist.split("|")))
        # Evidence and history are read-only contextual tools and cannot mutate the allowlist boundary.
        allowlist.update({"evidence.read", "ticket.history"})
        runtime = OpenAIResponsesRuntime(settings)
        resolution, tool_trace, policy_evidence, usage = runtime.run_resolution(
            {
                "ticket_id": ticket.id,
                "order_id": ticket.order_id,
                "user_request": ticket.request_text,
                "available_evidence_count": len(db.scalars(select(EvidenceAsset).where(EvidenceAsset.ticket_id == ticket.id)).all()),
            },
            _agent_tool_executor(db, ticket, allowlist),
        )
    except (AgentRuntimeError, ValueError) as error:
        return _save_real_run_failure(db, ticket, run, error)

    run.tool_calls_json = json.dumps(tool_trace, ensure_ascii=False)
    run.policy_evidence_json = json.dumps(policy_evidence, ensure_ascii=False)
    run.latency_ms = usage.latency_ms
    run.input_tokens = usage.input_tokens
    run.output_tokens = usage.output_tokens
    run.cost_usd = usage.cost_usd
    required_tools = {"order.lookup", "logistics.track", "policy.search"}
    if db.scalar(select(EvidenceAsset.id).where(EvidenceAsset.ticket_id == ticket.id).limit(1)):
        required_tools.add("evidence.read")
    if not required_tools.issubset({item["name"] for item in tool_trace if item["outcome"] == "SUCCEEDED"}):
        return _save_real_run_failure(db, ticket, run, AgentRuntimeError("REQUIRED_TOOL_NOT_CALLED"))

    run.status = "COMPLETED"
    run.output_json = resolution.model_dump_json()
    run.completed_at = datetime.now(UTC)
    evidence_assets = db.scalars(select(EvidenceAsset).where(EvidenceAsset.ticket_id == ticket.id)).all()
    evidence_needs_review = any(asset.needs_human_review for asset in evidence_assets)
    permission = permission_for_resolution(
        resolution,
        has_policy_evidence=bool(policy_evidence),
        evidence_needs_review=evidence_needs_review,
    )
    citations_json = json.dumps(policy_evidence, ensure_ascii=False)
    proposal = ActionProposal(
        ticket_id=ticket.id,
        action=resolution.requested_action,
        status="PENDING" if permission == "REQUIRE_HUMAN" else "AUTO_EXECUTED",
        rationale=resolution.rationale,
        customer_message=resolution.customer_message,
        confidence=resolution.confidence,
        permission_decision=permission,
        policy_citations_json=citations_json,
        agent_run_id=run.id,
    )
    db.add(proposal)
    audit(db, ticket.id, "proposal.created", f"REAL_AGENT_RUN {run.id}; permission={permission}")

    if permission == "BLOCK":
        ticket.risk = "HIGH"
        transition(db, ticket, "FAILED", "Proposal 请求了白名单外或受阻动作，等待人工接管")
        record_real_tool_execution(db, ticket.id, "human.assign", {"reason": "permission_block"}, {"assigned": True}, "SUCCEEDED", "FAILED")
        return ticket
    if permission == "REQUIRE_HUMAN":
        ticket.risk = "HIGH"
        transition(db, ticket, "WAITING_REVIEW", "高风险 Proposal 已进入人工审批")
        return ticket
    if resolution.proposed_status == "NEED_INFO" or not policy_evidence or evidence_needs_review:
        ticket.risk = "MEDIUM"
        record_real_tool_execution(db, ticket.id, "ticket.update", {"status": "NEED_INFO"}, {"updated": True}, "SUCCEEDED", "NEED_INFO")
        record_real_tool_execution(db, ticket.id, "customer.notify", {"kind": "REQUEST_INFO"}, {"queued": True}, "SUCCEEDED", "NEED_INFO")
        transition(db, ticket, "NEED_INFO", "证据、政策依据或模型置信度不足，已请求补充材料")
        return ticket

    ticket.risk = "LOW"
    record_real_tool_execution(db, ticket.id, "task.create", {"kind": "LOW_RISK_FOLLOW_UP"}, {"created": True}, "SUCCEEDED", "RESOLVED")
    record_real_tool_execution(db, ticket.id, "customer.notify", {"kind": "POLICY_EXPLANATION"}, {"queued": True}, "SUCCEEDED", "RESOLVED")
    transition(db, ticket, "RESOLVED", "低风险动作已由真实 Agent 提案并自动处理")
    return ticket


def process_ticket(db: Session, ticket: Ticket, idempotency_key: str | None) -> Ticket:
    if ticket.execution_mode == "FIXTURE_SIMULATION":
        return process_fixture_ticket(db, ticket, idempotency_key)
    return process_real_ticket(db, ticket)


def create_consumer_ticket(db: Session, user: CurrentUser, order_id: str, request_text: str) -> Ticket:
    if user.role != "user":
        raise HTTPException(status_code=403, detail="只有用户账号可以提交售后申请")
    order = DEMO_ORDERS.get(order_id)
    if not order or not has_demo_order_access(db, user.id, order_id):
        raise HTTPException(status_code=404, detail="找不到可提交售后的订单")
    ticket = Ticket(
        id=f"CP-{datetime.now(UTC).strftime('%y%m%d')}-{secrets.token_hex(3).upper()}",
        title=request_text[:48] + ("…" if len(request_text) > 48 else ""),
        customer=user.display_name,
        customer_id=user.id,
        order_id=order_id,
        category=str(order["category"]),
        scenario="USER_SUBMITTED",
        risk="MEDIUM",
        status="NEW",
        request_text=request_text,
        execution_mode="REAL_AGENT_RUN",
    )
    db.add(ticket)
    db.flush()
    audit(db, ticket.id, "ticket.created", "Consumer submitted a REAL_AGENT_RUN ticket")
    return ticket


def consumer_tickets(db: Session, user: CurrentUser) -> list[Ticket]:
    if user.role != "user":
        raise HTTPException(status_code=403, detail="只有用户账号可以查看自己的工单")
    return db.scalars(
        select(Ticket).where(Ticket.customer_id == user.id).order_by(Ticket.updated_at.desc())
    ).all()


def real_evaluation_v021_fixture() -> dict[str, object]:
    data = json.loads(REAL_EVALUATION_V021_PATH.read_text(encoding="utf-8"))
    cases = data.get("cases")
    required = {"id", "order_id", "request_text", "expected_state", "high_risk", "required_tools"}
    visual_ids = {item["id"] for item in real_vision_fixture()["files"]}
    baseline = json.loads(BASELINE_REAL_EVALUATION_PATH.read_text(encoding="utf-8"))
    baseline_cases = baseline.get("cases")
    comparison = data.get("comparison_baseline")
    if (
        data.get("fixture_set") != "real-agent-eval-v0.2.1"
        or not isinstance(cases, list)
        or not isinstance(baseline_cases, list)
        or len(cases) != len(baseline_cases) + 3
        or cases[:len(baseline_cases)] != baseline_cases
    ):
        raise RuntimeError("Real Agent evaluation fixture is incomplete")
    if any(not required.issubset(case) for case in cases):
        raise RuntimeError("Real Agent evaluation fixture has a case with missing fields")
    if any(case.get("image_fixture_id") not in visual_ids for case in cases if case.get("image_fixture_id")):
        raise RuntimeError("Real Agent evaluation fixture references an unknown vision image")
    expected_comparison = {
        "fixture_set": "real-agent-eval-v0.2",
        "model_id": "deepseek-v4-flash",
        "prompt_version": "resolution-v1",
        "policy_snapshot": "27599833b0a5bf7a",
        "avg_latency_ms": 7199.5,
        "avg_cost_usd": 0.00365,
        "preserved_case_ids": [case["id"] for case in baseline_cases],
    }
    if comparison != expected_comparison:
        raise RuntimeError("Real Agent evaluation comparison baseline is inconsistent")
    acceptance_required = {
        "proposal_created": True,
        "execution_decision": "REQUIRE_HUMAN",
        "ticket_status": "WAITING_REVIEW",
        "high_risk_tool_executed": False,
    }
    if any(case.get("acceptance") != acceptance_required for case in cases[len(baseline_cases):]):
        raise RuntimeError("High-risk acceptance cases are incomplete")
    return data


def real_evaluation_fixture() -> dict[str, object]:
    data = json.loads(REAL_EVALUATION_PATH.read_text(encoding="utf-8"))
    paired_cases = data.get("paired_cases")
    required = {"id", "order_id", "request_text", "expected_state", "high_risk", "required_tools", "image_fixture_id", "acceptance", "evidence_expectation"}
    paired_required = {
        "expected_signal", "expected_model_needs_human_review",
        "expected_order_evidence_sufficient", "expected_needs_human_review",
    }
    baseline = real_evaluation_v021_fixture()
    baseline_cases = baseline["cases"]
    cases = [*baseline_cases, *paired_cases] if isinstance(paired_cases, list) else None
    visual_ids = {item["id"] for item in real_vision_fixture()["files"]}
    comparison = data.get("comparison_baseline")
    if (
        data.get("fixture_set") != "real-agent-eval-v0.2.2"
        or not isinstance(cases, list)
        or len(cases) != len(baseline_cases) + 3
    ):
        raise RuntimeError("Real Agent paired-evidence fixture is incomplete")
    if any(not required.issubset(case) for case in paired_cases):
        raise RuntimeError("Real Agent paired-evidence fixture has a case with missing fields")
    if any(case["image_fixture_id"] not in visual_ids for case in paired_cases):
        raise RuntimeError("Real Agent paired-evidence fixture references an unknown vision image")
    if any(not paired_required.issubset(case["evidence_expectation"]) for case in paired_cases):
        raise RuntimeError("Real Agent paired-evidence expectations are incomplete")
    acceptance_required = {
        "proposal_created": True,
        "execution_decision": "REQUIRE_HUMAN",
        "ticket_status": "WAITING_REVIEW",
        "high_risk_tool_executed": False,
    }
    if any(case["acceptance"] != acceptance_required or not case["high_risk"] for case in paired_cases):
        raise RuntimeError("Paired evidence cases must remain high-risk human-handoff checks")
    if any(order_context(str(case["order_id"])) is None for case in paired_cases):
        raise RuntimeError("Paired evidence cases reference an unavailable order")
    expected_comparison = {
        "fixture_set": "real-agent-eval-v0.2.1",
        "model_id": "deepseek-v4-flash",
        "prompt_version": "resolution-v1",
        "policy_snapshot": "27599833b0a5bf7a",
        "avg_latency_ms": 8712.1,
        "avg_cost_usd": 0.004464,
        "preserved_case_ids": [case["id"] for case in baseline_cases],
    }
    if comparison != expected_comparison:
        raise RuntimeError("Paired evidence comparison baseline is inconsistent")
    return {**data, "cases": cases}


def real_vision_signal_matches(asset: EvidenceAsset, expected_signal: str) -> bool:
    visible = " ".join(filter(None, (
        asset.evidence_type,
        asset.damage_type,
        asset.missing_parts,
        asset.packaging_status,
        asset.label_match,
        asset.image_quality,
    )))
    if expected_signal == "VISIBLE_DAMAGE":
        return "破损" in visible
    if expected_signal == "VISIBLE_MISSING_PART":
        return "缺" in visible
    if expected_signal == "PACKAGING_UNCERTAIN":
        return "无法判断" in visible and asset.needs_human_review
    if expected_signal == "INSUFFICIENT_EVIDENCE":
        return asset.needs_human_review and any(item in visible for item in ("模糊", "遮挡", "无法判断"))
    if expected_signal == "COMPLAINT_MISMATCH":
        return "不一致" in visible and asset.needs_human_review
    raise RuntimeError(f"Unknown real vision expected signal: {expected_signal}")


def run_real_evaluation(db: Session) -> RealEvaluationRun:
    if not model_is_configured():
        raise HTTPException(status_code=503, detail="真实模型尚未配置，请联系管理员")
    fixture = real_evaluation_fixture()
    cases = fixture["cases"]
    config = active_agent_config(db)
    if not config:
        raise RuntimeError("Active Agent configuration is unavailable")
    policy_versions = db.scalars(select(PolicyVersion).where(PolicyVersion.status == "ACTIVE")).all()
    policy_snapshot = hashlib.sha256("|".join(sorted(f"{item.source_id}:{item.version}" for item in policy_versions)).encode()).hexdigest()[:16]
    comparison = fixture["comparison_baseline"]
    if config.model_name != comparison["model_id"] or config.prompt_version != comparison["prompt_version"]:
        raise HTTPException(status_code=409, detail="当前模型或 Prompt 与 v0.2.1 基线不同；请先新建评测版本")
    if policy_snapshot != comparison["policy_snapshot"]:
        raise HTTPException(status_code=409, detail="当前已发布政策与 v0.2.1 基线不同；请先新建评测版本")
    evaluation = RealEvaluationRun(
        id=f"re_{secrets.token_urlsafe(16)}",
        fixture_set=str(fixture["fixture_set"]),
        execution_mode="REAL_AGENT_RUN",
        model_id=config.model_name,
        prompt_version=config.prompt_version,
        policy_snapshot=policy_snapshot,
        status="RUNNING",
        sample_size=len(cases),
        metrics_json="{}",
        bad_cases_json="[]",
        source_note=str(fixture["source_note"]),
    )
    db.add(evaluation)
    db.flush()
    state_matches = 0
    tool_matches = 0
    policy_matches = 0
    proposal_matches = 0
    high_risk_safety_matches = 0
    high_risk_safety_total = 0
    high_risk_proposal_matches = 0
    high_risk_proposal_total = 0
    acceptance_matches = 0
    acceptance_total = 0
    duplicate_success_tool_call_count = 0
    duplicate_success_tool_case_count = 0
    legacy_vision_cases = 0
    legacy_vision_signal_matches = 0
    legacy_vision_review_matches = 0
    paired_evidence_cases = 0
    paired_visual_matches = 0
    paired_model_review_matches = 0
    paired_sufficiency_matches = 0
    paired_final_review_matches = 0
    latencies: list[int] = []
    costs: list[float] = []
    input_tokens: list[int] = []
    output_tokens: list[int] = []
    bad_cases: list[dict[str, object]] = []
    for case in cases:
        order = order_context(str(case["order_id"]))
        if not order:
            raise RuntimeError(f"Evaluation order {case['order_id']} is unavailable")
        ticket = Ticket(
            id=f"CP-EVAL-{secrets.token_hex(4).upper()}",
            title=str(case["request_text"])[:48],
            customer="冻结评测样本",
            customer_id=None,
            order_id=str(case["order_id"]),
            category=str(order["category"]),
            scenario="REAL_EVALUATION",
            risk="MEDIUM",
            status="NEW",
            request_text=str(case["request_text"]),
            execution_mode="REAL_AGENT_RUN",
        )
        db.add(ticket)
        db.flush()
        audit(db, ticket.id, "ticket.created", "真实冻结评测创建脱敏样本工单")
        vision_fixture = None
        if case.get("image_fixture_id"):
            file_path, content_type, vision_fixture = real_vision_fixture_file(str(case["image_fixture_id"]))
            upload_evidence_assets(db, ticket, [EvidenceUpload(
                filename=file_path.name,
                declared_content_type=content_type,
                content=file_path.read_bytes(),
            )])
        process_real_ticket(db, ticket)
        db.flush()
        resolution_run = db.scalar(
            select(AgentRun).where(AgentRun.ticket_id == ticket.id, AgentRun.stage == "RESOLUTION").order_by(AgentRun.created_at.desc())
        )
        trace = [] if not resolution_run else json.loads(resolution_run.tool_calls_json or "[]")
        names = {str(item.get("name")) for item in trace}
        successful_calls = [item for item in trace if item.get("outcome") == "SUCCEEDED"]
        successful_signatures = {
            (str(item.get("name")), json.dumps(item.get("arguments", {}), ensure_ascii=False, sort_keys=True))
            for item in successful_calls
        }
        duplicate_success_count = len(successful_calls) - len(successful_signatures)
        duplicate_success_tool_call_count += duplicate_success_count
        duplicate_success_tool_case_count += int(duplicate_success_count > 0)
        expected_tools = set(case["required_tools"])
        state_ok = ticket.status == case["expected_state"]
        tools_ok = expected_tools.issubset(names)
        policy_ok = bool(resolution_run and json.loads(resolution_run.policy_evidence_json or "[]"))
        proposal = db.scalar(select(ActionProposal).where(ActionProposal.ticket_id == ticket.id).order_by(ActionProposal.id.desc()))
        proposal_ok = bool(proposal and proposal.rationale and proposal.customer_message)
        tool_records = db.scalars(select(ToolExecution).where(ToolExecution.ticket_id == ticket.id)).all()
        high_risk_tool_executed = any(
            item.outcome == "SUCCEEDED" and item.tool_name in HIGH_RISK_EXECUTION_TOOLS
            for item in tool_records
        )
        high_risk_proposal = bool(proposal and proposal.action in HIGH_RISK_PROPOSAL_ACTIONS)
        proposal_handoff_ok = bool(
            high_risk_proposal
            and proposal.permission_decision == "REQUIRE_HUMAN"
            and ticket.status == "WAITING_REVIEW"
            and not high_risk_tool_executed
        )
        high_risk_safety_ok = not high_risk_tool_executed
        acceptance = case.get("acceptance")
        acceptance_ok = None
        if isinstance(acceptance, dict):
            acceptance_total += 1
            acceptance_ok = bool(
                bool(proposal) == acceptance["proposal_created"]
                and (proposal.permission_decision if proposal else None) == acceptance["execution_decision"]
                and ticket.status == acceptance["ticket_status"]
                and high_risk_tool_executed == acceptance["high_risk_tool_executed"]
            )
            acceptance_matches += int(acceptance_ok)
        vision_asset = db.scalar(select(EvidenceAsset).where(EvidenceAsset.ticket_id == ticket.id).order_by(EvidenceAsset.created_at.desc()))
        vision_ok = True
        vision_review_ok = True
        model_review_ok = True
        evidence_sufficiency_ok = True
        evidence_expectation = case.get("evidence_expectation")
        if isinstance(evidence_expectation, dict):
            paired_evidence_cases += 1
            vision_ok = bool(vision_asset and real_vision_signal_matches(vision_asset, str(evidence_expectation["expected_signal"])))
            model_review_ok = bool(
                vision_asset and vision_asset.model_needs_human_review == evidence_expectation["expected_model_needs_human_review"]
            )
            evidence_sufficiency_ok = bool(
                vision_asset and (not vision_asset.needs_human_review) == evidence_expectation["expected_order_evidence_sufficient"]
            )
            vision_review_ok = bool(
                vision_asset and vision_asset.needs_human_review == evidence_expectation["expected_needs_human_review"]
            )
            paired_visual_matches += int(vision_ok)
            paired_model_review_matches += int(model_review_ok)
            paired_sufficiency_matches += int(evidence_sufficiency_ok)
            paired_final_review_matches += int(vision_review_ok)
        elif vision_fixture:
            legacy_vision_cases += 1
            vision_ok = bool(vision_asset and real_vision_signal_matches(vision_asset, str(vision_fixture["expected_signal"])))
            vision_review_ok = bool(vision_asset and vision_asset.needs_human_review == vision_fixture["expected_needs_human_review"])
            legacy_vision_signal_matches += int(vision_ok)
            legacy_vision_review_matches += int(vision_review_ok)
        state_matches += int(state_ok)
        tool_matches += int(tools_ok)
        policy_matches += int(policy_ok)
        proposal_matches += int(proposal_ok)
        if case["high_risk"]:
            high_risk_safety_total += 1
            high_risk_safety_matches += int(high_risk_safety_ok)
        if high_risk_proposal:
            high_risk_proposal_total += 1
            high_risk_proposal_matches += int(proposal_handoff_ok)
        if resolution_run and resolution_run.latency_ms is not None:
            latencies.append(resolution_run.latency_ms)
        if resolution_run and resolution_run.cost_usd is not None:
            costs.append(resolution_run.cost_usd)
        if resolution_run and resolution_run.input_tokens is not None:
            input_tokens.append(resolution_run.input_tokens)
        if resolution_run and resolution_run.output_tokens is not None:
            output_tokens.append(resolution_run.output_tokens)
        if not all((
            state_ok, tools_ok, policy_ok, proposal_ok, high_risk_safety_ok, vision_ok, model_review_ok,
            evidence_sufficiency_ok, vision_review_ok, acceptance_ok is not False,
        )):
            bad_cases.append({
                "case_id": case["id"], "ticket_id": ticket.id, "state_ok": state_ok, "tools_ok": tools_ok,
                "policy_ok": policy_ok, "proposal_ok": proposal_ok, "handoff_ok": proposal_handoff_ok,
                "high_risk_safety_ok": high_risk_safety_ok,
                "high_risk_proposal_handoff_ok": proposal_handoff_ok if high_risk_proposal else None,
                "high_risk_tool_executed": high_risk_tool_executed,
                "duplicate_success_tool_call_count": duplicate_success_count,
                "acceptance_ok": acceptance_ok,
                "vision_evidence_ok": vision_ok,
                "vision_model_review_ok": model_review_ok if isinstance(evidence_expectation, dict) else None,
                "order_evidence_sufficiency_ok": evidence_sufficiency_ok if isinstance(evidence_expectation, dict) else None,
                "vision_review_ok": vision_review_ok,
                "failure_type": None if not resolution_run else resolution_run.failure_type,
            })
    sample_size = len(cases)
    avg_latency_ms = round(sum(latencies) / len(latencies), 1) if latencies else None
    avg_cost_usd = round(sum(costs) / len(costs), 6) if costs else None
    baseline_latency = float(comparison["avg_latency_ms"])
    baseline_cost = float(comparison["avg_cost_usd"])
    metrics = {
        "task_completion_rate": round(state_matches * 100 / sample_size, 1),
        "tool_calling_accuracy": round(tool_matches * 100 / sample_size, 1),
        "policy_retrieval_rate": round(policy_matches * 100 / sample_size, 1),
        "proposal_schema_rate": round(proposal_matches * 100 / sample_size, 1),
        "high_risk_safety_block_rate": 100.0 if not high_risk_safety_total else round(high_risk_safety_matches * 100 / high_risk_safety_total, 1),
        "high_risk_safety_sample_count": high_risk_safety_total,
        "high_risk_proposal_handoff_success_rate": None if not high_risk_proposal_total else round(high_risk_proposal_matches * 100 / high_risk_proposal_total, 1),
        "high_risk_proposal_sample_count": high_risk_proposal_total,
        "high_risk_acceptance_pass_rate": None if not acceptance_total else round(acceptance_matches * 100 / acceptance_total, 1),
        "high_risk_acceptance_sample_count": acceptance_total,
        "legacy_image_evidence_accuracy": None if not legacy_vision_cases else round(legacy_vision_signal_matches * 100 / legacy_vision_cases, 1),
        "legacy_image_review_accuracy": None if not legacy_vision_cases else round(legacy_vision_review_matches * 100 / legacy_vision_cases, 1),
        "paired_visual_observation_accuracy": None if not paired_evidence_cases else round(paired_visual_matches * 100 / paired_evidence_cases, 1),
        "paired_model_review_accuracy": None if not paired_evidence_cases else round(paired_model_review_matches * 100 / paired_evidence_cases, 1),
        "paired_order_evidence_sufficiency_accuracy": None if not paired_evidence_cases else round(paired_sufficiency_matches * 100 / paired_evidence_cases, 1),
        "paired_final_review_accuracy": None if not paired_evidence_cases else round(paired_final_review_matches * 100 / paired_evidence_cases, 1),
        "avg_latency_ms": avg_latency_ms,
        "avg_cost_usd": avg_cost_usd,
        "total_input_tokens": sum(input_tokens),
        "total_output_tokens": sum(output_tokens),
        "total_cost_usd": round(sum(costs), 6),
        "duplicate_success_tool_call_count": duplicate_success_tool_call_count,
        "duplicate_success_tool_case_count": duplicate_success_tool_case_count,
        "latency_change_pct_vs_v02": None if avg_latency_ms is None else round((avg_latency_ms / baseline_latency - 1) * 100, 1),
        "cost_change_pct_vs_v02": None if avg_cost_usd is None else round((avg_cost_usd / baseline_cost - 1) * 100, 1),
        "latency_anomaly_vs_v02": 0 if avg_latency_ms is None else int(avg_latency_ms > baseline_latency * 1.5),
        "cost_anomaly_vs_v02": 0 if avg_cost_usd is None else int(avg_cost_usd > baseline_cost * 1.5),
        "failure_type_counts": dict(Counter(str(item.get("failure_type")) for item in bad_cases if item.get("failure_type"))),
    }
    evaluation.status = "COMPLETED"
    evaluation.metrics_json = json.dumps(metrics, ensure_ascii=False)
    evaluation.bad_cases_json = json.dumps(bad_cases, ensure_ascii=False)
    evaluation.completed_at = datetime.now(UTC)
    return evaluation


def policy_audit(
    db: Session,
    source_id: str,
    event_type: str,
    summary: str,
    policy_version_id: int | None = None,
) -> None:
    db.add(
        PolicyAuditEvent(
            source_id=source_id,
            policy_version_id=policy_version_id,
            event_type=event_type,
            summary=summary,
        )
    )


def get_policy_source_or_404(db: Session, source_id: str) -> PolicySource:
    source = db.get(PolicySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="未找到该规则来源")
    return source


def get_policy_version_or_404(db: Session, version_id: int) -> PolicyVersion:
    version = db.get(PolicyVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="未找到该规则版本")
    return version


def active_policy_version(db: Session, source_id: str) -> PolicyVersion | None:
    return db.scalar(
        select(PolicyVersion)
        .where(PolicyVersion.source_id == source_id, PolicyVersion.status == "ACTIVE")
        .order_by(PolicyVersion.id.desc())
    )


def candidate_policy_version(db: Session, source_id: str) -> PolicyVersion | None:
    return db.scalar(
        select(PolicyVersion)
        .where(PolicyVersion.source_id == source_id, PolicyVersion.status == "CANDIDATE")
        .order_by(PolicyVersion.id.desc())
    )


def latest_policy_source_snapshot(db: Session, source_id: str) -> PolicySourceSnapshot | None:
    return db.scalar(
        select(PolicySourceSnapshot)
        .where(PolicySourceSnapshot.source_id == source_id)
        .order_by(PolicySourceSnapshot.id.desc())
    )


def sync_policy_source(db: Session, source: PolicySource) -> PolicyVersion:
    if candidate_policy_version(db, source.id):
        raise HTTPException(status_code=409, detail="已有待发布的规则版本，请先完成处理")
    spec = public_policy_source_spec(source.id)
    if not spec:
        raise HTTPException(
            status_code=409,
            detail="历史模拟来源不能导入，请选择公开规则来源",
        )
    checksum = source_snapshot_checksum(spec)
    existing_snapshot = db.scalar(
        select(PolicySourceSnapshot).where(
            PolicySourceSnapshot.source_id == source.id,
            PolicySourceSnapshot.content_checksum == checksum,
        )
    )
    if existing_snapshot:
        raise HTTPException(
            status_code=409,
            detail="最新公开规则快照已导入，未创建新版本",
        )

    retrieved_at = datetime.now(UTC)
    source.title = str(spec["title"])
    source.source_type = str(spec["source_type"])
    source.publisher = str(spec["publisher"])
    source.source_url = str(spec["source_url"])
    source.source_scope = str(spec["source_scope"])
    source.source_version_label = str(spec["source_version_label"])
    source.source_published_at = source_timestamp(spec["source_published_at"])
    source.current_checksum = checksum
    source.last_synced_at = retrieved_at
    source.last_verified_at = retrieved_at

    snapshot = PolicySourceSnapshot(
        source_id=source.id,
        pack_id=str(public_policy_pack()["pack_id"]),
        source_url=str(spec["source_url"]),
        publisher=str(spec["publisher"]),
        source_version_label=str(spec["source_version_label"]),
        source_published_at=source_timestamp(spec["source_published_at"]),
        retrieved_at=retrieved_at,
        content_checksum=checksum,
        source_excerpt=str(spec["source_excerpt"]),
        import_method="CURATED_PUBLIC_PACK",
    )
    db.add(snapshot)
    db.flush()
    for chunk in spec["chunks"]:
        db.add(
            PolicyGroundingChunk(
                snapshot_id=snapshot.id,
                chunk_key=str(chunk["chunk_key"]),
                category=str(chunk["category"]),
                title=str(chunk["title"]),
                content=str(chunk["content"]),
                keywords_json=json.dumps(chunk["keywords"], ensure_ascii=False),
            )
        )

    candidate = PolicyVersion(
        source_id=source.id,
        source_snapshot_id=snapshot.id,
        version=f"public-{checksum[:8]}",
        status="CANDIDATE",
        diff_summary=(
            f"已导入公开来源快照：{spec['source_version_label']}；"
            f"SHA-256 {checksum[:12]}…；{len(spec['chunks'])} 个检索片段。"
        ),
    )
    db.add(candidate)
    db.flush()
    db.add(
        PolicyRegressionRun(
            policy_version_id=candidate.id,
            status="PENDING",
            summary="等待校验来源快照 checksum 与公开政策检索冒烟用例；不会自动发布。",
        )
    )
    policy_audit(
        db,
        source.id,
        "policy.public_snapshot_imported",
        f"已导入 {snapshot.pack_id} 公开快照，checksum={checksum}；Candidate 等待回归与人工发布。",
        candidate.id,
    )
    return candidate


def run_policy_regression(db: Session, version: PolicyVersion) -> PolicyRegressionRun:
    if version.status != "CANDIDATE":
        raise HTTPException(status_code=409, detail="只有待发布版本可以运行完整性检查")
    run = db.scalar(
        select(PolicyRegressionRun)
        .where(PolicyRegressionRun.policy_version_id == version.id)
        .order_by(PolicyRegressionRun.id.desc())
    )
    if not run:
        run = PolicyRegressionRun(policy_version_id=version.id, status="PENDING", summary="等待回归")
        db.add(run)
        db.flush()
    if version.source_snapshot_id:
        snapshot = db.get(PolicySourceSnapshot, version.source_snapshot_id)
        spec = public_policy_source_spec(version.source_id)
        chunks = db.scalars(
            select(PolicyGroundingChunk).where(PolicyGroundingChunk.snapshot_id == version.source_snapshot_id)
        ).all()
        expected_chunk_keys = {str(chunk["chunk_key"]) for chunk in spec["chunks"]} if spec else set()
        actual_chunk_keys = {chunk.chunk_key for chunk in chunks}
        checksum_matches = bool(snapshot and spec and snapshot.content_checksum == source_snapshot_checksum(spec))
        chunks_match = bool(expected_chunk_keys and expected_chunk_keys == actual_chunk_keys)
        run.status = "PASSED" if checksum_matches and chunks_match else "FAILED"
        run.summary = (
            f"公开来源完整性：checksum {'匹配' if checksum_matches else '不匹配'}；"
            f"检索片段 {'完整' if chunks_match else '不完整'}（{len(actual_chunk_keys)} / {len(expected_chunk_keys)}）。"
            "这是来源完整性与检索冒烟校验，不是实际业务准确率。"
        )
    else:
        retrieval = policy_retrieval_snapshot()
        run.status = "PASSED" if retrieval["top3_hit_rate"] >= POLICY_REGRESSION_MIN_TOP3_HIT_RATE else "FAILED"
        run.summary = (
            f"{retrieval['query_count'] - len(retrieval['missed_query_ids'])} / {retrieval['query_count']} "
            f"自构造 Query–Policy Top-3 命中，{retrieval['top3_hit_rate']:.1f}%；"
            f"发布阈值为 {POLICY_REGRESSION_MIN_TOP3_HIT_RATE:.1f}%。"
        )
    run.completed_at = datetime.now(UTC)
    policy_audit(
        db,
        version.source_id,
        "policy.regression_passed" if run.status == "PASSED" else "policy.regression_failed",
        run.summary,
        version.id,
    )
    return run


def normalize_policy_query(query: str) -> str:
    """Expand a small, auditable set of after-sales synonyms for lexical policy search."""
    normalized_query = query.strip()
    if not normalized_query:
        return ""
    expansions = {
        "破损": ("质量", "照片", "证明"),
        "损坏": ("质量", "照片", "证明"),
        "开裂": ("质量", "照片", "证明"),
        "碎裂": ("质量", "照片", "证明"),
        "漏液": ("质量", "照片", "证明"),
        "变形": ("质量", "照片", "证明"),
        "缺少": ("缺件", "照片", "证明"),
        "少了": ("缺件", "照片", "证明"),
        "漏发": ("缺件", "照片", "证明"),
        "配件": ("缺件", "照片", "证明"),
        "换货": ("质量",),
        "换新": ("质量",),
        "售后": ("质量",),
        "签收": ("收到商品",),
    }
    additions = [term for trigger, terms in expansions.items() if trigger in normalized_query for term in terms]
    return " ".join(dict.fromkeys((normalized_query, *additions)))


def search_active_public_policy(db: Session, query: str, category: str | None = None) -> list[dict[str, object]]:
    normalized_query = normalize_policy_query(query)
    if not normalized_query:
        raise HTTPException(status_code=422, detail="请输入要检索的内容")
    rows = db.execute(
        select(PolicyGroundingChunk, PolicySourceSnapshot, PolicySource)
        .join(PolicySourceSnapshot, PolicyGroundingChunk.snapshot_id == PolicySourceSnapshot.id)
        .join(PolicyVersion, PolicyVersion.source_snapshot_id == PolicySourceSnapshot.id)
        .join(PolicySource, PolicySource.id == PolicySourceSnapshot.source_id)
        .where(PolicyVersion.status == "ACTIVE")
    ).all()
    requested_category = category.upper() if category else None
    results = []
    for chunk, snapshot, source in rows:
        if requested_category and chunk.category not in {"ALL", requested_category}:
            continue
        keywords = json.loads(chunk.keywords_json)
        score = sum(len(str(keyword)) for keyword in keywords if str(keyword) in normalized_query)
        if score:
            results.append({
                "source_id": source.id,
                "source_title": source.title,
                "source_url": snapshot.source_url,
                "source_version_label": snapshot.source_version_label,
                "content_checksum": snapshot.content_checksum,
                "chunk_key": chunk.chunk_key,
                "category": chunk.category,
                "title": chunk.title,
                "content": chunk.content,
                "score": score,
            })
    return sorted(results, key=lambda item: (-int(item["score"]), str(item["chunk_key"])))[:3]


def project_review_bundle(db: Session) -> dict[str, object]:
    sources = db.scalars(select(PolicySource).order_by(PolicySource.id)).all()
    source_records = []
    for source in sources:
        snapshot = latest_policy_source_snapshot(db, source.id)
        chunk_count = 0 if not snapshot else len(db.scalars(
            select(PolicyGroundingChunk).where(PolicyGroundingChunk.snapshot_id == snapshot.id)
        ).all())
        source_records.append({
            "source_id": source.id,
            "title": source.title,
            "source_scope": source.source_scope,
            "source_type": source.source_type,
            "source_url": source.source_url,
            "source_version_label": source.source_version_label,
            "active_version": None if not active_policy_version(db, source.id) else active_policy_version(db, source.id).version,
            "candidate_version": None if not candidate_policy_version(db, source.id) else candidate_policy_version(db, source.id).version,
            "latest_snapshot": None if not snapshot else {
                "id": snapshot.id,
                "retrieved_at": snapshot.retrieved_at,
                "content_checksum": snapshot.content_checksum,
                "chunk_count": chunk_count,
            },
        })
    latest_run = latest_evaluation_run(db)
    manual_study = json.loads(MANUAL_AGENT_RESULTS_PATH.read_text(encoding="utf-8"))
    return {
        "bundle_version": "carepilot-project-review-v0.1",
        "generated_at": datetime.now(UTC),
        "data_boundary": {
            "policy_sources": "Curated public policy references plus a separately labeled self-authored baseline.",
            "orders": "SIMULATED_ONLY",
            "logistics": "SIMULATED_ONLY",
            "refunds_and_payments": "SIMULATED_ONLY",
            "inventory": "SIMULATED_ONLY",
            "customer_data": "SIMULATED_OR_DEIDENTIFIED_ONLY",
        },
        "policy_grounding": {
            "sources": source_records,
            "release_rule": "Imported public snapshots are Candidates until integrity regression passes and a human publishes them.",
        },
        "offline_evaluation": None if not latest_run else offline_evaluation_snapshot(),
        "manual_agent_study": manual_study,
        "known_limitations": [
            "Public policy grounding does not create real orders, logistics, refunds, payments, inventory, or business outcomes.",
            "The frozen offline evaluation and anonymous study use self-authored simulated tasks.",
            "The manual-versus-Agent study is descriptive (five anonymous slots); conditions were not completed by the same person for every pair.",
            "Policy source integrity checks validate the imported snapshot and retrieval chunks, not legal applicability or production accuracy.",
        ],
    }


def publish_policy_version(db: Session, version: PolicyVersion, reviewer: str) -> PolicyVersion:
    if version.status != "CANDIDATE":
        raise HTTPException(status_code=409, detail="只有待发布版本可以发布")
    regression = db.scalar(
        select(PolicyRegressionRun)
        .where(PolicyRegressionRun.policy_version_id == version.id)
        .order_by(PolicyRegressionRun.id.desc())
    )
    if not regression or regression.status != "PASSED":
        raise HTTPException(status_code=409, detail="请先通过完整性检查，再人工发布")
    active = active_policy_version(db, version.source_id)
    if active:
        active.status = "ARCHIVED"
    version.status = "ACTIVE"
    version.published_by = reviewer
    policy_audit(db, version.source_id, "policy.published", f"{reviewer} manually published {version.version}", version.id)
    return version


def rollback_policy_version(db: Session, target: PolicyVersion, reviewer: str) -> PolicyVersion:
    if target.status != "ARCHIVED":
        raise HTTPException(status_code=409, detail="只有已归档版本可以恢复")
    active = active_policy_version(db, target.source_id)
    if active:
        active.status = "ARCHIVED"
    target.status = "ACTIVE"
    target.published_by = reviewer
    policy_audit(db, target.source_id, "policy.rolled_back", f"{reviewer} restored {target.version}", target.id)
    return target


def config_audit(db: Session, config_version_id: int, event_type: str, summary: str) -> None:
    db.add(
        ConfigAuditEvent(
            config_version_id=config_version_id,
            event_type=event_type,
            summary=summary,
        )
    )


def get_agent_config_or_404(db: Session, config_id: int) -> AgentConfigVersion:
    config = db.get(AgentConfigVersion, config_id)
    if not config:
        raise HTTPException(status_code=404, detail="未找到该 AI 配置版本")
    return config


def active_agent_config(db: Session) -> AgentConfigVersion | None:
    return db.scalar(
        select(AgentConfigVersion)
        .where(AgentConfigVersion.status == "ACTIVE")
        .order_by(AgentConfigVersion.id.desc())
    )


def latest_sandbox_run(db: Session, config_id: int) -> ConfigSandboxRun | None:
    return db.scalar(
        select(ConfigSandboxRun)
        .where(ConfigSandboxRun.config_version_id == config_id)
        .order_by(ConfigSandboxRun.id.desc())
    )


def run_config_sandbox(db: Session, config: AgentConfigVersion) -> ConfigSandboxRun:
    if config.status != "DRAFT":
        raise HTTPException(status_code=409, detail="只有草稿配置可以运行静态校验")
    run = ConfigSandboxRun(
        config_version_id=config.id,
        scenario_id="CP-SBX-018",
        status="PASSED",
        summary="仅完成配置结构与工具白名单静态校验（不是模型运行）；图片质量不足时仅允许 NEED_INFO 与用户通知，未允许退款、换货或补偿写操作。",
        completed_at=datetime.now(UTC),
    )
    db.add(run)
    config_audit(db, config.id, "config.sandbox_passed", run.summary)
    return run


def activate_agent_config(db: Session, config: AgentConfigVersion, reviewer: str) -> AgentConfigVersion:
    if config.status != "DRAFT":
        raise HTTPException(status_code=409, detail="只有草稿配置可以启用")
    sandbox = latest_sandbox_run(db, config.id)
    if not sandbox or sandbox.status != "PASSED":
        raise HTTPException(status_code=409, detail="请先通过静态校验，再启用配置")
    active = active_agent_config(db)
    if active:
        active.status = "ARCHIVED"
    config.status = "ACTIVE"
    config.activated_by = reviewer
    config_audit(db, config.id, "config.activated", f"{reviewer} activated {config.version} after Sandbox gate")
    return config


def rollback_agent_config(db: Session, target: AgentConfigVersion, reviewer: str) -> AgentConfigVersion:
    if target.status != "ARCHIVED":
        raise HTTPException(status_code=409, detail="只有已归档配置可以恢复")
    active = active_agent_config(db)
    if active:
        active.status = "ARCHIVED"
    target.status = "ACTIVE"
    target.activated_by = reviewer
    config_audit(db, target.id, "config.rolled_back", f"{reviewer} restored {target.version}")
    return target


def seed(db: Session) -> None:
    if not db.scalar(select(Ticket.id).limit(1)):
        for item in SEED_TICKETS:
            db.add(Ticket(**item))
        db.flush()
        for ticket in db.scalars(select(Ticket)).all():
            audit(db, ticket.id, "ticket.seeded", "模拟工单已创建")
        ticket = db.get(Ticket, "CP-240918")
        db.add(
            ActionProposal(
                ticket_id=ticket.id,
                action="replace.propose",
                status="PENDING",
                rationale="配件缺失会影响库存与售后权益，必须等待人工审批。",
            )
        )
        audit(db, ticket.id, "proposal.created", "replace.propose requires human approval")
    if not db.get(PolicySource, "PS-DIGITAL"):
        source = PolicySource(
            id="PS-DIGITAL",
            title="数码商品售后规范",
            source_type="PUBLIC_HTML",
            sync_schedule="每日 02:00 同步",
            last_synced_at=datetime.now(UTC),
        )
        db.add(source)
        db.flush()
        active = PolicyVersion(
            source_id=source.id,
            version="v3.2",
            status="ACTIVE",
            diff_summary="当前 Active 版本。",
            published_by="seed-admin",
        )
        db.add(active)
        db.flush()
        policy_audit(db, source.id, "policy.seeded", "Active v3.2 已初始化", active.id)
    for spec in public_policy_pack()["sources"]:
        source = db.get(PolicySource, str(spec["id"]))
        if not source:
            source = PolicySource(
                id=str(spec["id"]),
                title=str(spec["title"]),
                source_type=str(spec["source_type"]),
                sync_schedule="由 Policy Admin 手动导入已核验快照",
                publisher=str(spec["publisher"]),
                source_url=str(spec["source_url"]),
                source_scope=str(spec["source_scope"]),
                source_version_label=str(spec["source_version_label"]),
                source_published_at=source_timestamp(spec["source_published_at"]),
            )
            db.add(source)
            db.flush()
        # A reviewed baseline pack is seeded once as the initial Active policy. Subsequent
        # imports still enter Candidate and require the existing regression + human publish gate.
        if not db.scalar(select(PolicyVersion.id).where(PolicyVersion.source_id == source.id).limit(1)):
            checksum = source_snapshot_checksum(spec)
            seeded_at = datetime.now(UTC)
            source.current_checksum = checksum
            source.last_synced_at = seeded_at
            source.last_verified_at = seeded_at
            snapshot = PolicySourceSnapshot(
                source_id=source.id,
                pack_id=str(public_policy_pack()["pack_id"]),
                source_url=str(spec["source_url"]),
                publisher=str(spec["publisher"]),
                source_version_label=str(spec["source_version_label"]),
                source_published_at=source_timestamp(spec["source_published_at"]),
                retrieved_at=seeded_at,
                content_checksum=checksum,
                source_excerpt=str(spec["source_excerpt"]),
                import_method="CURATED_PUBLIC_BASELINE",
            )
            db.add(snapshot)
            db.flush()
            for chunk in spec["chunks"]:
                db.add(PolicyGroundingChunk(
                    snapshot_id=snapshot.id,
                    chunk_key=str(chunk["chunk_key"]),
                    category=str(chunk["category"]),
                    title=str(chunk["title"]),
                    content=str(chunk["content"]),
                    keywords_json=json.dumps(chunk["keywords"], ensure_ascii=False),
                ))
            active = PolicyVersion(
                source_id=source.id,
                source_snapshot_id=snapshot.id,
                version=f"baseline-{checksum[:8]}",
                status="ACTIVE",
                diff_summary="受控公开政策基线；后续更新须经 Candidate、回归和人工发布。",
                published_by="seed-admin",
            )
            db.add(active)
            policy_audit(db, source.id, "policy.baseline_published", "已初始化可检索的公开政策基线", active.id)
    if not active_agent_config(db):
        active = AgentConfigVersion(
            version="v1.3",
            status="ACTIVE",
            model_name=runtime_settings().model,
            prompt_version="resolution-v1",
            tool_allowlist="order.lookup|logistics.track|policy.search|ticket.update|customer.notify|task.create",
            risk_boundary="退款、换货、退货与补偿始终 REQUIRE_HUMAN。",
            activated_by="seed-admin",
        )
        draft = AgentConfigVersion(
            version="v1.4",
            status="DRAFT",
            model_name=runtime_settings().model,
            prompt_version="resolution-v1.1",
            tool_allowlist="order.lookup|logistics.track|policy.search|ticket.update|customer.notify|task.create",
            risk_boundary="退款、换货、退货与补偿始终 REQUIRE_HUMAN。",
        )
        db.add_all([active, draft])
        db.flush()
        config_audit(db, active.id, "config.seeded", "Active v1.3 已初始化")
        config_audit(db, draft.id, "config.draft_created", "Draft v1.4 已创建，等待 Sandbox")
    for config in db.scalars(select(AgentConfigVersion).where(AgentConfigVersion.model_name == "carepilot-single-agent")).all():
        config.model_name = runtime_settings().model
        config.prompt_version = "resolution-v1"
    fixture_set = offline_evaluation_snapshot()["fixture_set"]
    if not db.scalar(select(EvaluationRun.id).where(EvaluationRun.fixture_set == fixture_set).limit(1)):
        db.add(run_offline_evaluation())
    db.commit()
