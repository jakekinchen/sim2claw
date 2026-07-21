"""Semantically matched Inspect SWE agent adapters."""

from __future__ import annotations

from pathlib import Path

from inspect_ai.agent import Agent, BridgedToolsSpec
from inspect_swe import claude_code, codex_cli


PACKAGE_ROOT = Path(__file__).resolve().parent
SKILL_ROOT = PACKAGE_ROOT / "skills"
SKILL_NAMES = (
    "freeze-case",
    "localize-gap",
    "design-probe",
    "implement-repair",
    "submit-evidence",
)
CORRECTIVE_SKILL_ROOT = PACKAGE_ROOT / "corrective_skills"
CORRECTIVE_SKILL_NAMES = (
    "freeze-repair-case",
    "estimate-correction",
    "design-repair-probe",
    "evaluate-bounded-repair",
    "submit-repair-evidence",
)


def skill_paths() -> list[Path]:
    return [SKILL_ROOT / name for name in SKILL_NAMES]


def corrective_skill_paths() -> list[Path]:
    return [CORRECTIVE_SKILL_ROOT / name for name in CORRECTIVE_SKILL_NAMES]


def build_agent(harness: str, bridge: BridgedToolsSpec) -> Agent:
    shared = {
        "skills": skill_paths(),
        "bridged_tools": [bridge],
        "cwd": "/workspace",
        "sandbox": "default",
        "user": "agent",
        "version": "sandbox",
        "attempts": 1,
        "env": {
            "SIM2CLAW_PROOF_CLASS": "synthetic_benchmark",
            "SIM2CLAW_PHYSICAL_AUTHORITY": "false",
        },
    }
    if harness == "codex_cli":
        return codex_cli(
            name="gapbench_codex_cli",
            web_search="disabled",
            goals=False,
            home_dir="/home/agent/.codex",
            **shared,
        )
    if harness == "claude_code":
        return claude_code(
            name="gapbench_claude_code",
            disallowed_tools=["WebSearch", "WebFetch"],
            **shared,
        )
    raise ValueError(f"unsupported harness: {harness}")


def build_corrective_agent(harness: str, bridge: BridgedToolsSpec) -> Agent:
    """Build semantically matched adapters for the corrective repair task."""

    shared = {
        "skills": corrective_skill_paths(),
        "bridged_tools": [bridge],
        "cwd": "/workspace",
        "sandbox": "default",
        "user": "agent",
        "version": "sandbox",
        "attempts": 1,
        "env": {
            "SIM2CLAW_PROOF_CLASS": "synthetic_benchmark",
            "SIM2CLAW_PHYSICAL_AUTHORITY": "false",
        },
    }
    if harness == "codex_cli":
        return codex_cli(
            name="corrective_repair_codex_cli",
            web_search="disabled",
            goals=False,
            home_dir="/home/agent/.codex",
            **shared,
        )
    if harness == "claude_code":
        return claude_code(
            name="corrective_repair_claude_code",
            disallowed_tools=["WebSearch", "WebFetch"],
            **shared,
        )
    raise ValueError(f"unsupported harness: {harness}")
