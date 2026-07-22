"""Inspect AI task entrypoint for Sim2Claw GapBench."""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample

from evals.inspect_gapbench.agents import build_agent
from evals.inspect_gapbench.approvers import gapbench_approval_policy
from evals.inspect_gapbench.dataset import PACKAGE_ROOT, build_sessions, prompt_for_case, sample_files, skill_bundle_digest
from evals.inspect_gapbench.scorers import sealed_gapbench_score
from evals.inspect_gapbench.tools import gapbench_bridge


@task
def sim2claw_gapbench(
    harness: str = "codex_cli",
    enforce_cost_limit: bool = True,
    sealed_source: str | None = None,
) -> Task:
    """Construct the six-case task without making a provider-backed model call."""

    sessions = build_sessions(
        harness,
        sealed_source=Path(sealed_source) if sealed_source else None,
    )
    samples = [
        Sample(
            id=f"{harness}-{case_id}",
            input=prompt_for_case(case_id),
            target="Create one evaluator-owned terminal score receipt.",
            metadata={"case_id": case_id, "harness": harness, "proof_class": "synthetic_benchmark"},
            sandbox=("docker", str(PACKAGE_ROOT / "compose.yaml")),
            files=sample_files(session),
            setup="mkdir -p candidate && cp candidate/baseline.json candidate/proposal.json && chown -R agent:agent /workspace",
        )
        for case_id, session in sorted(sessions.items())
    ]
    bridge = gapbench_bridge(sessions)
    return Task(
        dataset=MemoryDataset(samples=samples, name="sim2claw-gapbench-six-case-v1"),
        solver=build_agent(harness, bridge),
        scorer=sealed_gapbench_score(sessions),
        approval=gapbench_approval_policy(),
        message_limit=80,
        token_limit=120_000,
        turn_limit=40,
        time_limit=1_800,
        working_limit=1_500,
        cost_limit=25.0 if enforce_cost_limit else None,
        fail_on_error=False,
        metadata={
            "proof_class": "synthetic_benchmark",
            "model_calls_authorized_by_task": False,
            "physical_authority": False,
            "promotion_authority": False,
            "skill_bundle_sha256": skill_bundle_digest(),
        },
    )
