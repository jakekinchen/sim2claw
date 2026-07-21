"""Inspect task for retrospective physical telemetry evidence auditing."""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample

from evals.inspect_gapbench.telemetry_approvers import (
    physical_telemetry_approval_policy,
)
from evals.inspect_gapbench.telemetry_agents import build_telemetry_agent
from evals.inspect_gapbench.telemetry_dataset import (
    PACKAGE_ROOT,
    REPO_ROOT,
    build_telemetry_sessions,
    prompt_for_telemetry_episode,
    telemetry_bindings,
    telemetry_sample_files,
)
from evals.inspect_gapbench.telemetry_scorers import physical_telemetry_audit_score
from evals.inspect_gapbench.telemetry_tools import physical_telemetry_bridge


@task
def sim2claw_physical_telemetry_audit(
    harness: str = "codex_cli",
    enforce_cost_limit: bool = True,
) -> Task:
    """Construct the 18-episode task without a provider call or physical action."""

    build_root = REPO_ROOT / ".inspect_ai" / "physical_telemetry" / harness
    sessions, corpus = build_telemetry_sessions(harness, build_root)
    samples = [
        Sample(
            id=f"physical-telemetry-{harness}-{recording_id}",
            input=prompt_for_telemetry_episode(recording_id),
            target="Create one exact evaluator-owned telemetry audit receipt.",
            metadata={
                "recording_id": recording_id,
                "harness": harness,
                "proof_class": "retrospective_physical_teleoperation_observation",
                "bindings": telemetry_bindings(recording_id, session),
            },
            sandbox=("docker", str(PACKAGE_ROOT / "compose.yaml")),
            files=telemetry_sample_files(session, build_root),
            setup="chown -R agent:agent /workspace",
        )
        for recording_id, session in sorted(sessions.items())
    ]
    bridge = physical_telemetry_bridge(sessions)
    return Task(
        dataset=MemoryDataset(
            samples=samples,
            name="sim2claw-physical-telemetry-eighteen-episode-v1",
        ),
        solver=build_telemetry_agent(harness, bridge),
        scorer=physical_telemetry_audit_score(sessions),
        approval=physical_telemetry_approval_policy(),
        message_limit=40,
        token_limit=60_000,
        turn_limit=24,
        time_limit=900,
        working_limit=750,
        cost_limit=10.0 if enforce_cost_limit else None,
        fail_on_error=False,
        metadata={
            "proof_class": "retrospective_physical_teleoperation_observation",
            "model_calls_authorized_by_task": False,
            "physical_actions": 0,
            "physical_authority": False,
            "promotion_authority": False,
            "episode_count": corpus["episode_count"],
            "sample_count": corpus["sample_count"],
            "corpus_comparison_sha256": corpus["corpus_comparison_sha256"],
        },
    )
