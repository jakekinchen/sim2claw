"""Inspect score adapter for evaluator-owned terminal receipts."""

from __future__ import annotations

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

from sim2claw.gapbench_tools import GapBenchSession


@scorer(metrics=[mean()])
def sealed_gapbench_score(sessions: dict[str, GapBenchSession]) -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        del target
        metadata = state.metadata or {}
        case_id = str(metadata.get("case_id", ""))
        session = sessions.get(case_id)
        if session is None:
            return Score(value=0.0, explanation="No evaluator-owned session matched this sample.")
        receipt = session.terminal_receipt()
        if not isinstance(receipt, dict):
            return Score(value=0.0, explanation="The agent did not create a valid terminal submission.")
        return Score(
            value=float(receipt["aggregate_score"]),
            explanation="Deterministic sealed GapBench score; no model judge was used.",
            metadata={
                "case_id": case_id,
                "proof_class": receipt["proof_class"],
                "scores": receipt["scores"],
                "receipt_sha256": receipt["receipt_sha256"],
                "promotion_authority": False,
            },
        )
    return score
