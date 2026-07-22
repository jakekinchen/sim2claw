"""Inspect scorer for evaluator-owned corrective repair receipts."""

from __future__ import annotations

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

from sim2claw.corrective_benchmark import CorrectiveRepairSession


@scorer(metrics=[mean()])
def sealed_corrective_repair_score(sessions: dict[str, CorrectiveRepairSession]) -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        del target
        case_id = str((state.metadata or {}).get("case_id", ""))
        session = sessions.get(case_id)
        receipt = session.terminal_receipt() if session is not None else None
        if not isinstance(receipt, dict):
            return Score(value=0.0, explanation="No evaluator-owned corrective repair receipt exists.")
        return Score(
            value=float(receipt["aggregate_score"]),
            explanation="Deterministic sealed corrective-repair score; no model judge was used.",
            metadata={
                "case_id": case_id,
                "proof_class": receipt["proof_class"],
                "components": receipt["components"],
                "receipt_sha256": receipt["receipt_sha256"],
                "promotion_authority": False,
                "physical_transfer_proof": False,
            },
        )
    return score
