"""Canonical state validation and rendered authority surfaces.

The committed project state binds stable authority and milestone identities.
Exact runtime commits belong in generated receipts so a commit never attempts
to contain its own hash.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from ..learning_factory_artifacts import canonical_digest, sha256_file


STATE_SCHEMA = "sim2claw.autonomous_dev_loop_state.v1"
AUDIT_SCHEMA = "sim2claw.autonomous_dev_loop_authority_audit.v1"
LEDGER_START = "<!-- autonomous-dev-loop-current:start -->"
LEDGER_END = "<!-- autonomous-dev-loop-current:end -->"
TERMINAL_AUTHORITY_MODE = "generated_post_push_merge_readiness_packet"
FINAL_REQUIRED_TEST_TIERS = (
    "final_focused",
    "sail_fast_contract",
    "sail_synthetic_golden",
    "sail_integration",
    "full_repository",
)
FINAL_REMAINING_GATES = (
    "exact_current_HEAD_final_focused_sail_fast_contract_sail_synthetic_golden_sail_integration_and_full_repository_test_receipts",
    "fresh_independent_PASS_review_covering_every_exact_current_HEAD_test_receipt",
    "push_current_main_HEAD_to_origin_main_and_confirm_remote_equality",
    "post_push_D6_authority_audit_bound_to_current_HEAD_and_project_state",
    "generated_merge_ready_terminal_authority_packet_with_zero_live_process_leases",
)

PROHIBITED_TRUE_AUTHORITIES = (
    "release",
    "provider",
    "paid_compute",
    "training",
    "simulator_campaign",
    "simulator_promotion",
    "physical_capture",
    "robot_gateway",
    "robot_motion",
    "history_rewrite",
)


class DevLoopStateError(ValueError):
    """The development-loop control plane drifted or widened authority."""


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DevLoopStateError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise DevLoopStateError(f"{label} must contain an object: {path}")
    return value


def _repo_path(repo_root: Path, value: object, *, label: str) -> Path:
    relative = Path(str(value))
    if relative.is_absolute():
        raise DevLoopStateError(f"{label} must be repository-relative")
    root = repo_root.resolve()
    resolved = (root / relative).resolve()
    if resolved != root and root not in resolved.parents:
        raise DevLoopStateError(f"{label} escapes the repository")
    return resolved


def _git(repo_root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DevLoopStateError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _active_milestone(dev_state: Mapping[str, Any]) -> str:
    milestones = dev_state.get("milestones")
    if not isinstance(milestones, dict):
        raise DevLoopStateError("autonomous_dev_loop milestones must be an object")
    active = [str(name) for name, status in milestones.items() if status == "in_progress"]
    if dev_state.get("status") == "closed":
        if active or not str(milestones.get("D6", "")).startswith("completed"):
            raise DevLoopStateError(
                "closed development loop requires completed D6 and no active milestone"
            )
        return "D6"
    if len(active) != 1:
        raise DevLoopStateError("exactly one development-loop milestone must be in_progress")
    return active[0]


def _validate_terminal_authority_candidate(dev_state: Mapping[str, Any]) -> None:
    terminal_authority = dev_state.get("terminal_authority")
    if terminal_authority is None:
        return
    if not isinstance(terminal_authority, dict):
        raise DevLoopStateError("development-loop terminal authority contract is malformed")
    if terminal_authority.get("mode") != TERMINAL_AUTHORITY_MODE:
        raise DevLoopStateError("unexpected development-loop terminal authority mode")
    if terminal_authority.get("committed_state_may_be_terminal") is not False:
        raise DevLoopStateError("committed development-loop state may not be terminal")
    if terminal_authority.get("required_test_tiers") != list(FINAL_REQUIRED_TEST_TIERS):
        raise DevLoopStateError("final required test tier set changed")

    state_machine = dev_state.get("state_machine")
    if not isinstance(state_machine, dict):
        raise DevLoopStateError("development-loop state machine is missing")
    if (
        dev_state.get("status") != "active"
        or state_machine.get("phase") != "FULL_VERIFY"
        or state_machine.get("terminal") is not False
    ):
        raise DevLoopStateError(
            "committed development-loop state must remain an active FULL_VERIFY candidate"
        )

    milestones = dev_state.get("milestones")
    progress = dev_state.get("progress_ledger")
    if (
        not isinstance(milestones, dict)
        or milestones.get("D6") != "in_progress"
        or not isinstance(progress, dict)
        or progress.get("remaining") != list(FINAL_REMAINING_GATES)
    ):
        raise DevLoopStateError(
            "verification candidate requires in-progress D6 and the exact remaining gates"
        )


def validate_dev_loop_state(
    project_state: Mapping[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(project_state))
    dev_state = normalized.get("autonomous_dev_loop")
    if not isinstance(dev_state, dict):
        raise DevLoopStateError("project state has no autonomous_dev_loop object")
    if dev_state.get("schema_version") != STATE_SCHEMA:
        raise DevLoopStateError("unexpected autonomous development-loop schema")
    if dev_state.get("status") not in {"active", "merge_ready", "closed", "blocked"}:
        raise DevLoopStateError("invalid autonomous development-loop status")
    _validate_terminal_authority_candidate(dev_state)

    active = _active_milestone(dev_state)
    current = str(normalized.get("current_milestone", ""))
    if not current.startswith(f"{active}_"):
        raise DevLoopStateError("top-level current milestone disagrees with development state")

    for name, digest_name in (("plan", "plan_sha256"), ("goal_loop", "goal_loop_sha256")):
        path = _repo_path(repo_root, dev_state.get(name), label=name)
        if not path.is_file():
            raise DevLoopStateError(f"development-loop {name} is missing")
        if sha256_file(path) != dev_state.get(digest_name):
            raise DevLoopStateError(f"development-loop {name} hash drift")

    authority = dev_state.get("authority")
    if not isinstance(authority, dict):
        raise DevLoopStateError("development-loop authority must be an object")
    if any(authority.get(name) is not False for name in PROHIBITED_TRUE_AUTHORITIES):
        raise DevLoopStateError("development-loop external authority widened")
    if authority.get("push_origin_main") is not True:
        raise DevLoopStateError("authorized origin/main push is not recorded")
    if authority.get("prior_sail_fast_forward_completed") is not True:
        raise DevLoopStateError("completed SAIL fast-forward is not recorded")

    physical = (
        dev_state.get("progress_ledger", {})
        .get("external_readiness_blockers", {})
        .get("physical_measurement_and_motion", {})
    )
    if not isinstance(physical, dict):
        raise DevLoopStateError("physical readiness blocker is missing")
    if physical.get("physical_gateway_may_open") is not False:
        raise DevLoopStateError("physical gateway readiness widened")
    if physical.get("measurement_evidence_available") is not False:
        raise DevLoopStateError("missing physical measurement was asserted available")
    return normalized


def render_current_ledger_block(project_state: Mapping[str, Any]) -> str:
    dev_state = project_state["autonomous_dev_loop"]
    active = _active_milestone(dev_state)
    authority = dev_state["authority"]
    physical = dev_state["progress_ledger"]["external_readiness_blockers"][
        "physical_measurement_and_motion"
    ]
    lines = [
        LEDGER_START,
        "## Generated current autonomous-development state",
        "",
        f"- Status: `{dev_state['status']}`.",
        f"- Milestone: `{active}` (`{dev_state['milestones'][active]}`).",
        f"- Branch / remote: `{dev_state['branch']}` / `{dev_state['expected_remote']}`.",
        f"- Baseline: `{dev_state['baseline_commit']}`.",
        f"- Plan SHA-256: `{dev_state['plan_sha256']}`.",
        f"- Goal SHA-256: `{dev_state['goal_loop_sha256']}`.",
        f"- Scoped origin/main push: `{str(authority['push_origin_main']).lower()}`.",
        "- External authority: provider, paid compute, training, simulator "
        "campaign/promotion, physical capture, gateway, and motion are `false`.",
        f"- Physical readiness: `{physical['status']}`; gateway remains `false`.",
        f"- Next step: `{dev_state['progress_ledger']['next_step']}`.",
        LEDGER_END,
    ]
    return "\n".join(lines) + "\n"


def update_current_ledger_block(
    ledger_text: str, *, project_state: Mapping[str, Any]
) -> str:
    rendered = render_current_ledger_block(project_state)
    has_start = LEDGER_START in ledger_text
    has_end = LEDGER_END in ledger_text
    if has_start != has_end:
        raise DevLoopStateError("orchestration ledger has an incomplete generated block")
    if has_start:
        prefix, remainder = ledger_text.split(LEDGER_START, 1)
        _, suffix = remainder.split(LEDGER_END, 1)
        return (
            prefix.rstrip("\n")
            + "\n\n"
            + rendered.rstrip("\n")
            + "\n\n"
            + suffix.lstrip("\n")
        )
    title = "# Orchestration Ledger\n"
    if not ledger_text.startswith(title):
        raise DevLoopStateError("orchestration ledger title changed")
    return (
        title.rstrip("\n")
        + "\n\n"
        + rendered.rstrip("\n")
        + "\n\n"
        + ledger_text[len(title) :].lstrip("\n")
    )


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def audit_dev_loop_authority(
    repo_root: Path,
    *,
    check_git: bool = True,
    git_snapshot: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    project_state_path = root / "docs/autonomous-workflow/project_state.json"
    project_state = _load_object(project_state_path, label="project state")
    project_state = validate_dev_loop_state(project_state, repo_root=root)
    dev_state = project_state["autonomous_dev_loop"]
    active = _active_milestone(dev_state)
    checks: list[dict[str, Any]] = []

    checks.append(_check("canonical_state", True, f"schema={STATE_SCHEMA}"))
    checks.append(_check("plan_identity", True, str(dev_state["plan_sha256"])))
    checks.append(_check("goal_identity", True, str(dev_state["goal_loop_sha256"])))

    goal = (root / "GOAL.md").read_text(encoding="utf-8")
    goal_matches = re.findall(
        r"^Current milestone\s*: \*\*(D\d+)\b", goal, re.MULTILINE | re.IGNORECASE
    )
    goal_ok = (
        len(goal_matches) == 1
        and goal_matches[0] == active
        and str(dev_state["plan"]) in goal
        and str(dev_state["goal_loop"]) in goal
    )
    observed_goal = ",".join(goal_matches) if goal_matches else "missing"
    checks.append(
        _check(
            "goal_alignment",
            goal_ok,
            f"active={active} observed_current={observed_goal}",
        )
    )

    ledger_path = root / ".factory/orchestration-ledger.md"
    ledger = ledger_path.read_text(encoding="utf-8")
    expected_block = render_current_ledger_block(project_state)
    ledger_ok = expected_block in ledger
    checks.append(_check("rendered_ledger", ledger_ok, "current block matches canonical state"))
    history = ledger
    if LEDGER_START in ledger and LEDGER_END in ledger:
        prefix, remainder = ledger.split(LEDGER_START, 1)
        _, suffix = remainder.split(LEDGER_END, 1)
        history = prefix + suffix
    shadow_pattern = re.compile(
        r"^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?current\s+"
        r"(?:milestone|state|control\s+plane)\b",
        re.MULTILINE | re.IGNORECASE,
    )
    shadow_free = shadow_pattern.search(history) is None
    checks.append(
        _check(
            "no_shadow_current_state",
            shadow_free,
            "historical ledger contains no competing current-state labels",
        )
    )

    git_identity: dict[str, str] | None = None
    if check_git:
        snapshot = dict(git_snapshot or {})
        branch = snapshot.get("branch") or _git(root, "branch", "--show-current")
        head = snapshot.get("head") or _git(root, "rev-parse", "HEAD")
        remote = snapshot.get("remote") or _git(root, "rev-parse", str(dev_state["expected_remote"]))
        baseline_ancestor = snapshot.get("baseline_ancestor")
        if baseline_ancestor is None:
            completed = subprocess.run(
                ["git", "merge-base", "--is-ancestor", str(dev_state["baseline_commit"]), head],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )
            baseline_ancestor = "true" if completed.returncode == 0 else "false"
        checks.extend(
            [
                _check("branch", branch == dev_state["branch"], f"observed={branch}"),
                _check("remote", head == remote, f"head={head} remote={remote}"),
                _check("baseline_ancestry", baseline_ancestor == "true", str(dev_state["baseline_commit"])),
            ]
        )
        git_identity = {
            "branch": branch,
            "head": head,
            "remote": remote,
            "expected_remote": str(dev_state["expected_remote"]),
        }

    authority = dev_state["authority"]
    authority_ok = all(authority[name] is False for name in PROHIBITED_TRUE_AUTHORITIES)
    checks.append(_check("authority", authority_ok, "external authority remains false"))
    passed = all(row["passed"] for row in checks)
    unsigned = {
        "schema_version": AUDIT_SCHEMA,
        "status": "pass" if passed else "fail",
        "proof_class": "deterministic_repository_authority_consistency",
        "active_milestone": active,
        "project_state_sha256": sha256_file(project_state_path),
        "project_state_digest": canonical_digest(project_state),
        "state_semantics": {
            "status": dev_state["status"],
            "phase": dev_state.get("state_machine", {}).get("phase"),
            "terminal": dev_state.get("state_machine", {}).get("terminal"),
            "d6_status": dev_state["milestones"].get("D6"),
            "remaining": list(dev_state["progress_ledger"].get("remaining", [])),
            "terminal_authority_mode": dev_state.get("terminal_authority", {}).get("mode"),
        },
        "git_identity": git_identity,
        "checks": checks,
        "authority": {
            name: bool(authority[name])
            for name in sorted(authority)
        },
    }
    return {**unsigned, "audit_digest": canonical_digest(unsigned)}


__all__ = [
    "AUDIT_SCHEMA",
    "DevLoopStateError",
    "LEDGER_END",
    "LEDGER_START",
    "FINAL_REMAINING_GATES",
    "FINAL_REQUIRED_TEST_TIERS",
    "STATE_SCHEMA",
    "TERMINAL_AUTHORITY_MODE",
    "audit_dev_loop_authority",
    "render_current_ledger_block",
    "update_current_ledger_block",
    "validate_dev_loop_state",
]
