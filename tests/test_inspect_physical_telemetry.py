from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("inspect_ai")
pytest.importorskip("inspect_swe")

from evals.inspect_gapbench.telemetry_agents import (
    TELEMETRY_SKILL_NAMES,
    telemetry_skill_paths,
)
from evals.inspect_gapbench.telemetry_dataset import build_telemetry_sessions
from evals.inspect_gapbench.telemetry_task import sim2claw_physical_telemetry_audit
from evals.inspect_gapbench.telemetry_tools import telemetry_inspect_tools
from inspect_ai._util.registry import registry_info
from sim2claw.physical_telemetry import TOOL_NAMES


def test_physical_telemetry_tasks_load_without_model_or_physical_calls() -> None:
    codex = sim2claw_physical_telemetry_audit(harness="codex_cli")
    claude = sim2claw_physical_telemetry_audit(harness="claude_code")
    assert len(codex.dataset) == len(claude.dataset) == 18
    assert [row.metadata["recording_id"] for row in codex.dataset] == [
        row.metadata["recording_id"] for row in claude.dataset
    ]
    assert codex.metadata["sample_count"] == 7741
    assert codex.metadata["model_calls_authorized_by_task"] is False
    assert codex.metadata["physical_actions"] == 0
    assert claude.metadata["physical_authority"] is False


def test_physical_telemetry_skills_tools_and_sandbox_are_bounded(
    tmp_path: Path,
) -> None:
    assert tuple(path.name for path in telemetry_skill_paths()) == TELEMETRY_SKILL_NAMES
    assert all((path / "SKILL.md").is_file() for path in telemetry_skill_paths())
    sessions, corpus = build_telemetry_sessions("codex_cli", tmp_path / "sessions")
    tools = telemetry_inspect_tools(sessions)
    assert tuple(registry_info(tool).name for tool in tools) == TOOL_NAMES
    assert corpus["comparison_scope"]["real_vs_sim"] is False
    task = sim2claw_physical_telemetry_audit(harness="codex_cli")
    assert len(task.approval) == 1
    compose = (
        Path(__file__).parents[1]
        / "evals"
        / "inspect_gapbench"
        / "compose.yaml"
    ).read_text(encoding="utf-8")
    assert "network_mode: none" in compose
    assert "volumes:" not in compose
    assert "docker.sock" not in compose
