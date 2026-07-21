"""Inspect task for fixed-data multimodal interaction-event auditing."""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample

from evals.inspect_gapbench.event_agents import build_event_agent
from evals.inspect_gapbench.event_approvers import interaction_event_approval_policy
from evals.inspect_gapbench.event_dataset import (
    PACKAGE_ROOT,
    REPO_ROOT,
    build_event_sessions,
    event_bindings,
    event_sample_files,
    prompt_for_event_episode,
)
from evals.inspect_gapbench.event_scorers import interaction_event_audit_score
from evals.inspect_gapbench.event_tools import interaction_event_bridge


@task
def sim2claw_interaction_event_audit(
    harness: str = "codex_cli",
    partition: str = "train",
    evaluator_owned: bool = False,
    enforce_cost_limit: bool = True,
) -> Task:
    """Build the fixed-data annotation task without invoking a provider."""

    if partition != "train" and not evaluator_owned:
        raise ValueError("held-out interaction events require evaluator_owned=True")
    build_root = (
        REPO_ROOT / ".inspect_ai" / "interaction_events" / partition / harness
    )
    sessions, corpus = build_event_sessions(
        harness,
        partition=partition,
        evaluator_owned=evaluator_owned,
        build_root=build_root,
    )
    samples = [
        Sample(
            id=f"interaction-event-{partition}-{harness}-{recording_id}",
            input=prompt_for_event_episode(recording_id),
            target="Submit one bounded visual annotation and exact audit receipt.",
            metadata={
                "recording_id": recording_id,
                "partition": partition,
                "harness": harness,
                "proof_class": "retrospective_physical_multimodal_derived_candidates",
                "bindings": event_bindings(recording_id, session),
            },
            sandbox=("docker", str(PACKAGE_ROOT / "compose.yaml")),
            files=event_sample_files(session, build_root),
            setup="chown -R agent:agent /workspace",
        )
        for recording_id, session in sorted(sessions.items())
    ]
    bridge = interaction_event_bridge(sessions)
    return Task(
        dataset=MemoryDataset(
            samples=samples,
            name=f"sim2claw-interaction-events-{partition}-v1",
        ),
        solver=build_event_agent(harness, bridge),
        scorer=interaction_event_audit_score(sessions),
        approval=interaction_event_approval_policy(),
        message_limit=32,
        token_limit=48_000,
        turn_limit=18,
        time_limit=750,
        working_limit=600,
        cost_limit=6.0 if enforce_cost_limit else None,
        fail_on_error=False,
        metadata={
            "proof_class": "retrospective_physical_multimodal_derived_candidates",
            "partition": partition,
            "evaluator_owned": evaluator_owned,
            "model_calls_authorized_by_task": False,
            "annotation_correctness_scored": False,
            "physical_actions": 0,
            "physical_authority": False,
            "promotion_authority": False,
            "episode_count": corpus["episode_count"],
            "sample_count": corpus["sample_count"],
            "corpus_sha256": corpus["corpus_sha256"],
        },
    )
