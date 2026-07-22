"""Inspect task for bounded corrective-repair reasoning."""

from __future__ import annotations

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample

from evals.inspect_gapbench.agents import build_corrective_agent
from evals.inspect_gapbench.corrective_approvers import corrective_repair_approval_policy
from evals.inspect_gapbench.corrective_dataset import (
    PACKAGE_ROOT,
    build_corrective_sessions,
    corrective_bindings,
    corrective_sample_files,
    prompt_for_corrective_case,
)
from evals.inspect_gapbench.corrective_scorers import sealed_corrective_repair_score
from evals.inspect_gapbench.corrective_tools import corrective_repair_bridge


@task
def sim2claw_corrective_repair(harness: str = "codex_cli", enforce_cost_limit: bool = True) -> Task:
    """Construct the four-case task without making a provider-backed call."""

    sessions = build_corrective_sessions(harness)
    samples = [
        Sample(
            id=f"corrective-{harness}-{case_id}",
            input=prompt_for_corrective_case(case_id),
            target="Create one evaluator-owned terminal corrective-repair receipt.",
            metadata={
                "case_id": case_id,
                "harness": harness,
                "proof_class": "synthetic_benchmark",
                "bindings": corrective_bindings(case_id),
            },
            sandbox=("docker", str(PACKAGE_ROOT / "compose.yaml")),
            files=corrective_sample_files(session),
            setup="mkdir -p candidate && cp candidate/baseline.json candidate/proposal.json && chown -R agent:agent /workspace",
        )
        for case_id, session in sorted(sessions.items())
    ]
    bridge = corrective_repair_bridge(sessions)
    return Task(
        dataset=MemoryDataset(samples=samples, name="sim2claw-corrective-repair-four-case-v1"),
        solver=build_corrective_agent(harness, bridge),
        scorer=sealed_corrective_repair_score(sessions),
        approval=corrective_repair_approval_policy(),
        message_limit=60,
        token_limit=80_000,
        turn_limit=30,
        time_limit=1_200,
        working_limit=1_000,
        cost_limit=20.0 if enforce_cost_limit else None,
        fail_on_error=False,
        metadata={
            "proof_class": "synthetic_benchmark",
            "model_calls_authorized_by_task": False,
            "physical_authority": False,
            "promotion_authority": False,
            "case_count": len(samples),
        },
    )
