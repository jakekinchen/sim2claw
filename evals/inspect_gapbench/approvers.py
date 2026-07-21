"""Fail-closed approval policy for bridged GapBench tools."""

from __future__ import annotations

import json

from inspect_ai.approval import Approval, ApprovalPolicy, Approver, approver
from inspect_ai.model import ChatMessage
from inspect_ai.tool import ToolCall, ToolCallView

from sim2claw.gapbench_tools import TOOL_NAMES


@approver(name="gapbench_boundary")
def gapbench_approver() -> Approver:
    async def approve(
        message: str,
        call: ToolCall,
        view: ToolCallView,
        history: list[ChatMessage],
    ) -> Approval:
        del message, view, history
        function = call.function.rsplit("__", 1)[-1]
        if function not in TOOL_NAMES:
            return Approval(decision="reject", explanation="Tool is outside the six-tool GapBench surface.")
        payload = json.dumps(call.arguments, sort_keys=True).lower()
        terminal_tokens = ("/var/run/docker.sock", "openai_api_key", "anthropic_api_key", "robot motion", "hidden_rows")
        if any(token in payload for token in terminal_tokens):
            return Approval(decision="terminate", explanation="Attempted to cross a benchmark authority boundary.")
        return Approval(decision="approve", explanation="Declared GapBench tool; core contract enforces budgets and scope.")
    return approve


def gapbench_approval_policy() -> list[ApprovalPolicy]:
    return [ApprovalPolicy(approver=gapbench_approver(), tools="mcp__gapbench__")]
