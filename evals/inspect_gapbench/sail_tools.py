"""Inspect wrappers for the structural SAIL session in GapBench."""

from __future__ import annotations

import json
from typing import Any

from inspect_ai.agent import BridgedToolsSpec
from inspect_ai.tool import Tool, tool

from sim2claw.sail.agent_campaign import StructuralCampaignSession


def structural_inspect_tools(sessions: dict[str, StructuralCampaignSession]) -> list[Tool]:
    def session(case_id: str) -> StructuralCampaignSession:
        if case_id not in sessions:
            raise ValueError("case_id is not active")
        return sessions[case_id]

    @tool(name="case_status")
    def case_status() -> Tool:
        async def execute(case_id: str) -> str:
            """Return the frozen structural case status and remaining budgets."""
            return json.dumps(session(case_id).status(), sort_keys=True)
        return execute

    @tool(name="read_evidence")
    def read_evidence() -> Tool:
        async def execute(case_id: str, start: int = 0, limit: int = 100) -> str:
            """Read one bounded slice of public evidence."""
            return json.dumps(session(case_id).read_evidence(start, limit), sort_keys=True)
        return execute

    @tool(name="inspect_residuals")
    def inspect_residuals() -> Tool:
        async def execute(case_id: str) -> str:
            """Inspect the public phase-aware residual summary."""
            return json.dumps(session(case_id).inspect_residuals(), sort_keys=True)
        return execute

    @tool(name="inspect_belief_graph")
    def inspect_belief_graph() -> Tool:
        async def execute(case_id: str) -> str:
            """Inspect candidate mechanism nodes and unresolved graph edges."""
            return json.dumps(session(case_id).inspect_belief_graph(), sort_keys=True)
        return execute

    @tool(name="submit_hypotheses")
    def submit_hypotheses() -> Tool:
        async def execute(case_id: str, hypotheses: list[dict[str, Any]]) -> str:
            """Submit ranked typed hypotheses including uncertainty."""
            return json.dumps(session(case_id).submit_hypotheses(hypotheses), sort_keys=True)
        return execute

    @tool(name="request_probe")
    def request_probe() -> Tool:
        async def execute(case_id: str, probe_id: str) -> str:
            """Request one declared simulator-only structural probe."""
            return json.dumps(session(case_id).request_probe(probe_id), sort_keys=True)
        return execute

    @tool(name="run_public_evaluation")
    def run_public_evaluation() -> Tool:
        async def execute(case_id: str, parameter: float) -> str:
            """Evaluate one bounded parameter on public rows."""
            return json.dumps(session(case_id).public_evaluate(parameter), sort_keys=True)
        return execute

    @tool(name="submit_candidate")
    def submit_candidate() -> Tool:
        async def execute(case_id: str, family: str, parameter: float, uncertainty: float, claim_boundary: str) -> str:
            """Make the one terminal structured candidate submission."""
            return json.dumps(session(case_id).submit_candidate(family=family, parameter=parameter, uncertainty=uncertainty, claim_boundary=claim_boundary), sort_keys=True)
        return execute

    return [case_status(), read_evidence(), inspect_residuals(), inspect_belief_graph(), submit_hypotheses(), request_probe(), run_public_evaluation(), submit_candidate()]


def structural_gapbench_bridge(sessions: dict[str, StructuralCampaignSession]) -> BridgedToolsSpec:
    return BridgedToolsSpec(name="sail_gapbench", tools=structural_inspect_tools(sessions))
