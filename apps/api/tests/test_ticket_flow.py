import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient


class TicketFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.temp_dir.name}/carepilot-test.db"
        from app.auth import CurrentUser, get_current_user
        from app.main import app

        cls.CurrentUser = CurrentUser
        cls.current_user = CurrentUser(id="00000000-0000-4000-8000-000000000001", email="ops@example.test", display_name="测试客服", role="superadmin")
        app.dependency_overrides[get_current_user] = lambda: cls.current_user
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        cls.temp_dir.cleanup()

    def setUp(self):
        self.__class__.current_user = self.CurrentUser(
            id="00000000-0000-4000-8000-000000000001", email="ops@example.test", display_name="测试客服", role="superadmin"
        )

    def test_low_risk_ticket_auto_closes_once(self):
        response = self.client.post(
            "/api/tickets/CP-240917/process",
            headers={"Idempotency-Key": "demo-low-risk-1"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "RESOLVED")
        self.assertEqual([tool["tool_name"] for tool in payload["tool_executions"]], [
            "order.lookup", "logistics.track", "policy.search", "task.create", "customer.notify"
        ])
        repeated = self.client.post("/api/tickets/CP-240917/process", headers={"Idempotency-Key": "demo-low-risk-1"})
        self.assertEqual(repeated.status_code, 409)

    def test_high_risk_review_requires_human_then_records_approval(self):
        initial = self.client.get("/api/tickets/CP-240918").json()
        self.assertEqual(initial["status"], "WAITING_REVIEW")
        self.assertEqual(initial["proposal"]["action"], "replace.propose")
        approved = self.client.post("/api/tickets/CP-240918/review", json={"decision": "APPROVE", "note": "照片与订单信息一致"})
        self.assertEqual(approved.status_code, 200)
        payload = approved.json()
        self.assertEqual(payload["status"], "RESOLVED")
        self.assertEqual(payload["proposal"]["status"], "APPROVED")
        self.assertIn("human.reviewed", [event["event_type"] for event in payload["audit_events"]])
        self.assertNotIn("replace.execute", [tool["tool_name"] for tool in payload["tool_executions"]])

    def test_need_info_requires_evidence_before_reprocessing(self):
        initial = self.client.get("/api/tickets/CP-240916")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["risk"], "MEDIUM")
        without_upload = self.client.post("/api/tickets/CP-240916/submit-evidence")
        self.assertEqual(without_upload.status_code, 409)

        image_path = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "evidence-images-v0.1" / "EVI-A-11.png"
        with image_path.open("rb") as image:
            uploaded = self.client.post(
                "/api/tickets/CP-240916/evidence-files",
                files={"files": (image_path.name, image.read(), "image/png")},
            )
        self.assertEqual(uploaded.status_code, 201)
        evidence = uploaded.json()["evidence_assets"]
        self.assertEqual(evidence[0]["fixture_id"], "EVI-A-11")
        self.assertEqual(evidence[0]["analysis_origin"], "FIXTURE_ANNOTATION")
        self.assertFalse(evidence[0]["needs_human_review"])

        response = self.client.post("/api/tickets/CP-240916/submit-evidence")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "PROCESSING")
        reviewed = self.client.post("/api/tickets/CP-240916/process")
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(reviewed.json()["status"], "WAITING_REVIEW")
        self.assertEqual(reviewed.json()["proposal"]["action"], "replace.propose")
        invalid = self.client.post("/api/tickets/CP-240916/submit-evidence")
        self.assertEqual(invalid.status_code, 409)

    def test_policy_publish_requires_regression_and_named_reviewer(self):
        from app.database import SessionLocal
        from app.models import PolicySourceSnapshot, PolicyVersion
        from sqlalchemy import select

        source = self.client.get("/api/policy-sources/PS-SAMR-7DAY")
        self.assertEqual(source.status_code, 200)
        self.assertEqual(source.json()["source_scope"], "PUBLIC_POLICY_REFERENCE")
        self.assertEqual(source.json()["active_version"]["status"], "ACTIVE")
        self.assertIsNone(source.json()["candidate_version"])

        # A changed public source is first represented as a Candidate. The
        # bootstrapped Active baseline is deliberately available to real runs.
        db = SessionLocal()
        try:
            snapshot = db.scalar(select(PolicySourceSnapshot).where(PolicySourceSnapshot.source_id == "PS-SAMR-7DAY"))
            candidate = PolicyVersion(
                source_id="PS-SAMR-7DAY",
                source_snapshot_id=snapshot.id,
                version="public-test-publish",
                status="CANDIDATE",
                diff_summary="test candidate for manual publication gate",
            )
            db.add(candidate)
            db.commit()
            candidate_id = candidate.id
        finally:
            db.close()

        blocked = self.client.post(f"/api/policy-versions/{candidate_id}/publish", json={"reviewer": "admin"})
        self.assertEqual(blocked.status_code, 409)

        regressed = self.client.post(f"/api/policy-versions/{candidate_id}/regression")
        self.assertEqual(regressed.status_code, 200)
        self.assertEqual(regressed.json()["regressions"][0]["status"], "PASSED")

        published = self.client.post(f"/api/policy-versions/{candidate_id}/publish", json={"reviewer": "ops-admin"})
        self.assertEqual(published.status_code, 200)
        payload = published.json()
        self.assertTrue(payload["active_version"]["version"].startswith("public-"))
        self.assertIsNone(payload["candidate_version"])
        self.assertIn("policy.published", [event["event_type"] for event in payload["audit_events"]])

    def test_policy_regression_blocks_failed_retrieval(self):
        from app.database import SessionLocal
        from app.models import PolicySourceSnapshot, PolicyVersion
        from sqlalchemy import select

        db = SessionLocal()
        try:
            snapshot = db.scalar(select(PolicySourceSnapshot).where(PolicySourceSnapshot.source_id == "PS-JD-DIGITAL-SELF"))
            candidate = PolicyVersion(
                source_id="PS-JD-DIGITAL-SELF",
                source_snapshot_id=snapshot.id,
                version="public-test-failure",
                status="CANDIDATE",
                diff_summary="test candidate for failed source integrity check",
            )
            db.add(candidate)
            db.commit()
            candidate_id = candidate.id
        finally:
            db.close()

        with patch("app.domain.source_snapshot_checksum", return_value="0" * 64):
            regressed = self.client.post(f"/api/policy-versions/{candidate_id}/regression")

        self.assertEqual(regressed.status_code, 200)
        self.assertEqual(regressed.json()["regressions"][0]["status"], "FAILED")
        blocked = self.client.post(f"/api/policy-versions/{candidate_id}/publish", json={"reviewer": "ops-admin"})
        self.assertEqual(blocked.status_code, 409)

    def test_real_agent_without_key_fails_explicitly_without_fixture_fallback(self):
        from app.settings import RuntimeSettings

        self.__class__.current_user = self.CurrentUser(
            id="00000000-0000-4000-8000-000000000002", email="consumer@example.test", display_name="测试用户", role="user"
        )
        orders = self.client.get("/api/orders")
        self.assertEqual(orders.status_code, 200)
        created = self.client.post(
            "/api/tickets",
            json={"order_id": "OD20260907086", "request_text": "物流三天没有更新，请查询现在的状态。"},
        )
        self.assertEqual(created.status_code, 201)
        with patch("app.domain.runtime_settings", return_value=RuntimeSettings(
            api_key=None,
            base_url="https://api.openai.com/v1",
            model="gpt-4.1-mini-2025-04-14",
            vision_model="gpt-4.1-mini-2025-04-14",
            input_usd_per_million=0.40,
            output_usd_per_million=1.60,
        )):
            processed = self.client.post(f"/api/tickets/{created.json()['id']}/process")
        self.assertEqual(processed.status_code, 200)
        payload = processed.json()
        self.assertEqual(payload["execution_mode"], "REAL_AGENT_RUN")
        self.assertEqual(payload["status"], "FAILED")
        self.assertEqual(payload["agent_runs"][0]["failure_type"], "REAL_MODEL_NOT_CONFIGURED")
        self.assertEqual(payload["tool_executions"], [])

    def test_role_boundaries_are_enforced_server_side(self):
        self.__class__.current_user = self.CurrentUser(
            id="00000000-0000-4000-8000-000000000002", email="consumer@example.test", display_name="测试用户", role="user"
        )
        self.assertEqual(self.client.get("/api/tickets").status_code, 403)
        self.assertEqual(self.client.get("/api/policy-sources").status_code, 403)

        self.__class__.current_user = self.CurrentUser(
            id="00000000-0000-4000-8000-000000000001", email="ops@example.test", display_name="测试客服", role="admin"
        )
        self.assertEqual(self.client.get("/api/tickets").status_code, 200)
        self.assertEqual(self.client.get("/api/policy-sources").status_code, 403)

        self.__class__.current_user = self.CurrentUser(
            id="00000000-0000-4000-8000-000000000003", email="super@example.test", display_name="测试管理员", role="superadmin"
        )
        self.assertEqual(self.client.get("/api/policy-sources").status_code, 200)

    def test_responses_runtime_translates_provider_function_names_into_audited_tools(self):
        from app.agent_runtime import OpenAIResponsesRuntime
        from app.settings import RuntimeSettings

        runtime = OpenAIResponsesRuntime(RuntimeSettings(
            api_key="test-server-key",
            base_url="https://api.openai.com/v1",
            model="test-model",
            vision_model="test-model",
            input_usd_per_million=0.40,
            output_usd_per_million=1.60,
        ))
        calls = iter([
            {"id": "r1", "status": "completed", "usage": {"input_tokens": 10, "output_tokens": 2}, "output": [{"type": "function_call", "name": "order_lookup", "arguments": '{"order_id":"OD20260907086"}', "call_id": "c1"}]},
            {"id": "r2", "status": "completed", "usage": {"input_tokens": 12, "output_tokens": 2}, "output": [{"type": "function_call", "name": "logistics_track", "arguments": '{"order_id":"OD20260907086"}', "call_id": "c2"}]},
            {"id": "r3", "status": "completed", "usage": {"input_tokens": 12, "output_tokens": 2}, "output": [{"type": "function_call", "name": "policy_search", "arguments": '{"query":"物流延迟","category":"HOME"}', "call_id": "c3"}]},
            {"id": "r4", "status": "completed", "usage": {"input_tokens": 12, "output_tokens": 40}, "output": [], "output_text": '{"intent":"物流延迟","category":"HOME","summary":"物流信息已读取，建议创建查询跟进任务。","requested_action":"task.create","proposed_status":"RESOLVED","rationale":"订单和物流状态均已核验，公开政策引用支持发送物流跟进说明。","customer_message":"已为您创建物流跟进任务。","confidence":0.88,"policy_citations":[{"source_id":"PS-JD-HOME","chunk_key":"home-delay","title":"物流延迟说明"}],"evidence_ids":[],"missing_information":[]}'},
        ])
        executed: list[str] = []

        def fake_call(_payload):
            return next(calls), 5

        def execute_tool(name, arguments):
            executed.append(name)
            if name == "policy.search":
                return {"citations": [{"source_id": "PS-JD-HOME", "chunk_key": "home-delay", "title": "物流延迟说明"}]}
            return {"ok": True, "arguments": arguments}

        runtime._call = fake_call
        resolution, trace, policy_evidence, usage = runtime.run_resolution(
            {"ticket_id": "CP-T", "order_id": "OD20260907086", "user_request": "物流未更新"},
            execute_tool,
        )
        self.assertEqual(executed, ["order.lookup", "logistics.track", "policy.search"])
        self.assertEqual([item["name"] for item in trace], executed)
        self.assertEqual(policy_evidence[0]["chunk_key"], "home-delay")
        self.assertEqual(resolution.requested_action, "task.create")
        self.assertEqual(usage.input_tokens, 46)
        self.assertEqual(usage.output_tokens, 46)

    def test_deepseek_responses_runtime_replays_tool_history_without_previous_response_id(self):
        from copy import deepcopy

        from app.agent_runtime import OpenAIResponsesRuntime
        from app.settings import RuntimeSettings

        runtime = OpenAIResponsesRuntime(RuntimeSettings(
            api_key="test-deepseek-server-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            vision_model="deepseek-v4-flash-vision-exp",
            input_usd_per_million=0.44,
            output_usd_per_million=1.32,
        ))
        responses = iter([
            {"id": "d1", "status": "completed", "usage": {"input_tokens": 10, "output_tokens": 2}, "output": [{"type": "function_call", "name": "order_lookup", "arguments": '{"order_id":"OD20260907086"}', "call_id": "dc1"}]},
            {"id": "d2", "status": "completed", "usage": {"input_tokens": 12, "output_tokens": 30}, "output": [], "output_text": '{"intent":"物流延迟","category":"HOME","summary":"订单已读取，等待继续处理。","requested_action":"need_info","proposed_status":"NEED_INFO","rationale":"该单元测试只验证无状态 Tool 上下文传递。","customer_message":"请补充需要查询的具体物流信息。","confidence":0.7,"policy_citations":[],"evidence_ids":[],"missing_information":["物流单号"]}'},
        ])
        payloads = []

        def fake_call(payload):
            payloads.append(deepcopy(payload))
            return next(responses), 5

        runtime._call = fake_call
        runtime.run_resolution(
            {"ticket_id": "CP-T", "order_id": "OD20260907086", "user_request": "物流未更新"},
            lambda name, arguments: {"name": name, "arguments": arguments},
        )
        self.assertNotIn("previous_response_id", payloads[1])
        self.assertTrue(any(item.get("type") == "function_call" for item in payloads[1]["input"]))
        self.assertTrue(any(item.get("type") == "function_call_output" for item in payloads[1]["input"]))

    def test_resolution_runtime_allows_sequential_required_tool_calls(self):
        from app.agent_runtime import OpenAIResponsesRuntime
        from app.settings import RuntimeSettings

        runtime = OpenAIResponsesRuntime(RuntimeSettings(
            api_key="test-deepseek-server-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            vision_model="deepseek-v4-flash-vision-exp",
            input_usd_per_million=0.44,
            output_usd_per_million=1.32,
        ))
        response_text = '{"intent":"缺件咨询","category":"DIGITAL","summary":"已读取订单和图片信息，需补充材料。","requested_action":"need_info","proposed_status":"NEED_INFO","rationale":"图片与订单商品的一致性不足，需要用户补充清晰的商品与配件照片。","customer_message":"请补拍商品、包装和全部配件，以便继续核验。","confidence":0.7,"policy_citations":[{"source_id":"PS-1","chunk_key":"digital-return","title":"数码售后"}],"evidence_ids":[1],"missing_information":["清晰配件照片"]}'
        responses = iter([
            {"status": "completed", "usage": {}, "output": [{"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}]}
            for name, arguments, call_id in (
                ("order_lookup", '{"order_id":"OD20260908132"}', "tc-1"),
                ("logistics_track", '{"order_id":"OD20260908132"}', "tc-2"),
                ("policy_search", '{"query":"耳机缺件","category":"DIGITAL"}', "tc-3"),
                ("evidence_read", '{"ticket_id":"CP-TEST"}', "tc-4"),
                ("ticket_history", '{"ticket_id":"CP-TEST"}', "tc-5"),
            )
        ] + [{"status": "completed", "usage": {}, "output_text": response_text, "output": []}])

        runtime._call = lambda _: (next(responses), 1)
        _, trace, _, _ = runtime.run_resolution(
            {"ticket_id": "CP-TEST", "order_id": "OD20260908132", "available_evidence_count": 1},
            lambda name, arguments: {"citations": [{"source_id": "PS-1", "chunk_key": "digital-return", "title": "数码售后"}]} if name == "policy.search" else {"ok": True, "arguments": arguments},
        )
        self.assertEqual([item["name"] for item in trace], [
            "order.lookup", "logistics.track", "policy.search", "evidence.read", "ticket.history",
        ])

    def test_deepseek_vision_runtime_uses_the_separate_vision_model(self):
        from app.agent_runtime import OpenAIResponsesRuntime
        from app.settings import RuntimeSettings

        runtime = OpenAIResponsesRuntime(RuntimeSettings(
            api_key="test-deepseek-server-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            vision_model="deepseek-v4-flash-vision-exp",
            input_usd_per_million=0.44,
            output_usd_per_million=1.32,
        ))
        payloads = []

        def fake_call(payload):
            payloads.append(payload)
            return {
                "status": "completed",
                "usage": {"input_tokens": 12, "output_tokens": 18},
                "output_text": '{"evidence_type":"商品与包装","damage_type":null,"damage_location":null,"packaging_status":"包装可见","missing_parts":null,"label_match":"无法判断","image_quality":"清晰","confidence":0.8,"needs_human_review":false,"review_reason":null}',
            }, 5

        runtime._call = fake_call
        evidence, usage = runtime.analyze_image(
            b"test-image",
            "image/png",
            {"用户诉求": "耳机右侧外壳破损，申请换货。", "订单商品": "悦声 Air 3 无线耳机"},
        )

        self.assertEqual(payloads[0]["model"], "deepseek-v4-flash-vision-exp")
        self.assertEqual([part["type"] for part in payloads[0]["input"][1]["content"]], ["input_text", "input_image"])
        self.assertIn("订单商品", payloads[0]["input"][1]["content"][0]["text"])
        self.assertTrue(payloads[0]["input"][1]["content"][1]["image_url"].startswith("data:image/png;base64,"))
        self.assertEqual(evidence.evidence_type, "商品与包装")
        self.assertEqual(usage.input_tokens, 12)

    def test_evidence_review_gate_escalates_low_quality_or_order_mismatch(self):
        from app.domain import evidence_review_gate

        model_observation = {
            "damage_type": "明显破损",
            "packaging_status": "包装可见",
            "missing_parts": None,
            "label_match": "与诉求不一致",
            "image_quality": "清晰",
            "confidence": 0.92,
        }
        self.assertEqual(
            evidence_review_gate(model_observation, "耳机右侧破损，申请换货"),
            ["ORDER_OR_COMPLAINT_MISMATCH"],
        )
        self.assertEqual(
            evidence_review_gate({**model_observation, "label_match": "与诉求一致", "image_quality": "模糊", "confidence": 0.3}, "耳机右侧破损，申请换货"),
            ["IMAGE_QUALITY_INSUFFICIENT", "VISION_CONFIDENCE_BELOW_THRESHOLD"],
        )

    def test_real_vision_fixture_is_frozen_and_referenced_by_real_agent_evaluation(self):
        from app.domain import real_evaluation_fixture, real_vision_fixture

        vision = real_vision_fixture()
        self.assertEqual(vision["fixture_set"], "real-vision-eval-v0.2")
        self.assertEqual(len(vision["files"]), 20)
        self.assertEqual(vision["folder_counts"], {
            "明显破损": 5,
            "明显缺件": 4,
            "包装破损状态不确定": 5,
            "模糊遮挡证据不足": 3,
            "与投诉内容不一致": 3,
        })

        evaluation = real_evaluation_fixture()
        image_ids = {item["id"] for item in vision["files"]}
        self.assertEqual(evaluation["fixture_set"], "real-agent-eval-v0.2.2")
        self.assertEqual(len(evaluation["cases"]), 15)
        self.assertEqual([case["id"] for case in evaluation["cases"][:9]], [
            "RAE-001", "RAE-002", "RAE-003", "RAE-004", "RAE-005", "RAE-006", "RAE-007", "RAE-008", "RAE-009",
        ])
        self.assertEqual([case["id"] for case in evaluation["cases"][9:12]], ["HRA-001", "HRA-002", "HRA-003"])
        self.assertEqual([case["id"] for case in evaluation["cases"][12:]], ["HRA-P-001", "HRA-P-002", "HRA-P-003"])
        self.assertTrue(all(case["acceptance"]["proposal_created"] for case in evaluation["cases"][12:]))
        self.assertTrue(all(case["evidence_expectation"]["expected_order_evidence_sufficient"] for case in evaluation["cases"][12:]))
        self.assertTrue(all(
            case["image_fixture_id"] in image_ids
            for case in evaluation["cases"]
            if "image_fixture_id" in case
        ))

    def test_real_vision_validation_is_not_recorded_as_a_fixture_tool(self):
        from app.agent_runtime import ModelUsage, VisionEvidenceOutput
        from app.models import Ticket
        from app.settings import RuntimeSettings
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            db.add(Ticket(
                id="CP-TEST-REAL-EVI",
                title="真实视觉运行记录测试",
                customer="测试用户",
                category="数码",
                scenario="USER_SUBMITTED",
                risk="MEDIUM",
                status="NEW",
                execution_mode="REAL_AGENT_RUN",
            ))
            db.commit()
        finally:
            db.close()

        settings = RuntimeSettings(
            api_key="test-server-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-flash",
            vision_model="deepseek-v4-flash-vision-exp",
            input_usd_per_million=0.44,
            output_usd_per_million=1.32,
        )
        vision = VisionEvidenceOutput(
            evidence_type="商品与包装",
            damage_type="外观破损",
            damage_location="右侧",
            packaging_status="包装破损",
            missing_parts=None,
            label_match="无法判断",
            image_quality="清晰",
            confidence=0.9,
            needs_human_review=True,
            review_reason="需要人工核验",
        )
        image_path = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "evidence-images-v0.1" / "EVI-D-02.png"
        with (
            patch("app.domain.runtime_settings", return_value=settings),
            patch("app.domain.OpenAIResponsesRuntime.analyze_image", return_value=(vision, ModelUsage(10, 5, 0.00001, 6))),
        ):
            response = self.client.post(
                "/api/tickets/CP-TEST-REAL-EVI/evidence-files",
                files={"files": (image_path.name, image_path.read_bytes(), "image/png")},
            )

        self.assertEqual(response.status_code, 201)
        evidence_asset = response.json()["evidence_assets"][0]
        self.assertTrue(evidence_asset["model_needs_human_review"])
        self.assertIn("ORDER_OR_COMPLAINT_MISMATCH", evidence_asset["review_gate_reasons"])
        validation = next(item for item in response.json()["tool_executions"] if item["tool_name"] == "evidence.validate")
        self.assertEqual(validation["caller"], "real-agent")
        self.assertEqual(validation["output_json"], '{"validated": true, "needs_human_review_count": 1}')

    def test_public_policy_search_and_project_review_bundle_keep_simulation_boundary(self):
        response = self.client.get("/api/policy-grounding/search", params={"q": "数码商品激活后能退货吗"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["source_id"] == "PS-SAMR-7DAY" for item in response.json()))

        logistics_response = self.client.get("/api/policy-grounding/search", params={"q": "物流三天没有更新"})
        self.assertEqual(logistics_response.status_code, 200)
        self.assertTrue(any(item["source_id"] == "PS-JD-LOGISTICS-DELAY" for item in logistics_response.json()))

        damage_response = self.client.get("/api/policy-grounding/search", params={"q": "耳机外壳破损申请换货"})
        self.assertEqual(damage_response.status_code, 200)
        self.assertTrue(any(item["chunk_key"] == "jd-general-quality-and-logistics" for item in damage_response.json()))

        bundle = self.client.get("/api/project-review-bundle")
        self.assertEqual(bundle.status_code, 200)
        payload = bundle.json()
        self.assertEqual(payload["bundle_version"], "carepilot-project-review-v0.1")
        self.assertEqual(payload["data_boundary"]["orders"], "SIMULATED_ONLY")
        self.assertEqual(payload["data_boundary"]["refunds_and_payments"], "SIMULATED_ONLY")
        self.assertTrue(any(item["source_id"] == "PS-SAMR-7DAY" for item in payload["policy_grounding"]["sources"]))

    def test_config_activation_requires_sandbox_then_supports_rollback(self):
        configs = self.client.get("/api/agent-configs")
        self.assertEqual(configs.status_code, 200)
        draft = next(item for item in configs.json() if item["status"] == "DRAFT")

        blocked = self.client.post(f"/api/agent-configs/{draft['id']}/activate", json={"reviewer": "ops-admin"})
        self.assertEqual(blocked.status_code, 409)

        sandboxed = self.client.post(f"/api/agent-configs/{draft['id']}/sandbox")
        self.assertEqual(sandboxed.status_code, 200)
        self.assertEqual(sandboxed.json()["sandbox_runs"][0]["status"], "PASSED")

        activated = self.client.post(f"/api/agent-configs/{draft['id']}/activate", json={"reviewer": "ops-admin"})
        self.assertEqual(activated.status_code, 200)
        self.assertEqual(activated.json()["status"], "ACTIVE")
        archived = next(item for item in activated.json()["versions"] if item["version"] == "v1.3")
        self.assertEqual(archived["status"], "ARCHIVED")

        rolled_back = self.client.post(f"/api/agent-configs/{archived['id']}/rollback", json={"reviewer": "ops-admin"})
        self.assertEqual(rolled_back.status_code, 200)
        self.assertEqual(rolled_back.json()["status"], "ACTIVE")
        self.assertIn("config.rolled_back", [event["event_type"] for event in rolled_back.json()["audit_events"]])

    def test_offline_evaluation_is_labeled_and_repeatable(self):
        latest = self.client.get("/api/evaluations/latest")
        self.assertEqual(latest.status_code, 200)
        snapshot = latest.json()
        self.assertEqual(snapshot["execution_mode"], "SIMULATED_OFFLINE")
        self.assertEqual(snapshot["fixture_set"], "synthetic-ticket-set-v0.2")
        self.assertEqual(snapshot["sample_size"], 80)
        self.assertEqual(snapshot["policy_top3_hit_rate"], 100.0)
        self.assertEqual(snapshot["tool_failure_rate"], 0.9)
        self.assertEqual(snapshot["fixture_coverage"], {
            "categories": {"DIGITAL": 32, "APPAREL": 24, "HOME": 24},
            "image_case_count": 36,
            "high_risk_case_count": 20,
            "exception_case_count": 12,
        })
        self.assertIn("不代表线上经营结果", snapshot["source_note"])

        rerun = self.client.post("/api/evaluations/run")
        self.assertEqual(rerun.status_code, 200)
        self.assertGreater(rerun.json()["id"], snapshot["id"])
        self.assertEqual(rerun.json()["fixture_set"], snapshot["fixture_set"])

    def test_frozen_fixture_contracts_cover_all_80_cases(self):
        from app.domain import frozen_evaluation_fixture

        fixture = frozen_evaluation_fixture()
        cases = fixture["cases"]
        self.assertEqual(len(cases), 80)
        self.assertEqual(
            Counter(case["exception_tag"] for case in cases if case["exception_tag"]),
            Counter({"POLICY_CONFLICT": 3, "TOOL_TIMEOUT": 3, "DUPLICATE_REQUEST": 3, "PROMPT_INJECTION": 3}),
        )

    def test_self_authored_query_policy_baseline_measures_top3(self):
        from app.domain import policy_retrieval_snapshot

        snapshot = policy_retrieval_snapshot()
        self.assertEqual(snapshot["fixture_set"], "self-authored-query-policy-v0.1")
        self.assertEqual(snapshot["corpus_set"], "self-authored-policy-corpus-v0.1")
        self.assertEqual(snapshot["query_count"], 60)
        self.assertEqual(snapshot["top3_hit_rate"], 100.0)
        self.assertEqual(snapshot["missed_query_ids"], [])

    def test_manual_agent_tasks_are_paired_and_human_gated(self):
        from app.domain import manual_agent_assignment_fixture, manual_agent_task_fixture

        fixture = manual_agent_task_fixture()
        self.assertEqual(len(fixture["pairs"]), 10)
        self.assertEqual(sum(2 for _ in fixture["pairs"]), 20)
        self.assertEqual(sum(pair["risk"] == "HIGH" for pair in fixture["pairs"]), 3)

        assignment = manual_agent_assignment_fixture()
        self.assertEqual(len(assignment["participant_slots"]), 5)
        self.assertEqual(len(assignment["assignments"]), 20)
        self.assertEqual({item["task_id"] for item in assignment["assignments"]}, {
            task["id"] for pair in fixture["pairs"] for task in (pair["manual_task"], pair["agent_task"])
        })

    def test_customer_efficiency_v1_fixture_and_assignment_are_balanced(self):
        fixtures_dir = Path(__file__).resolve().parents[3] / "evals" / "fixtures"
        task_fixture = json.loads((fixtures_dir / "customer-efficiency-tasks-v1.json").read_text())
        assignment_fixture = json.loads((fixtures_dir / "customer-efficiency-assignment-v1.json").read_text())
        pairs = task_fixture["pairs"]
        assignments = assignment_fixture["assignments"]

        self.assertEqual(task_fixture["fixture_set"], "customer-efficiency-tasks-v1")
        self.assertEqual(len(pairs), 12)
        self.assertEqual(len({pair["pair_id"] for pair in pairs}), 12)
        self.assertEqual(Counter(pair["risk"] for pair in pairs), Counter({"LOW": 4, "MEDIUM": 3, "HIGH": 5}))
        self.assertEqual(sum(pair["eligible_for_safe_automation"] for pair in pairs), 4)
        self.assertTrue(all(pair["requires_human_review"] == (pair["risk"] == "HIGH") for pair in pairs))
        for pair in pairs:
            self.assertTrue(set(pair["required_information_fields"]).issubset(pair["decision_package"]["field_status"]))
            if pair["decision_package"]["missing_information"]:
                self.assertIn("MISSING", pair["decision_package"]["field_status"].values())

        self.assertEqual(len(assignment_fixture["participant_slots"]), 8)
        self.assertEqual(len(assignments), 48)
        self.assertEqual(Counter(item["participant_slot"] for item in assignments), Counter({slot: 6 for slot in assignment_fixture["participant_slots"]}))
        self.assertEqual(Counter((item["pair_id"], item["condition"]) for item in assignments), Counter({
            (pair["pair_id"], condition): 2 for pair in pairs for condition in ("MANUAL", "DECISION_PACKAGE")
        }))

        for slot in assignment_fixture["participant_slots"]:
            slot_assignments = [item for item in assignments if item["participant_slot"] == slot]
            self.assertEqual(Counter(item["condition"] for item in slot_assignments), Counter({"MANUAL": 3, "DECISION_PACKAGE": 3}))
            self.assertEqual(len({item["pair_id"] for item in slot_assignments}), 6)
            self.assertEqual(sorted(item["round"] for item in slot_assignments), [1, 2, 3, 4, 5, 6])
            for item in slot_assignments:
                suffix = "M" if item["condition"] == "MANUAL" else "D"
                self.assertEqual(item["task_id"], f'{item["pair_id"]}-{suffix}')

    def test_public_customer_efficiency_session_balances_and_deduplicates_submissions(self):
        from app.public_efficiency import pair_for_task_id

        participant_id = str(uuid4())
        created = self.client.post("/api/public-efficiency/sessions", json={"participant_id": participant_id})
        self.assertEqual(created.status_code, 200)
        session = created.json()
        self.assertEqual(session["participant_id"], participant_id)
        self.assertEqual(session["study_mode"], "FORMAL")
        self.assertEqual(len(session["tasks"]), 6)
        self.assertEqual(Counter(task["condition"] for task in session["tasks"]), Counter({"MANUAL": 3, "DECISION_PACKAGE": 3}))
        self.assertEqual(len({task["pair_id"] for task in session["tasks"]}), 6)
        self.assertTrue(all("target_outcome" not in task for task in session["tasks"]))

        resumed = self.client.post("/api/public-efficiency/sessions", json={"participant_id": participant_id})
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual([task["task_id"] for task in resumed.json()["tasks"]], [task["task_id"] for task in session["tasks"]])

        for task in session["tasks"]:
            started = self.client.post(f'/api/public-efficiency/tasks/{task["task_id"]}/start', json={"participant_id": participant_id})
            self.assertEqual(started.status_code, 200)
            pair, _ = pair_for_task_id(task["task_id"])
            payload = {
                "participant_id": participant_id,
                "selected_outcome": pair["target_outcome"],
                "source_actions": [task["sources"][0]["id"]],
                "high_risk_gate_observed": pair["requires_human_review"],
                "proposal_outcome": "ADOPTED" if pair["requires_human_review"] and task["condition"] == "DECISION_PACKAGE" else None,
                "active_duration_seconds": 0,
                "ease_rating_1_to_7": 5,
            }
            if task["round"] == 1:
                invalid_duration = self.client.post(f'/api/public-efficiency/tasks/{task["task_id"]}/records', json={
                    **payload,
                    "active_duration_seconds": 999_999,
                })
                self.assertEqual(invalid_duration.status_code, 422)
            submitted = self.client.post(f'/api/public-efficiency/tasks/{task["task_id"]}/records', json=payload)
            self.assertEqual(submitted.status_code, 200)

        self.assertTrue(submitted.json()["experiment_completed"])
        self.assertEqual(len(submitted.json()["completed_task_ids"]), 6)
        duplicate = self.client.post(f'/api/public-efficiency/tasks/{session["tasks"][0]["task_id"]}/records', json={
            "participant_id": participant_id,
            "selected_outcome": "RESOLVED",
            "ease_rating_1_to_7": 5,
        })
        self.assertEqual(duplicate.status_code, 409)

        second_participant = self.client.post("/api/public-efficiency/sessions", json={"participant_id": str(uuid4())})
        self.assertEqual(second_participant.status_code, 200)
        self.assertEqual(Counter(task["condition"] for task in second_participant.json()["tasks"]), Counter({"MANUAL": 3, "DECISION_PACKAGE": 3}))
        self.assertEqual(len({task["pair_id"] for task in second_participant.json()["tasks"]}), 6)

    def test_evidence_fixture_is_self_authored_and_sanitizes_exif(self):
        from PIL import Image
        from app.domain import MAX_EVIDENCE_BYTES, EvidenceUpload, evidence_fixture, sanitize_evidence_upload

        fixture = evidence_fixture()
        self.assertEqual(fixture["fixture_set"], "self-authored-evidence-v0.1")
        self.assertEqual(len(fixture["files"]), 30)
        self.assertIn("不含人物、地址、订单、品牌或第三方素材", fixture["source_note"])

        raw = BytesIO()
        exif = Image.Exif()
        exif[270] = "test-only metadata"
        Image.new("RGB", (12, 12), "navy").save(raw, format="JPEG", exif=exif)
        sanitized = sanitize_evidence_upload(EvidenceUpload("test.jpg", "image/jpeg", raw.getvalue()))
        self.assertTrue(sanitized.exif_removed)
        with Image.open(BytesIO(sanitized.sanitized_content)) as image:
            self.assertEqual(len(image.getexif()), 0)

        from app.database import SessionLocal
        from app.models import Ticket

        db = SessionLocal()
        try:
            db.add(Ticket(
                id="CP-TEST-EVI",
                title="仅用于 Evidence 人工复核测试",
                customer="测试用户",
                category="数码",
                scenario="NEED_EVIDENCE",
                risk="MEDIUM",
                status="NEED_INFO",
            ))
            db.commit()
        finally:
            db.close()
        unassessed = self.client.post(
            "/api/tickets/CP-TEST-EVI/evidence-files",
            files={"files": ("unassessed.jpg", raw.getvalue(), "image/jpeg")},
        )
        self.assertEqual(unassessed.status_code, 201)
        self.assertEqual(unassessed.json()["evidence_assets"][0]["analysis_origin"], "UNASSESSED")
        self.assertTrue(unassessed.json()["evidence_assets"][0]["needs_human_review"])
        blocked = self.client.post("/api/tickets/CP-TEST-EVI/submit-evidence")
        self.assertEqual(blocked.status_code, 409)

        mismatch = self.client.post(
            "/api/tickets/CP-240916/evidence-files",
            files={"files": ("spoofed.png", raw.getvalue(), "image/png")},
        )
        self.assertEqual(mismatch.status_code, 415)

        with self.assertRaises(HTTPException) as too_large:
            sanitize_evidence_upload(EvidenceUpload("large.jpg", "image/jpeg", b"x" * (MAX_EVIDENCE_BYTES + 1)))
        self.assertEqual(too_large.exception.status_code, 413)

        image_path = Path(__file__).resolve().parents[3] / "evals" / "fixtures" / "evidence-images-v0.1" / "EVI-A-11.png"
        content = image_path.read_bytes()
        too_many = self.client.post(
            "/api/tickets/CP-240916/evidence-files",
            files=[("files", (image_path.name, content, "image/png")) for _ in range(5)],
        )
        self.assertEqual(too_many.status_code, 409)

    def test_supabase_settings_without_database_url_fail_closed(self):
        environment = os.environ.copy()
        environment.pop("DATABASE_URL", None)
        environment["CARE_PILOT_ENV_FILE"] = str(Path(__file__).resolve().parent / "missing.env")
        environment["SUPABASE_URL"] = "https://example.supabase.co"
        result = subprocess.run(
            [sys.executable, "-c", "import app.database"],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
