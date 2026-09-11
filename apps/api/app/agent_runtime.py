import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .settings import RuntimeSettings, runtime_settings


class AgentRuntimeError(RuntimeError):
    pass


class PolicyCitationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=2, max_length=80)
    chunk_key: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=2, max_length=240)


class ResolutionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=2, max_length=80)
    category: str = Field(min_length=2, max_length=40)
    summary: str = Field(min_length=8, max_length=800)
    requested_action: Literal[
        "task.create",
        "ticket.update",
        "customer.notify",
        "need_info",
        "refund.propose",
        "return.propose",
        "replace.propose",
        "compensation.propose",
    ]
    proposed_status: str = Field(pattern="^(NEED_INFO|WAITING_REVIEW|RESOLVED)$")
    rationale: str = Field(min_length=12, max_length=1600)
    customer_message: str = Field(min_length=8, max_length=1200)
    confidence: float = Field(ge=0, le=1)
    policy_citations: list[PolicyCitationOutput] = Field(max_length=5)
    evidence_ids: list[int] = Field(max_length=4)
    missing_information: list[str] = Field(max_length=8)


class VisionEvidenceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_type: str = Field(min_length=2, max_length=48)
    damage_type: str | None = Field(max_length=80)
    damage_location: str | None = Field(max_length=120)
    packaging_status: str | None = Field(max_length=120)
    missing_parts: str | None = Field(max_length=160)
    label_match: str = Field(min_length=2, max_length=32)
    image_quality: str = Field(min_length=2, max_length=32)
    confidence: float = Field(ge=0, le=1)
    needs_human_review: bool
    review_reason: str | None = Field(max_length=120)


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "order_lookup",
        "description": "CarePilot internal tool order.lookup. Query the selected simulated e-commerce order and verify its owner before deciding after-sales handling.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "logistics_track",
        "description": "CarePilot internal tool logistics.track. Query the latest logistics status for an already verified order.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "policy_search",
        "description": "CarePilot internal tool policy.search. Retrieve up to three citations from currently published public after-sales policy snapshots. Use this before proposing any resolution.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {"type": "string"},
            },
            "required": ["query", "category"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "evidence_read",
        "description": "CarePilot internal tool evidence.read. Read already extracted visual evidence for this ticket. Evidence describes visible facts only and never grants refunds or replacements.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "ticket_history",
        "description": "CarePilot internal tool ticket.history. Read prior ticket events when the request may be a repeated or resumed after-sales case.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
            "additionalProperties": False,
        },
    },
]

# Provider function names intentionally use underscores: the OpenAI function-name
# contract is narrower than CarePilot's audit-facing dotted tool identifiers.
PROVIDER_TO_CAREPILOT_TOOL = {
    "order_lookup": "order.lookup",
    "logistics_track": "logistics.track",
    "policy_search": "policy.search",
    "evidence_read": "evidence.read",
    "ticket_history": "ticket.history",
}

MAX_AGENT_TOOL_ROUNDS = 8


RESOLUTION_SCHEMA = ResolutionOutput.model_json_schema()
VISION_SCHEMA = VisionEvidenceOutput.model_json_schema()


