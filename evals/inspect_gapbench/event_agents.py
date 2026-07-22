"""Matched read-only Inspect SWE adapters for interaction-event auditing."""

from __future__ import annotations

from pathlib import Path

from inspect_ai.agent import Agent, BridgedToolsSpec
from inspect_swe import claude_code, codex_cli


PACKAGE_ROOT = Path(__file__).resolve().parent
EVENT_SKILL_ROOT = PACKAGE_ROOT / "event_skills"
EVENT_SKILL_NAMES = ("audit-interaction-events",)


def event_skill_paths() -> list[Path]:
    return [EVENT_SKILL_ROOT / name for name in EVENT_SKILL_NAMES]


def build_event_agent(harness: str, bridge: BridgedToolsSpec) -> Agent:
    shared = {
        "skills": event_skill_paths(),
        "bridged_tools": [bridge],
        "cwd": "/workspace",
        "sandbox": "default",
        "user": "agent",
        "version": "sandbox",
        "attempts": 1,
        "env": {
            "SIM2CLAW_PROOF_CLASS": "retrospective_physical_multimodal_derived_candidates",
            "SIM2CLAW_PHYSICAL_AUTHORITY": "false",
            "SIM2CLAW_CONTACT_GROUND_TRUTH": "false",
        },
    }
    if harness == "codex_cli":
        return codex_cli(
            name="interaction_event_codex_cli",
            web_search="disabled",
            goals=False,
            home_dir="/home/agent/.codex",
            **shared,
        )
    if harness == "claude_code":
        return claude_code(
            name="interaction_event_claude_code",
            disallowed_tools=["WebSearch", "WebFetch"],
            **shared,
        )
    raise ValueError(f"unsupported harness: {harness}")
