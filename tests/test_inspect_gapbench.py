from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("inspect_ai")
pytest.importorskip("inspect_swe")

from evals.inspect_gapbench.agents import SKILL_NAMES, skill_paths
from evals.inspect_gapbench.task import sim2claw_gapbench
from evals.inspect_gapbench.tools import inspect_tools
from inspect_ai._util.registry import registry_info
from sim2claw.gapbench_tools import TOOL_NAMES


def test_both_inspect_tasks_load_without_a_model_call(
    gapbench_smoke_sealed_source: tuple[Path, str],
) -> None:
    source, _ = gapbench_smoke_sealed_source
    codex = sim2claw_gapbench(harness="codex_cli", sealed_source=str(source))
    claude = sim2claw_gapbench(harness="claude_code", sealed_source=str(source))
    assert len(codex.dataset) == len(claude.dataset) == 6
    assert [sample.metadata["case_id"] for sample in codex.dataset] == [sample.metadata["case_id"] for sample in claude.dataset]
    assert codex.metadata["model_calls_authorized_by_task"] is False
    assert claude.metadata["physical_authority"] is False


def test_shared_skills_and_tools_are_complete(
    gapbench_smoke_sealed_source: tuple[Path, str],
) -> None:
    source, _ = gapbench_smoke_sealed_source
    assert tuple(path.name for path in skill_paths()) == SKILL_NAMES
    assert all((path / "SKILL.md").is_file() for path in skill_paths())
    task = sim2claw_gapbench(harness="codex_cli", sealed_source=str(source))
    sessions = __import__(
        "evals.inspect_gapbench.dataset", fromlist=["build_sessions"]
    ).build_sessions("codex_cli", sealed_source=source)
    tools = inspect_tools(sessions)
    assert tuple(registry_info(tool).name for tool in tools) == TOOL_NAMES
    assert len(task.approval) == 1


def test_compose_has_no_host_mount_network_or_privileged_surface() -> None:
    root = Path(__file__).parents[1] / "evals" / "inspect_gapbench"
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "network_mode: none" in compose
    assert "cap_drop:" in compose and "cap_add:\n      - CHOWN\n      - SETGID\n      - SETUID" in compose
    assert "no-new-privileges:true" in compose
    assert "volumes:" not in compose
    assert "docker.sock" not in compose
    assert "USER root" in dockerfile
    assert "@openai/codex@${CODEX_CLI_VERSION}" in dockerfile
    assert "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" in dockerfile
