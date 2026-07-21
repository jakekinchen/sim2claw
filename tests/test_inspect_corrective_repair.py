from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("inspect_ai")
pytest.importorskip("inspect_swe")

from evals.inspect_gapbench.agents import CORRECTIVE_SKILL_NAMES, corrective_skill_paths
from evals.inspect_gapbench.corrective_dataset import build_corrective_sessions
from evals.inspect_gapbench.corrective_task import sim2claw_corrective_repair
from evals.inspect_gapbench.corrective_tools import corrective_inspect_tools
from inspect_ai._util.registry import registry_info
from sim2claw.corrective_benchmark import TOOL_NAMES, case_ids


def test_corrective_tasks_load_with_identical_cases_and_limits_without_model_calls() -> None:
    codex = sim2claw_corrective_repair(harness="codex_cli")
    claude = sim2claw_corrective_repair(harness="claude_code")
    assert len(codex.dataset) == len(claude.dataset) == len(case_ids()) == 4
    assert [row.metadata["case_id"] for row in codex.dataset] == [row.metadata["case_id"] for row in claude.dataset]
    assert codex.message_limit == claude.message_limit == 60
    assert codex.token_limit == claude.token_limit == 80_000
    assert codex.turn_limit == claude.turn_limit == 30
    assert codex.metadata["model_calls_authorized_by_task"] is False
    assert claude.metadata["physical_authority"] is False


def test_corrective_skills_tools_and_sandbox_are_shared_and_bounded(tmp_path: Path) -> None:
    assert tuple(path.name for path in corrective_skill_paths()) == CORRECTIVE_SKILL_NAMES
    assert all((path / "SKILL.md").is_file() for path in corrective_skill_paths())
    sessions = build_corrective_sessions("codex_cli", tmp_path / "sessions")
    tools = corrective_inspect_tools(sessions)
    assert tuple(registry_info(tool).name for tool in tools) == TOOL_NAMES
    task = sim2claw_corrective_repair(harness="codex_cli")
    assert len(task.approval) == 1
    compose = (Path(__file__).parents[1] / "evals" / "inspect_gapbench" / "compose.yaml").read_text(encoding="utf-8")
    assert "network_mode: none" in compose
    assert "volumes:" not in compose
    assert "docker.sock" not in compose


def test_harness_public_case_bytes_differ_only_in_editable_baseline_provenance(tmp_path: Path) -> None:
    codex = build_corrective_sessions("codex_cli", tmp_path / "codex")
    claude = build_corrective_sessions("claude_code", tmp_path / "claude")
    for case_id in case_ids():
        assert codex[case_id].case["case_sha256"] == claude[case_id].case["case_sha256"]
        codex_evidence = sorted((codex[case_id].packet_root / "evidence").glob("*.json"))
        claude_evidence = sorted((claude[case_id].packet_root / "evidence").glob("*.json"))
        assert [path.read_bytes() for path in codex_evidence] == [path.read_bytes() for path in claude_evidence]
