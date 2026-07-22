"""Fail-closed approval policy for corrective-repair tools."""

from __future__ import annotations

import json

from inspect_ai.approval import Approval, ApprovalPolicy, Approver, approver
from inspect_ai.model import ChatMessage
from inspect_ai.tool import ToolCall, ToolCallView

from sim2claw.corrective_benchmark import TOOL_NAMES


@approver(name="corrective_repair_boundary")
def corrective_repair_approver() -> Approver:
    async def approve(message: str, call: ToolCall, view: ToolCallView, history: list[ChatMessage]) -> Approval:
        del message, view, history
        function = call.function.rsplit("__", 1)[-1]
        if function not in TOOL_NAMES:
            return Approval(decision="reject", explanation="Tool is outside the corrective-repair surface.")
        payload = json.dumps(call.arguments, sort_keys=True).lower()
        forbidden = (
            "/var/run/docker.sock",
            "openai_api_key",
            "anthropic_api_key",
            "raw_joint",
            "robot motion",
            "hidden_perturbations",
            "sealed_target",
        )
        if any(token in payload for token in forbidden):
            return Approval(decision="terminate", explanation="Attempted to cross a corrective benchmark authority boundary.")
        return Approval(decision="approve", explanation="Declared corrective-repair tool; the core enforces scope and budgets.")
    return approve


def corrective_repair_approval_policy() -> list[ApprovalPolicy]:
    return [ApprovalPolicy(approver=corrective_repair_approver(), tools="mcp__corrective_repair__")]
