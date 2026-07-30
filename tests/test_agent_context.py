from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from sim2claw.agent_context import (
    AgentContextError,
    check_agent_workspace,
    compile_agent_context,
    render_goal,
)
from sim2claw.learning_factory_artifacts import sha256_file


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "agent-context@example.invalid")
    _git(tmp_path, "config", "user.name", "Agent Context Test")
    for relative in (
        "configs/agent/schemas",
        "configs/sail",
        "configs/decisions",
        "docs/autonomous-workflow",
        "docs/history",
    ):
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    schema = json.loads(
        (
            Path(__file__).parents[1]
            / "configs/agent/schemas/current_state_v1.json"
        ).read_text(encoding="utf-8")
    )
    (tmp_path / "configs/agent/schemas/current_state_v1.json").write_text(
        json.dumps(schema), encoding="utf-8"
    )
    queue = tmp_path / "docs/autonomous-workflow/queue.md"
    queue.write_text("# Queue\n", encoding="utf-8")
    closeout = tmp_path / "configs/decisions/or10.json"
    closeout.write_text('{"status":"pass"}\n', encoding="utf-8")
    graph = {
        "schema_version": "sim2claw.sail_current_campaign_graph_config.v1",
        "campaign_id": "campaign-v1",
        "status": "complete_or10_external_boundary",
        "active_card": None,
        "next_transition": "external_service_then_or9",
        "authority": {
            "physical_motion": False,
            "camera_open": False,
            "serial": False,
            "gateway": False,
            "heldout_open": False,
            "task_attempt": False,
            "training": False,
            "paid_compute": False,
            "simulator_promotion": False,
            "transfer_claim": False,
        },
        "source_bindings": {
            "queue": {
                "path": "docs/autonomous-workflow/queue.md",
                "sha256": sha256_file(queue),
                "proof_class": "campaign_control_state",
            },
            "or10": {
                "path": "configs/decisions/or10.json",
                "sha256": sha256_file(closeout),
                "proof_class": "bounded_diagnostic",
            },
        },
    }
    graph_path = tmp_path / "configs/sail/current_graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    project_state = {
        "schema_version": "sim2claw.autonomous_project_state.v1",
        "active_campaign": "campaign-v1",
        "current_milestone": "OR10_COMPLETE_EXTERNAL_BOUNDARY",
        "proof_class": "bounded_diagnostic",
        "autonomous_dev_loop": {
            "schema_version": "sim2claw.autonomous_dev_loop_state.v1",
            "status": "active",
            "operational_scope": "historical_closed_by_terminal_packet",
        },
        "sail_executed_benchmark_c2_adapter": {
            "closed_d6_baseline": {
                "path": "outputs/dev-loop/final/merge-readiness-packet.json",
                "file_sha256": "1" * 64,
                "packet_digest": "2" * 64,
                "head": "3" * 40,
                "terminal_authority": True,
            }
        },
    }
    project_path = tmp_path / "docs/autonomous-workflow/project_state.json"
    project_path.write_text(json.dumps(project_state), encoding="utf-8")
    manifest = {
        "schema_version": "sim2claw.agent_current_state.v1",
        "project_state_path": "docs/autonomous-workflow/project_state.json",
        "campaign_graph_path": "configs/sail/current_graph.json",
        "goal_path": "GOAL.md",
        "goal_history_path": "docs/history/GOAL-history.md",
        "expected_branch": "main",
        "expected_remote": "origin/main",
        "require_remote_equality_at_boundary": True,
        "max_context_bytes": 15360,
        "max_goal_lines": 100,
        "historical_control_planes": [
            {
                "name": "autonomous_dev_loop",
                "project_state_key": "autonomous_dev_loop",
                "operational_scope": "historical_closed_by_terminal_packet",
                "closeout_state_path": "sail_executed_benchmark_c2_adapter.closed_d6_baseline",
            }
        ],
    }
    (tmp_path / "configs/agent/current_state_v1.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tmp_path / "docs/history/GOAL-history.md").write_text(
        "# Historical goal\n", encoding="utf-8"
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
    (tmp_path / "GOAL.md").write_text("# placeholder\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "seed")
    _git(tmp_path, "remote", "add", "origin", str(tmp_path))
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    (tmp_path / "GOAL.md").write_text(render_goal(tmp_path), encoding="utf-8")
    _git(tmp_path, "add", "GOAL.md")
    _git(tmp_path, "commit", "-m", "render goal")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    return tmp_path


def test_compiler_emits_bounded_read_only_context_at_external_boundary(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    packet = compile_agent_context(root, role="executor")
    assert packet["status"] == "pass"
    assert packet["execution_admitted"] is False
    assert packet["scope"]["write_paths"] == []
    assert packet["authority"]["commit"] is False
    assert packet["campaign"]["active_card"] is None
    assert packet["limits"]["context_bytes"] < 15360
    assert packet["limits"]["context_bytes"] == len(
        json.dumps(packet, indent=2, sort_keys=True).encode("utf-8")
    )
    assert packet["limits"]["goal_lines"] < 100
    assert packet["historical_control_planes"][0]["operational_scope"].startswith(
        "historical_closed"
    )

    report = check_agent_workspace(root)
    assert report["status"] == "pass"
    assert set(report["roles"]) == {"executor", "manager", "reviewer"}


def test_compiler_rejects_shadow_control_plane_and_queue_hash_drift(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    state_path = root / "docs/autonomous-workflow/project_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["autonomous_dev_loop"].pop("operational_scope")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(AgentContextError, match="not explicitly archived"):
        compile_agent_context(root, role="manager")

    state["autonomous_dev_loop"][
        "operational_scope"
    ] = "historical_closed_by_terminal_packet"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    (root / "docs/autonomous-workflow/queue.md").write_text(
        "# drift\n", encoding="utf-8"
    )
    with pytest.raises(AgentContextError, match="queue binding hash drift"):
        compile_agent_context(root, role="manager")


def test_compiler_rejects_goal_drift_widened_authority_and_active_unscoped_write(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    (root / "GOAL.md").write_text("# stale\n", encoding="utf-8")
    with pytest.raises(AgentContextError, match="not the generated"):
        compile_agent_context(root, role="reviewer")

    (root / "GOAL.md").write_text(render_goal(root), encoding="utf-8")
    graph_path = root / "configs/sail/current_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["authority"]["physical_motion"] = True
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    with pytest.raises(AgentContextError, match="authority widened"):
        compile_agent_context(root, role="executor")

    graph["authority"]["physical_motion"] = False
    graph["active_card"] = "OR10"
    graph["status"] = "active_or10"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (root / "GOAL.md").write_text(render_goal(root), encoding="utf-8")
    with pytest.raises(AgentContextError, match="card-specific allowed-path"):
        compile_agent_context(root, role="executor")


def test_compiler_admits_only_scoped_active_card_executor_write(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    graph_path = root / "configs/sail/current_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["active_card"] = "OR10"
    graph["status"] = "active_or10"
    graph["active_card_contract"] = {
        "card_id": "OR10",
        "proof_target": "one bounded diagnostic",
        "allowed_paths": [
            "configs/evaluations/diagnostic.json",
            "src/sim2claw/diagnostic.py",
            "tests/test_diagnostic.py",
        ],
        "allowed_operations": ["read", "test", "write", "commit"],
        "validation_commands": [
            "uv run pytest -q tests/test_diagnostic.py",
            "uv run --locked sim2claw check --profile agent",
        ],
        "commit": True,
        "push_origin_main": False,
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (root / "GOAL.md").write_text(render_goal(root), encoding="utf-8")

    executor = compile_agent_context(root, role="executor")
    assert executor["execution_admitted"] is True
    assert executor["scope"]["write_paths"] == graph[
        "active_card_contract"
    ]["allowed_paths"]
    assert executor["scope"]["proof_target"] == "one bounded diagnostic"
    assert executor["authority"]["commit"] is True
    assert executor["authority"]["push_origin_main"] is False
    assert executor["authority"]["physical_motion"] is False

    reviewer = compile_agent_context(root, role="reviewer")
    assert reviewer["execution_admitted"] is False
    assert reviewer["scope"]["write_paths"] == []
    assert reviewer["authority"]["commit"] is False


def test_compiler_rejects_active_card_contract_scope_and_git_widening(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    graph_path = root / "configs/sail/current_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["active_card"] = "OR10"
    graph["status"] = "active_or10"
    graph["active_card_contract"] = {
        "card_id": "OR9",
        "proof_target": "mismatched",
        "allowed_paths": ["src/sim2claw/diagnostic.py"],
        "allowed_operations": ["read", "write"],
        "validation_commands": ["uv run pytest -q"],
        "commit": False,
        "push_origin_main": False,
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (root / "GOAL.md").write_text(render_goal(root), encoding="utf-8")
    with pytest.raises(AgentContextError, match="identity mismatch"):
        compile_agent_context(root, role="executor")

    graph["active_card_contract"]["card_id"] = "OR10"
    graph["active_card_contract"]["allowed_paths"] = ["../escape"]
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    with pytest.raises(AgentContextError, match="escapes"):
        compile_agent_context(root, role="executor")

    graph["active_card_contract"]["allowed_paths"] = [
        "src/sim2claw/diagnostic.py"
    ]
    graph["active_card_contract"]["push_origin_main"] = True
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    with pytest.raises(AgentContextError, match="push requires commit"):
        compile_agent_context(root, role="executor")


def test_context_digest_changes_when_role_changes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    executor = compile_agent_context(root, role="executor")
    reviewer = compile_agent_context(root, role="reviewer")
    assert executor["context_digest"] != reviewer["context_digest"]
    assert executor["scope"]["allowed_operations"] != reviewer["scope"][
        "allowed_operations"
    ]


def test_compiler_rejects_stale_card_and_wrong_repository_identity(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    graph_path = root / "configs/sail/current_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["active_card"] = "OR9"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    with pytest.raises(AgentContextError, match="active card disagrees"):
        compile_agent_context(root, role="manager")

    graph["active_card"] = None
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (root / "identity-drift.txt").write_text("drift\n", encoding="utf-8")
    _git(root, "add", "identity-drift.txt")
    _git(root, "commit", "-m", "advance without remote")
    with pytest.raises(AgentContextError, match="HEAD differs"):
        compile_agent_context(root, role="manager")