class OpenAIResponsesRuntime:
    """Minimal server-side Responses API client for a bounded, auditable agent loop."""

    def __init__(self, settings: RuntimeSettings | None = None):
        self.settings = settings or runtime_settings()
        if not self.settings.api_key:
            raise AgentRuntimeError("REAL_MODEL_NOT_CONFIGURED")

    def _call(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                response = client.post(
                    f"{self.settings.base_url}/responses",
                    headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AgentRuntimeError(f"MODEL_REQUEST_FAILED: {exc.__class__.__name__}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise AgentRuntimeError(f"MODEL_REQUEST_FAILED: HTTP_{response.status_code}")
        body = response.json()
        if body.get("status") not in {None, "completed"}:
            raise AgentRuntimeError(f"MODEL_RESPONSE_{str(body.get('status')).upper()}")
        return body, latency_ms

    def _usage(self, responses: list[dict[str, Any]], latency_ms: int) -> ModelUsage:
        input_tokens = sum(int(response.get("usage", {}).get("input_tokens", 0) or 0) for response in responses)
        output_tokens = sum(int(response.get("usage", {}).get("output_tokens", 0) or 0) for response in responses)
        cost = (
            input_tokens * self.settings.input_usd_per_million / 1_000_000
            + output_tokens * self.settings.output_usd_per_million / 1_000_000
        )
        return ModelUsage(input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=round(cost, 8), latency_ms=latency_ms)

    def _uses_stateless_responses(self) -> bool:
        """DeepSeek's compatible Responses endpoint requires full input history."""
        return "deepseek" in self.settings.base_url.lower()

    @staticmethod
    def _function_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
        return [item for item in response.get("output", []) if item.get("type") == "function_call"]

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        parts: list[str] = []
        for item in response.get("output", []):
            for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    parts.append(content["text"])
        if parts:
            return "\n".join(parts)
        raise AgentRuntimeError("MODEL_EMPTY_STRUCTURED_OUTPUT")

    def run_resolution(
        self,
        ticket_context: dict[str, Any],
        execute_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    ) -> tuple[ResolutionOutput, list[dict[str, Any]], list[dict[str, Any]], ModelUsage]:
        instructions = (
            "You are CarePilot's after-sales resolution agent. Work only from the user request and custom tool outputs. "
            "Before resolving, call order_lookup, logistics_track, and policy_search. If image evidence exists, call evidence_read. "
            "Do not call the same tool again after it has returned successfully unless its arguments materially change. "
            "Never call, promise, or imply direct payment, refund, return, replacement, compensation, or inventory execution. "
            "You may recommend these only as a proposal for human approval. Cite only policy chunks returned by policy.search. "
            "Return the required JSON schema with concise Chinese customer-facing content."
        )
        response_format = {"format": {"type": "json_schema", "name": "carepilot_resolution", "strict": True, "schema": RESOLUTION_SCHEMA}}
        stateless_history = [
            {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(ticket_context, ensure_ascii=False)}]},
        ]
        if self._uses_stateless_responses():
            payload: dict[str, Any] = {
                "model": self.settings.model,
                "input": stateless_history,
                "tools": TOOL_SCHEMAS,
                "tool_choice": "auto",
                "text": response_format,
            }
        else:
            payload = {
                "model": self.settings.model,
                "instructions": instructions,
                "input": json.dumps(ticket_context, ensure_ascii=False),
                "tools": TOOL_SCHEMAS,
                "tool_choice": "auto",
                "text": response_format,
                "store": False,
            }
        responses: list[dict[str, Any]] = []
        tool_trace: list[dict[str, Any]] = []
        policy_evidence: list[dict[str, Any]] = []
        elapsed_ms = 0
        response, call_ms = self._call(payload)
        responses.append(response)
        elapsed_ms += call_ms
        for _ in range(MAX_AGENT_TOOL_ROUNDS):
            calls = self._function_calls(response)
            if not calls:
                break
            tool_outputs = []
            for call in calls:
                provider_name = str(call.get("name", ""))
                name = PROVIDER_TO_CAREPILOT_TOOL.get(provider_name, provider_name)
                try:
                    arguments = json.loads(str(call.get("arguments", "{}")))
                    if not isinstance(arguments, dict):
                        raise ValueError("arguments must be an object")
                    output = execute_tool(name, arguments)
                    outcome = "SUCCEEDED"
                except Exception as exc:  # The model receives a bounded tool error, never a stack trace.
                    arguments = {"raw": str(call.get("arguments", ""))}
                    output = {"error": "TOOL_EXECUTION_FAILED", "detail": exc.__class__.__name__}
                    outcome = "FAILED"
                tool_trace.append({"name": name, "arguments": arguments, "output": output, "outcome": outcome})
                if name == "policy.search" and outcome == "SUCCEEDED":
                    policy_evidence.extend(output.get("citations", []))
                call_id = call.get("call_id")
                tool_outputs.append({"type": "function_call_output", "call_id": call_id, "output": json.dumps(output, ensure_ascii=False)})
                if self._uses_stateless_responses():
                    stateless_history.append({
                        "type": "function_call",
                        "call_id": call_id,
                        "name": provider_name,
                        "arguments": str(call.get("arguments", "{}")),
                    })
            if self._uses_stateless_responses():
                stateless_history.extend(tool_outputs)
                follow_up = {
                    "model": self.settings.model,
                    "input": stateless_history,
                    "tools": TOOL_SCHEMAS,
                    "tool_choice": "auto",
                    "text": response_format,
                }
            else:
                follow_up = {
                    "model": self.settings.model,
                    "previous_response_id": response.get("id"),
                    "input": tool_outputs,
                    "tools": TOOL_SCHEMAS,
                    "text": response_format,
                    "store": False,
                }
            response, call_ms = self._call(follow_up)
            responses.append(response)
            elapsed_ms += call_ms
        else:
            raise AgentRuntimeError("TOOL_CALL_LIMIT_REACHED")

        output = ResolutionOutput.model_validate_json(self._output_text(response))
        return output, tool_trace, policy_evidence, self._usage(responses, elapsed_ms)

    def analyze_image(
        self,
        sanitized_content: bytes,
        content_type: str,
        visual_context: dict[str, str | None] | None = None,
    ) -> tuple[VisionEvidenceOutput, ModelUsage]:
        image_url = f"data:{content_type};base64,{base64.b64encode(sanitized_content).decode('ascii')}"
        instructions = (
            "Extract only visible after-sales evidence from this image. Do not determine eligibility, fraud, refunds, replacements, "
            "or compensation. If image quality is poor, unrelated, ambiguous, or insufficient, set needs_human_review true. "
            "Use the complaint and order title only to assess label_match; all other fields must describe visible facts. "
            "Use concise Chinese values: 明显破损、明确缺件、包装破损、无法判断、清晰、模糊、遮挡、与诉求一致、与诉求不一致."
        )
        context_text = "提取售后图片的可见 Evidence。"
        if visual_context:
            context_text = json.dumps({"任务": "提取售后图片的可见 Evidence", **visual_context}, ensure_ascii=False)
        payload: dict[str, Any] = {
            "model": self.settings.vision_model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": context_text}, {"type": "input_image", "image_url": image_url, "detail": "high"}]}],
            "text": {"format": {"type": "json_schema", "name": "carepilot_evidence", "strict": True, "schema": VISION_SCHEMA}},
        }
        if self._uses_stateless_responses():
            payload["input"].insert(0, {"role": "system", "content": [{"type": "input_text", "text": instructions}]})
        else:
            payload["instructions"] = instructions
            payload["store"] = False
        response, latency_ms = self._call(payload)
        output = VisionEvidenceOutput.model_validate_json(self._output_text(response))
        return output, self._usage([response], latency_ms)
