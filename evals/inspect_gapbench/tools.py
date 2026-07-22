"""Inspect host-tool wrappers around the six GapBench contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from inspect_ai.agent import BridgedToolsSpec
from inspect_ai.tool import Tool, tool
from inspect_ai.util import sandbox

from sim2claw.gapbench_contracts import GapBenchContractError
from sim2claw.gapbench_tools import GapBenchSession
from sim2claw.learning_factory_artifacts import atomic_write_json


def _session(sessions: dict[str, GapBenchSession], case_id: str) -> GapBenchSession:
    try:
        return sessions[case_id]
    except KeyError as error:
        raise GapBenchContractError("case_id is not active in this task") from error


async def _sync_candidate(session: GapBenchSession, candidate_ref: str) -> None:
    relative = Path(candidate_ref)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "candidate":
        raise GapBenchContractError("candidate_ref must remain inside candidate/")
    raw = await sandbox().read_file(relative.as_posix())
    if not isinstance(raw, str):
        raise GapBenchContractError("candidate must be UTF-8 JSON")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise GapBenchContractError("candidate is not valid JSON") from error
    if not isinstance(value, dict):
        raise GapBenchContractError("candidate JSON must contain an object")
    atomic_write_json(session.packet_root / relative, value)


def inspect_tools(sessions: dict[str, GapBenchSession]) -> list[Tool]:
    @tool(name="case_status")
    def case_status_tool() -> Tool:
        async def execute(case_id: str) -> str:
            """Return frozen case identity, evidence, budgets, and allowed actions.

            Args:
                case_id: Exact active case identifier from the task prompt.
            """
            return json.dumps(_session(sessions, case_id).case_status(case_id), sort_keys=True)
        return execute

    @tool(name="read_evidence")
    def read_evidence_tool() -> Tool:
        async def execute(case_id: str, artifact_id: str, start: int = 0, limit: int = 100) -> str:
            """Read a bounded slice of one artifact in the public evidence manifest.

            Args:
                case_id: Exact active case identifier.
                artifact_id: Public artifact identifier returned by case_status.
                start: Zero-based row offset for list evidence.
                limit: Maximum number of rows to return, up to 200.
            """
            result = _session(sessions, case_id).read_evidence(case_id, artifact_id, start, limit)
            return json.dumps(result, sort_keys=True)
        return execute

    @tool(name="submit_hypotheses")
    def submit_hypotheses_tool() -> Tool:
        async def execute(case_id: str, hypotheses: list[dict[str, Any]]) -> str:
            """Submit an ordered causal ledger with evidence and predictions.

            Args:
                case_id: Exact active case identifier.
                hypotheses: Ranked typed hypothesis objects with contiguous ranks.
            """
            result = _session(sessions, case_id).submit_hypotheses(case_id, hypotheses)
            return json.dumps(result, sort_keys=True)
        return execute

    @tool(name="request_probe")
    def request_probe_tool() -> Tool:
        async def execute(case_id: str, probe_id: str) -> str:
            """Run one declared simulated or read-only probe and charge its budget.

            Args:
                case_id: Exact active case identifier.
                probe_id: Declared probe identifier returned by case_status.
            """
            result = _session(sessions, case_id).request_probe(case_id, probe_id)
            return json.dumps(result, sort_keys=True)
        return execute

    @tool(name="run_public_evaluation")
    def run_public_evaluation_tool() -> Tool:
        async def execute(case_id: str, candidate_ref: str) -> str:
            """Evaluate a bounded candidate on visible development rows.

            Args:
                case_id: Exact active case identifier.
                candidate_ref: Relative JSON path below candidate/ in the sandbox.
            """
            session = _session(sessions, case_id)
            await _sync_candidate(session, candidate_ref)
            result = session.run_public_evaluation(case_id, candidate_ref)
            return json.dumps(result, sort_keys=True)
        return execute

    @tool(name="submit_candidate")
    def submit_candidate_tool() -> Tool:
        async def execute(
            case_id: str,
            candidate_ref: str,
            prediction: dict[str, Any],
            claim_boundary: str,
        ) -> str:
            """Freeze one terminal candidate and return its sealed score receipt.

            Args:
                case_id: Exact active case identifier.
                candidate_ref: Relative JSON path below candidate/ in the sandbox.
                prediction: Fault family, uncertainty, and held-out consequence prediction.
                claim_boundary: Must be exactly synthetic_only.
            """
            session = _session(sessions, case_id)
            await _sync_candidate(session, candidate_ref)
            result = session.submit_candidate(case_id, candidate_ref, prediction, claim_boundary)
            return json.dumps(result, sort_keys=True)
        return execute

    return [
        case_status_tool(),
        read_evidence_tool(),
        submit_hypotheses_tool(),
        request_probe_tool(),
        run_public_evaluation_tool(),
        submit_candidate_tool(),
    ]


def gapbench_bridge(sessions: dict[str, GapBenchSession]) -> BridgedToolsSpec:
    return BridgedToolsSpec(name="gapbench", tools=inspect_tools(sessions))
