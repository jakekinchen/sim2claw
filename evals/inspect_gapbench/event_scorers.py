"""Deterministic completeness scorer for interaction-event audits."""

from __future__ import annotations

from inspect_ai.scorer import Score, Scorer, Target, mean, scorer
from inspect_ai.solver import TaskState

from sim2claw.interaction_events import InteractionEventSession


@scorer(metrics=[mean()])
def interaction_event_audit_score(
    sessions: dict[str, InteractionEventSession],
) -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        del target
        recording_id = str((state.metadata or {}).get("recording_id", ""))
        session = sessions.get(recording_id)
        receipt = session.terminal_receipt() if session is not None else None
        if not isinstance(receipt, dict):
            return Score(
                value=0.0,
                explanation="No evaluator-owned interaction-event audit receipt exists.",
            )
        return Score(
            value=1.0 if receipt["audit_complete"] else 0.0,
            explanation=(
                "Schema and evidence-boundary completeness only; visual annotation "
                "correctness was not scored and no model judge was used."
            ),
            metadata={
                "recording_id": recording_id,
                "partition": receipt["partition"],
                "event_episode_sha256": receipt["event_episode_sha256"],
                "annotation_sha256": receipt["annotation_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
                "annotation_correctness_scored": False,
                "measured_contact_claimed": False,
                "physical_actions": 0,
            },
        )

    return score
