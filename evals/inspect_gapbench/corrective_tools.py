"""Inspect wrappers for the corrective-repair benchmark tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from inspect_ai.agent import BridgedToolsSpec
from inspect_ai.tool import Tool, tool
from inspect_ai.util import sandbox

from sim2claw.corrective_benchmark import CorrectiveBenchmarkError, CorrectiveRepairSession
from sim2claw.learning_factory_artifacts import atomic_write_json, load_json_object


def _session(sessions: dict[str, CorrectiveRepairSession], case_id: str) -> CorrectiveRepairSession:
    try:
        return sessions[case_id]
    except KeyError as error:
        raise CorrectiveBenchmarkError("case_id is not active in this corrective repair task") from error


async def _sync_proposal(session: CorrectiveRepairSession, candidate_ref: str) -> dict[str, Any]:
    relative = Path(candidate_ref)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.parts[0] != "candidate":
        raise CorrectiveBenchmarkError("candidate_ref must remain inside candidate/")
    raw = await sandbox().read_file(relative.as_posix())
    if not isinstance(raw, str):
        raise CorrectiveBenchmarkError("corrective proposal must be UTF-8 JSON")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CorrectiveBenchmarkError("corrective proposal is not valid JSON") from error
    if not isinstance(value, dict):
        raise CorrectiveBenchmarkError("corrective proposal JSON must contain an object")
    atomic_write_json(session.packet_root / relative, value)
    return load_json_object(session.packet_root / relative, label="corrective repair proposal")


def corrective_inspect_tools(sessions: dict[str, CorrectiveRepairSession]) -> list[Tool]:
    @tool(name="repair_status")
    def repair_status_tool() -> Tool:
        async def execute(case_id: str) -> str:
            """Return frozen repair identity, evidence, budgets, and authority.

            Args:
                case_id: Exact active corrective repair case identifier.
            """
            return json.dumps(_session(sessions, case_id).repair_status(case_id), sort_keys=True)
        return execute

    @tool(name="read_repair_evidence")
    def read_repair_evidence_tool() -> Tool:
        async def execute(case_id: str, artifact_id: str, start: int = 0, limit: int = 100) -> str:
            """Read a bounded public corrective-repair evidence artifact.

            Args:
                case_id: Exact active case identifier.
                artifact_id: Artifact identifier returned by repair_status.
                start: Zero-based list row offset.
                limit: Maximum rows to return, up to 200.
            """
            value = _session(sessions, case_id).read_repair_evidence(case_id, artifact_id, start, limit)
            return json.dumps(value, sort_keys=True)
        return execute

    @tool(name="submit_repair_hypothesis")
    def submit_repair_hypothesis_tool() -> Tool:
        async def execute(case_id: str, hypothesis: dict[str, Any]) -> str:
            """Submit one evidence-bound pregrasp-centering hypothesis.

            Args:
                case_id: Exact active case identifier.
                hypothesis: Mechanism, evidence IDs, predicted translation, and confidence.
            """
            value = _session(sessions, case_id).submit_repair_hypothesis(case_id, hypothesis)
            return json.dumps(value, sort_keys=True)
        return execute

    @tool(name="request_repair_probe")
    def request_repair_probe_tool() -> Tool:
        async def execute(case_id: str, probe_id: str) -> str:
            """Run one declared simulated or read-only corrective probe.

            Args:
                case_id: Exact active case identifier.
                probe_id: Declared probe identifier returned by repair_status.
            """
            value = _session(sessions, case_id).request_repair_probe(case_id, probe_id)
            return json.dumps(value, sort_keys=True)
        return execute

    @tool(name="run_public_repair_evaluation")
    def run_public_repair_evaluation_tool() -> Tool:
        async def execute(case_id: str, candidate_ref: str) -> str:
            """Evaluate one typed proposal on visible development perturbations.

            Args:
                case_id: Exact active case identifier.
                candidate_ref: Relative JSON path below candidate/.
            """
            session = _session(sessions, case_id)
            proposal = await _sync_proposal(session, candidate_ref)
            value = session.run_public_repair_evaluation(case_id, proposal)
            return json.dumps(value, sort_keys=True)
        return execute

    @tool(name="submit_repair")
    def submit_repair_tool() -> Tool:
        async def execute(case_id: str, candidate_ref: str, claim_boundary: str) -> str:
            """Create the single evaluator-owned sealed repair receipt.

            Args:
                case_id: Exact active case identifier.
                candidate_ref: Relative JSON path below candidate/.
                claim_boundary: Must be exactly synthetic_benchmark_only.
            """
            session = _session(sessions, case_id)
            proposal = await _sync_proposal(session, candidate_ref)
            value = session.submit_repair(case_id, proposal, claim_boundary)
            return json.dumps(value, sort_keys=True)
        return execute

    return [
        repair_status_tool(),
        read_repair_evidence_tool(),
        submit_repair_hypothesis_tool(),
        request_repair_probe_tool(),
        run_public_repair_evaluation_tool(),
        submit_repair_tool(),
    ]


def corrective_repair_bridge(sessions: dict[str, CorrectiveRepairSession]) -> BridgedToolsSpec:
    return BridgedToolsSpec(name="corrective_repair", tools=corrective_inspect_tools(sessions))
