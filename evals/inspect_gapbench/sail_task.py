"""Inspect task for governed structural SAIL cases within GapBench."""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import TaskState

from evals.inspect_gapbench.agents import build_agent
from evals.inspect_gapbench.approvers import gapbench_approval_policy
from evals.inspect_gapbench.dataset import PACKAGE_ROOT
from evals.inspect_gapbench.sail_tools import structural_gapbench_bridge
from sim2claw.sail.agent_campaign import StructuralCampaignSession, build_packets, load_campaign_config

REPO_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "sail" / "inspect_campaign_v1.json"


@scorer(metrics=[mean()])
def sealed_sail_score(sessions: dict[str, StructuralCampaignSession]):
    async def score(state: TaskState, target: Target) -> Score:
        del target
        case_id = str((state.metadata or {}).get("case_id", ""))
        session = sessions.get(case_id)
        receipt = session.state.get("terminal") if session is not None else None
        if not isinstance(receipt, dict):
            return Score(value=0.0, explanation="No valid terminal structural submission; failure remains scored.")
        return Score(
            value=float(receipt["aggregate_score"]),
            explanation="Deterministic evaluator-owned structural score; agent prose has no authority.",
            metadata={"receipt_sha256": receipt["receipt_sha256"], "promotion_authority": False},
        )
    return score


@task
def sim2claw_sail_gapbench(harness: str = "codex_cli", config_path: str | None = None) -> Task:
    """Load structural cases without authorizing or making a model call."""
    if harness not in {"codex_cli", "claude_code"}:
        raise ValueError("unsupported harness")
    config = load_campaign_config(Path(config_path) if config_path else DEFAULT_CONFIG)
    packets, sealed = build_packets(config)
    sessions = {case_id: StructuralCampaignSession(packet, sealed[case_id]) for case_id, packet in packets.items()}
    samples = [
        Sample(
            id=f"sail-{harness}-{case_id}",
            input=(
                f"Diagnose structural SAIL case {case_id}. Use only bridged tools, submit ranked "
                "hypotheses with uncertainty, and make exactly one terminal synthetic-only submission."
            ),
            target="Create one evaluator-owned terminal structural score receipt.",
            metadata={"case_id": case_id, "harness": harness, "proof_class": "synthetic_benchmark"},
            sandbox=("docker", str(PACKAGE_ROOT / "compose.yaml")),
        )
        for case_id in config["case_order"]
    ]
    bridge = structural_gapbench_bridge(sessions)
    return Task(
        dataset=MemoryDataset(samples=samples, name="sim2claw-sail-structural-gapbench-v1"),
        solver=build_agent(harness, bridge),
        scorer=sealed_sail_score(sessions),
        approval=gapbench_approval_policy(),
        message_limit=config["budgets"]["message_limit"],
        token_limit=config["budgets"]["token_limit"],
        turn_limit=config["budgets"]["turn_limit"],
        time_limit=config["budgets"]["time_limit_seconds"],
        working_limit=config["budgets"]["working_limit_seconds"],
        cost_limit=config["budgets"]["provider_cost_ceiling_usd"],
        fail_on_error=False,
        metadata={
            "proof_class": "synthetic_benchmark",
            "model_calls_authorized_by_task": False,
            "provider_cost_ceiling_usd": 0.0,
            "physical_authority": False,
            "promotion_authority": False,
        },
    )
