from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.dev_loop.state import (
    DevLoopStateError,
    audit_dev_loop_authority,
    render_current_ledger_block,
    update_current_ledger_block,
    validate_dev_loop_state,
)
from sim2claw.learning_factory_artifacts import sha256_file


def _repo(tmp_path: Path) -> tuple[Path, dict]:
    plan = tmp_path / "docs/goals/plan.md"
    goal_loop = tmp_path / "docs/autonomous-workflow/goal-loop.md"
    plan.parent.mkdir(parents=True)
    goal_loop.parent.mkdir(parents=True)
    plan.write_text("# Plan\n", encoding="utf-8")
    goal_loop.write_text("# Goal loop\n", encoding="utf-8")
    state = {
        "schema_version": "sim2claw.autonomous_project_state.v1",
        "current_milestone": "D1_CANONICAL_STATE_AND_DRIFT_CHECKER",
        "autonomous_dev_loop": {
            "schema_version": "sim2claw.autonomous_dev_loop_state.v1",
            "status": "active",
            "plan": "docs/goals/plan.md",
            "plan_sha256": sha256_file(plan),
            "goal_loop": "docs/autonomous-workflow/goal-loop.md",
            "goal_loop_sha256": sha256_file(goal_loop),
            "branch": "main",
            "baseline_commit": "abc1234",
            "expected_remote": "origin/main",
            "milestones": {"D0": "completed", "D1": "in_progress", "D2": "pending"},
            "progress_ledger": {
                "next_step": "implement_D1",
                "external_readiness_blockers": {
                    "physical_measurement_and_motion": {
                        "status": "blocked_hardware_and_calibration_not_ready",
                        "physical_gateway_may_open": False,
                        "measurement_evidence_available": False,
                    }
                },
            },
            "authority": {
                "push_origin_main": True,
                "prior_sail_fast_forward_completed": True,
                "history_rewrite": False,
                "release": False,
                "provider": False,
                "paid_compute": False,
                "training": False,
                "simulator_campaign": False,
                "simulator_promotion": False,
                "physical_capture": False,
                "robot_gateway": False,
                "robot_motion": False,
            },
        },
    }
    (tmp_path / "GOAL.md").write_text(
        "\n".join(
            [
                "# Goal",
                "docs/goals/plan.md",
                "docs/autonomous-workflow/goal-loop.md",
                "Current milestone: **D1 — test milestone**",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    state_path = tmp_path / "docs/autonomous-workflow/project_state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    ledger_path = tmp_path / ".factory/orchestration-ledger.md"
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text("# Orchestration Ledger\n", encoding="utf-8")
    ledger_path.write_text(
        update_current_ledger_block(ledger_path.read_text(), project_state=state),
        encoding="utf-8",
    )
    return tmp_path, state


def _snapshot(**overrides: str) -> dict[str, str]:
    return {
        "branch": "main",
        "head": "def5678",
        "remote": "def5678",
        "baseline_ancestor": "true",
        **overrides,
    }


def test_live_authority_surfaces_pass_with_exact_rendered_state(tmp_path: Path) -> None:
    root, _ = _repo(tmp_path)
    report = audit_dev_loop_authority(root, git_snapshot=_snapshot())
    assert report["status"] == "pass"
    assert all(row["passed"] for row in report["checks"])
    assert report["authority"]["physical_capture"] is False


def test_plan_hash_and_authority_widening_fail_closed(tmp_path: Path) -> None:
    root, state = _repo(tmp_path)
    (root / "docs/goals/plan.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(DevLoopStateError, match="plan hash drift"):
        audit_dev_loop_authority(root, git_snapshot=_snapshot())

    (root / "docs/goals/plan.md").write_text("# Plan\n", encoding="utf-8")
    state["autonomous_dev_loop"]["authority"]["physical_capture"] = True
    (root / "docs/autonomous-workflow/project_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    with pytest.raises(DevLoopStateError, match="authority widened"):
        audit_dev_loop_authority(root, git_snapshot=_snapshot())


def test_goal_ledger_branch_and_remote_drift_are_reported(tmp_path: Path) -> None:
    root, _ = _repo(tmp_path)
    (root / "GOAL.md").write_text("# stale\n", encoding="utf-8")
    ledger = root / ".factory/orchestration-ledger.md"
    ledger.write_text("# Orchestration Ledger\n", encoding="utf-8")
    report = audit_dev_loop_authority(
        root,
        git_snapshot=_snapshot(branch="feature", remote="different"),
    )
    failed = {row["name"] for row in report["checks"] if not row["passed"]}
    assert failed == {"goal_alignment", "rendered_ledger", "branch", "remote"}


def test_shadow_current_ledger_state_is_rejected(tmp_path: Path) -> None:
    root, _ = _repo(tmp_path)
    ledger = root / ".factory/orchestration-ledger.md"
    ledger.write_text(
        ledger.read_text(encoding="utf-8")
        + "\n## Current control plane — autonomous development operations and advancement\n"
        + "\n- Current milestone: D0\n",
        encoding="utf-8",
    )
    report = audit_dev_loop_authority(root, git_snapshot=_snapshot())
    failed = {row["name"] for row in report["checks"] if not row["passed"]}
    assert failed == {"no_shadow_current_state"}


def test_duplicate_goal_current_milestone_is_rejected(tmp_path: Path) -> None:
    root, _ = _repo(tmp_path)
    goal = root / "GOAL.md"
    goal.write_text(
        goal.read_text(encoding="utf-8")
        + "\nCurrent milestone: **D9 — shadow milestone**\n",
        encoding="utf-8",
    )
    report = audit_dev_loop_authority(root, git_snapshot=_snapshot())
    failed = {row["name"] for row in report["checks"] if not row["passed"]}
    assert failed == {"goal_alignment"}


def test_milestone_drift_and_multiple_active_milestones_fail(tmp_path: Path) -> None:
    root, state = _repo(tmp_path)
    state["current_milestone"] = "D2_OTHER"
    (root / "docs/autonomous-workflow/project_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    with pytest.raises(DevLoopStateError, match="current milestone"):
        audit_dev_loop_authority(root, git_snapshot=_snapshot())

    state["current_milestone"] = "D1_CANONICAL_STATE_AND_DRIFT_CHECKER"
    state["autonomous_dev_loop"]["milestones"]["D2"] = "in_progress"
    (root / "docs/autonomous-workflow/project_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    with pytest.raises(DevLoopStateError, match="exactly one"):
        audit_dev_loop_authority(root, git_snapshot=_snapshot())


def test_closed_state_requires_completed_d6_and_no_active_milestone(
    tmp_path: Path,
) -> None:
    root, state = _repo(tmp_path)
    state["current_milestone"] = "D6_VERIFICATION_AND_CLOSEOUT"
    dev_state = state["autonomous_dev_loop"]
    dev_state["status"] = "closed"
    dev_state["milestones"] = {
        "D0": "completed",
        "D1": "completed",
        "D2": "completed",
        "D3": "completed",
        "D4": "completed",
        "D5": "completed",
        "D6": "completed_final_verification_and_review",
    }
    validated = validate_dev_loop_state(state, repo_root=root)
    assert validated["autonomous_dev_loop"]["status"] == "closed"

    dev_state["milestones"]["D6"] = "pending"
    with pytest.raises(DevLoopStateError, match="requires completed D6"):
        validate_dev_loop_state(state, repo_root=root)

    dev_state["milestones"]["D6"] = "completed_final_verification_and_review"
    dev_state["milestones"]["D5"] = "in_progress"
    with pytest.raises(DevLoopStateError, match="requires completed D6"):
        validate_dev_loop_state(state, repo_root=root)


def test_ledger_render_is_idempotent_and_repairs_only_generated_block(
    tmp_path: Path,
) -> None:
    root, state = _repo(tmp_path)
    ledger_path = root / ".factory/orchestration-ledger.md"
    ledger = ledger_path.read_text(encoding="utf-8") + "\nHistorical evidence.\n"
    once = update_current_ledger_block(ledger, project_state=state)
    twice = update_current_ledger_block(once, project_state=state)
    assert once == twice
    assert render_current_ledger_block(state) in once
    assert once.endswith("Historical evidence.\n")


def test_incomplete_ledger_markers_fail_closed(tmp_path: Path) -> None:
    _, state = _repo(tmp_path)
    with pytest.raises(DevLoopStateError, match="incomplete generated block"):
        update_current_ledger_block(
            "# Orchestration Ledger\n<!-- autonomous-dev-loop-current:start -->\n",
            project_state=state,
        )
