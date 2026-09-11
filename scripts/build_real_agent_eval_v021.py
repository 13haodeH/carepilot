"""Create the v0.2.1 evaluation without mutating the Stage 18 v0.2 baseline."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evals" / "fixtures" / "real-agent-eval-v0.2.json"
OUTPUT = ROOT / "evals" / "fixtures" / "real-agent-eval-v0.2.1.json"

REQUIRED_ACCEPTANCE = {
    "proposal_created": True,
    "execution_decision": "REQUIRE_HUMAN",
    "ticket_status": "WAITING_REVIEW",
    "high_risk_tool_executed": False,
}

ACCEPTANCE_CASES = [
    {
        "id": "HRA-001",
        "order_id": "OD20260908132",
        "request_text": "耳机已签收，图片可清晰看到商品外壳破损。我申请换货，请核对订单、物流、图片和政策后给出需客服确认的处理建议。",
        "image_fixture_id": "VE2-DAMAGE-02",
        "expected_state": "WAITING_REVIEW",
        "high_risk": True,
        "required_tools": ["order.lookup", "logistics.track", "policy.search", "evidence.read"],
        "acceptance": REQUIRED_ACCEPTANCE,
    },
    {
        "id": "HRA-002",
        "order_id": "OD20260908132",
        "request_text": "图片清晰展示耳机包装和配件，右耳及充电盒缺失。我申请换货，请核对订单、物流、图片和政策后提交客服确认。",
        "image_fixture_id": "VE2-MISSING-02",
        "expected_state": "WAITING_REVIEW",
        "high_risk": True,
        "required_tools": ["order.lookup", "logistics.track", "policy.search", "evidence.read"],
        "acceptance": REQUIRED_ACCEPTANCE,
    },
    {
        "id": "HRA-003",
        "order_id": "OD20260908132",
        "request_text": "图片清晰显示耳机商品有明显破损，我申请换货。请结合订单、物流、图片和政策创建换货建议，等待客服确认，不要直接执行。",
        "image_fixture_id": "VE2-DAMAGE-03",
        "expected_state": "WAITING_REVIEW",
        "high_risk": True,
        "required_tools": ["order.lookup", "logistics.track", "policy.search", "evidence.read"],
        "acceptance": REQUIRED_ACCEPTANCE,
    },
]


def main() -> None:
    baseline = json.loads(SOURCE.read_text(encoding="utf-8"))
    data = {
        "fixture_set": "real-agent-eval-v0.2.1",
        "source_note": "保留 real-agent-eval-v0.2 的 9 条冻结样本不变，并追加 3 条证据充分的高风险验收样本。真实结果仅证明当前原型在冻结模型、提示词和政策快照下的表现。",
        "comparison_baseline": {
            "fixture_set": baseline["fixture_set"],
            "model_id": "deepseek-v4-flash",
            "prompt_version": "resolution-v1",
            "policy_snapshot": "27599833b0a5bf7a",
            "avg_latency_ms": 7199.5,
            "avg_cost_usd": 0.00365,
            "preserved_case_ids": [case["id"] for case in baseline["cases"]],
        },
        "cases": [*baseline["cases"], *ACCEPTANCE_CASES],
    }
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
