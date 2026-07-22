"""Inspect score adapter for completed physical telemetry audits."""

from __future__ import annotations

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

from sim2claw.physical_telemetry import PhysicalTelemetrySession


@scorer(metrics=[mean()])
def physical_telemetry_audit_score(
    sessions: dict[str, PhysicalTelemetrySession],
) -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        del target
        recording_id = str((state.metadata or {}).get("recording_id", ""))
        session = sessions.get(recording_id)
        receipt = session.terminal_receipt() if session is not None else None
        if not isinstance(receipt, dict):
            return Score(
                value=0.0,
                explanation="No evaluator-owned physical telemetry audit receipt exists.",
            )
        return Score(
            value=1.0 if receipt["audit_complete"] else 0.0,
            explanation="Exact telemetry availability audit; no model judge was used.",
            metadata={
                "recording_id": recording_id,
                "proof_class": receipt["proof_class"],
                "trace_comparison_sha256": receipt["trace_comparison_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
                "physical_actions": 0,
                "physical_transfer_proof": False,
            },
        )

    return score
