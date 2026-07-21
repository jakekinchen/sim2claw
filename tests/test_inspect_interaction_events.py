from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("inspect_ai")
pytest.importorskip("inspect_swe")

from evals.inspect_gapbench.event_agents import EVENT_SKILL_NAMES, event_skill_paths
from evals.inspect_gapbench.event_dataset import build_event_sessions
from evals.inspect_gapbench.event_task import sim2claw_interaction_event_audit
from evals.inspect_gapbench.event_tools import interaction_event_tools
from inspect_ai._util.registry import registry_info
from sim2claw.interaction_events import TOOL_NAMES


def test_interaction_event_tasks_load_without_provider_or_physical_calls() -> None:
    codex = sim2claw_interaction_event_audit(harness="codex_cli")
    claude = sim2claw_interaction_event_audit(harness="claude_code")
    assert len(codex.dataset) == len(claude.dataset) == 15
    assert [row.metadata["recording_id"] for row in codex.dataset] == [
        row.metadata["recording_id"] for row in claude.dataset
    ]
    assert codex.metadata["sample_count"] == 6486
    assert codex.metadata["model_calls_authorized_by_task"] is False
    assert codex.metadata["annotation_correctness_scored"] is False
    assert codex.metadata["physical_actions"] == 0
    assert claude.metadata["physical_authority"] is False


def test_interaction_event_skills_tools_and_held_out_boundary(
    tmp_path: Path,
) -> None:
    assert tuple(path.name for path in event_skill_paths()) == EVENT_SKILL_NAMES
    assert all((path / "SKILL.md").is_file() for path in event_skill_paths())
    sessions, corpus = build_event_sessions(
        "codex_cli", build_root=tmp_path / "sessions"
    )
    tools = interaction_event_tools(sessions)
    assert tuple(registry_info(tool).name for tool in tools) == TOOL_NAMES
    assert corpus["partition"] == "train"
    assert corpus["measured_contact_claimed"] is False
    with pytest.raises(ValueError, match="evaluator_owned"):
        sim2claw_interaction_event_audit(partition="held_out")
    held_out = sim2claw_interaction_event_audit(
        partition="held_out", evaluator_owned=True
    )
    assert len(held_out.dataset) == 3
    assert held_out.metadata["evaluator_owned"] is True
    compose = (
        Path(__file__).parents[1]
        / "evals"
        / "inspect_gapbench"
        / "compose.yaml"
    ).read_text(encoding="utf-8")
    assert "network_mode: none" in compose
    assert "volumes:" not in compose
    assert "docker.sock" not in compose
