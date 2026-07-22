"""Read-only Inspect SWE adapters for physical telemetry audits."""

from __future__ import annotations

from pathlib import Path

from inspect_ai.agent import Agent, BridgedToolsSpec
from inspect_swe import claude_code, codex_cli


PACKAGE_ROOT = Path(__file__).resolve().parent
TELEMETRY_SKILL_ROOT = PACKAGE_ROOT / "telemetry_skills"
TELEMETRY_SKILL_NAMES = ("audit-physical-telemetry",)


def telemetry_skill_paths() -> list[Path]:
    return [TELEMETRY_SKILL_ROOT / name for name in TELEMETRY_SKILL_NAMES]


def build_telemetry_agent(harness: str, bridge: BridgedToolsSpec) -> Agent:
    """Build semantically matched, read-only telemetry audit adapters."""

    shared = {
        "skills": telemetry_skill_paths(),
        "bridged_tools": [bridge],
        "cwd": "/workspace",
        "sandbox": "default",
        "user": "agent",
        "version": "sandbox",
        "attempts": 1,
        "env": {
            "SIM2CLAW_PROOF_CLASS": "retrospective_physical_teleoperation_observation",
            "SIM2CLAW_PHYSICAL_AUTHORITY": "false",
        },
    }
    if harness == "codex_cli":
        return codex_cli(
            name="physical_telemetry_codex_cli",
            web_search="disabled",
            goals=False,
            home_dir="/home/agent/.codex",
            **shared,
        )
    if harness == "claude_code":
        return claude_code(
            name="physical_telemetry_claude_code",
            disallowed_tools=["WebSearch", "WebFetch"],
            **shared,
        )
    raise ValueError(f"unsupported harness: {harness}")
