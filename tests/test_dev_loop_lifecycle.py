from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sim2claw.dev_loop import lifecycle
from sim2claw.dev_loop.contracts import SCHEMA_PATHS, load_dev_loop_schema
from sim2claw.dev_loop.lifecycle import (
    CANONICAL_FINAL_REVIEW_PATH,
    DevLoopLifecycleError,
    build_merge_readiness_packet,
    build_process_lease,
    build_review_receipt,
    build_task_contract,
    build_test_identity,
    build_test_receipt,
    cleanup_expired_process_lease,
    complete_process_lease,
    mark_missing_process_orphaned,
    resume_process_lease,
    is_test_receipt_reusable,
    REQUIRED_AUTHORITY_AUDIT_CHECKS,
    verify_task_contract,
    verify_authority_audit,
    verify_merge_readiness_packet,
    verify_test_receipt,
    writer_lease_available,
)
from sim2claw.dev_loop.state import (
    FINAL_REMAINING_GATES,
    FINAL_REQUIRED_TEST_TIERS,
    TERMINAL_AUTHORITY_MODE,
    audit_dev_loop_authority,
    update_current_ledger_block,
)
from sim2claw.learning_factory_artifacts import canonical_digest, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]


def _task(tmp_path: Path, *, role: str = "executor") -> dict:
    target = tmp_path / "work.py"
    target.write_text("pass\n", encoding="utf-8")
    return build_task_contract(
        task_id=f"task-{role}",
        role=role,
        repo_root=tmp_path,
        branch="main",
        base_commit="abc1234",
        allowed_paths=[target],
        allowed_operations=(
            ["read", "write", "test"]
            if role == "executor"
            else ["read", "review", "test"]
        ),
        proof_target="bounded deterministic proof",
    )


def _identity(command: list[str] | None = None) -> dict:
    return build_test_identity(
        repo_root=REPO_ROOT,
        command=command or ["pytest", "tests/test_dev_loop_lifecycle.py"],
        relevant_paths=["pyproject.toml", "tests/test_dev_loop_lifecycle.py"],
    )


def _test_receipt(identity: dict | None = None) -> dict:
    return build_test_receipt(
        identity=identity or _identity(),
        tier="focused",
        exit_code=0,
        duration_seconds=1.25,
        counts={"passed": 8, "failed": 0},
        log_sha256="0" * 64,
    )


def _redigest(payload: dict, field: str) -> dict:
    unsigned = {key: value for key, value in payload.items() if key != field}
    return {**unsigned, field: canonical_digest(unsigned)}


def test_all_dev_loop_schemas_are_valid() -> None:
    assert set(SCHEMA_PATHS) == {"task", "review", "test", "process", "merge"}
    for name, path in SCHEMA_PATHS.items():
        assert path.is_file()
        assert load_dev_loop_schema(name)["$schema"].endswith("2020-12/schema")


def test_task_contract_binds_scope_bounds_and_false_external_authority(
    tmp_path: Path,
) -> None:
    contract = verify_task_contract(_task(tmp_path))
    assert contract["role"] == "executor"
    assert contract["allowed_paths"] == ["work.py"]
    assert contract["authority"]["push_origin_main"] is True
    assert contract["authority"]["physical_capture"] is False

    tampered = copy.deepcopy(contract)
    tampered["allowed_paths"].append("other.py")
    with pytest.raises(DevLoopLifecycleError, match="digest mismatch"):
        verify_task_contract(tampered)

    reviewer = verify_task_contract(_task(tmp_path, role="reviewer"))
    assert reviewer["authority"]["commit"] is False
    assert reviewer["authority"]["push_origin_main"] is False
    with pytest.raises(DevLoopLifecycleError, match="writer operations"):
        build_task_contract(
            task_id="bad-reviewer",
            role="reviewer",
            repo_root=tmp_path,
            branch="main",
            base_commit="abc1234",
            allowed_paths=[tmp_path / "work.py"],
            allowed_operations=["read", "write"],
            proof_target="must fail",
        )


def test_test_receipt_reuse_requires_exact_identity() -> None:
    identity = _identity()
    receipt = _test_receipt(identity)
    assert verify_test_receipt(receipt)["status"] == "pass"
    assert is_test_receipt_reusable(receipt, identity)

    changed = _identity(["pytest", "tests/test_dev_loop_state.py"])
    assert not is_test_receipt_reusable(receipt, changed)
    tampered = copy.deepcopy(receipt)
    tampered["counts"]["passed"] += 1
    assert not is_test_receipt_reusable(tampered, identity)

    widened = copy.deepcopy(receipt)
    widened["authority"]["commit"] = True
    widened = _redigest(widened, "receipt_digest")
    with pytest.raises(DevLoopLifecycleError, match="repository-write authority"):
        verify_test_receipt(widened)


def test_test_identity_hashes_untracked_files_inside_relevant_directories(
    tmp_path: Path,
) -> None:
    (tmp_path / "relevant").mkdir()
    (tmp_path / "relevant" / "one.txt").write_text("one\n", encoding="utf-8")
    lifecycle.subprocess.run(
        ["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True
    )
    lifecycle.subprocess.run(
        ["git", "config", "user.email", "identity@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    lifecycle.subprocess.run(
        ["git", "config", "user.name", "Identity Test"], cwd=tmp_path, check=True
    )
    lifecycle.subprocess.run(["git", "add", "relevant/one.txt"], cwd=tmp_path, check=True)
    lifecycle.subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True)
    before = build_test_identity(
        repo_root=tmp_path,
        command=["pytest"],
        relevant_paths=["relevant"],
    )
    (tmp_path / "relevant" / "untracked.txt").write_text("new\n", encoding="utf-8")
    after = build_test_identity(
        repo_root=tmp_path,
        command=["pytest"],
        relevant_paths=["relevant"],
    )
    assert before["identity_digest"] != after["identity_digest"]


def test_writer_lease_rejects_duplicate_until_expiry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    now = datetime(2026, 7, 23, tzinfo=timezone.utc)
    monkeypatch.setattr(
        lifecycle,
        "process_identity",
        lambda pid: {
            "start_token": "token",
            "command": f"worker-{pid}",
            "cwd": str(tmp_path),
        },
    )
    lease = build_process_lease(
        lease_id="writer-one",
        task_contract=_task(tmp_path),
        pid=101,
        expected_command_substring="worker-101",
        expires_at=now + timedelta(minutes=5),
        now=now,
    )
    assert not writer_lease_available([lease], now=now)
    assert not writer_lease_available([lease], now=now + timedelta(minutes=6))


def test_expired_process_cleanup_requires_exact_pid_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    created = datetime(2026, 7, 23, tzinfo=timezone.utc)
    identity = {
        "start_token": "token",
        "command": "owned-worker-202",
        "cwd": str(tmp_path),
    }
    monkeypatch.setattr(lifecycle, "process_identity", lambda _pid: identity)
    lease = build_process_lease(
        lease_id="owned",
        task_contract=_task(tmp_path),
        pid=202,
        expected_command_substring="owned-worker",
        expires_at=created + timedelta(seconds=1),
        now=created,
    )
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(lifecycle.os, "kill", lambda pid, sig: signals.append((pid, sig)))
    closed = cleanup_expired_process_lease(
        lease,
        now=created + timedelta(seconds=2),
        terminate=True,
    )
    assert closed["status"] == "expired"
    assert signals and signals[0][0] == 202

    monkeypatch.setattr(
        lifecycle,
        "process_identity",
        lambda _pid: {
            "start_token": "different",
            "command": "owned-worker-202",
            "cwd": str(tmp_path),
        },
    )
    with pytest.raises(DevLoopLifecycleError, match="start identity changed"):
        cleanup_expired_process_lease(
            lease,
            now=created + timedelta(seconds=2),
            terminate=True,
        )

    monkeypatch.setattr(
        lifecycle,
        "process_identity",
        lambda _pid: {
            "start_token": "token",
            "command": "owned-worker-202",
            "cwd": str(tmp_path.parent),
        },
    )
    with pytest.raises(DevLoopLifecycleError, match="process cwd changed"):
        cleanup_expired_process_lease(
            lease,
            now=created + timedelta(seconds=2),
            terminate=True,
        )


def test_missing_expired_process_becomes_orphaned_and_resumable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    created = datetime(2026, 7, 23, tzinfo=timezone.utc)
    values = iter(
        [
            {
                "start_token": "token",
                "command": "owned-worker-303",
                "cwd": str(tmp_path),
            },
            None,
        ]
    )
    monkeypatch.setattr(lifecycle, "process_identity", lambda _pid: next(values))
    lease = build_process_lease(
        lease_id="orphan",
        task_contract=_task(tmp_path),
        pid=303,
        expected_command_substring="owned-worker",
        expires_at=created + timedelta(seconds=1),
        now=created,
    )
    orphaned = cleanup_expired_process_lease(
        lease, now=created + timedelta(seconds=2)
    )
    assert orphaned["status"] == "orphaned"
    resumed = resume_process_lease(orphaned, attempt=2, max_attempts=3)
    assert resumed["status"] == "resumable"
    with pytest.raises(DevLoopLifecycleError, match="attempt budget"):
        resume_process_lease(orphaned, attempt=4, max_attempts=3)


def test_active_process_lease_completion_and_missing_process_orphaning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    created = datetime(2026, 7, 23, tzinfo=timezone.utc)
    monkeypatch.setattr(
        lifecycle,
        "process_identity",
        lambda _pid: {
            "start_token": "token",
            "command": "owned-worker-404",
            "cwd": str(tmp_path),
        },
    )
    lease = build_process_lease(
        lease_id="complete",
        task_contract=_task(tmp_path),
        pid=404,
        expected_command_substring="owned-worker",
        expires_at=created + timedelta(minutes=1),
        now=created,
    )
    completed = complete_process_lease(lease, exit_code=0, now=created)
    assert completed["status"] == "completed"
    assert completed["exit_code"] == 0

    monkeypatch.setattr(lifecycle, "process_identity", lambda _pid: None)
    orphaned = mark_missing_process_orphaned(lease, now=created)
    assert orphaned["status"] == "orphaned"
    assert orphaned["process_present"] is False


def _completed_process_lease(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
) -> dict:
    monkeypatch.setattr(
        lifecycle,
        "process_identity",
        lambda _pid: {
            "start_token": "legacy-token",
            "command": "owned-worker",
            "cwd": str(repo_root),
        },
    )
    created = datetime(2026, 7, 23, tzinfo=timezone.utc)
    lease = build_process_lease(
        lease_id="legacy-complete",
        task_contract=_task(repo_root),
        pid=404,
        expected_command_substring="owned-worker",
        expires_at=created + timedelta(minutes=1),
        now=created,
    )
    return complete_process_lease(lease, exit_code=0, now=created)


def _write_process_lease(repo_root: Path, payload: dict) -> Path:
    path = repo_root / "outputs/dev-loop/compatibility/process-lease.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_completed_legacy_process_lease_is_accepted_only_after_process_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    completed = _completed_process_lease(monkeypatch, tmp_path)
    completed.pop("process_cwd")
    completed = _redigest(completed, "lease_digest")
    _write_process_lease(tmp_path, completed)

    monkeypatch.setattr(lifecycle, "process_identity", lambda _pid: None)
    leases = lifecycle._repository_process_leases(tmp_path)
    assert [(row["status"], row["lease_digest"]) for row in leases] == [
        ("completed", completed["lease_digest"])
    ]


def test_legacy_active_ambiguous_and_malformed_leases_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    completed = _completed_process_lease(monkeypatch, tmp_path)
    completed.pop("process_cwd")
    completed = _redigest(completed, "lease_digest")

    active = copy.deepcopy(completed)
    active["status"] = "active"
    active = _redigest(active, "lease_digest")
    _write_process_lease(tmp_path, active)
    monkeypatch.setattr(lifecycle, "process_identity", lambda _pid: None)
    with pytest.raises(DevLoopLifecycleError, match="not a completed historical"):
        lifecycle._repository_process_leases(tmp_path)

    _write_process_lease(tmp_path, completed)
    monkeypatch.setattr(
        lifecycle,
        "process_identity",
        lambda _pid: {
            "start_token": "legacy-token",
            "command": "owned-worker",
            "cwd": str(tmp_path),
        },
    )
    with pytest.raises(DevLoopLifecycleError, match="still matches a live process"):
        lifecycle._repository_process_leases(tmp_path)

    malformed = copy.deepcopy(completed)
    malformed.pop("heartbeat_at")
    malformed = _redigest(malformed, "lease_digest")
    _write_process_lease(tmp_path, malformed)
    monkeypatch.setattr(lifecycle, "process_identity", lambda _pid: None)
    with pytest.raises(DevLoopLifecycleError, match="malformed"):
        lifecycle._repository_process_leases(tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 17),
        ("schema_version", "sim2claw.dev_loop_process_lease.v0"),
        ("lease_id", 17),
        ("lease_id", ""),
        ("task_contract_digest", 17),
        ("task_contract_digest", "0" * 63),
        ("role", 17),
        ("role", "owner"),
        ("repository", 17),
        ("repository", "/different/repository"),
        ("pid", True),
        ("pid", 0),
        ("pid", "404"),
        ("process_start_token", 17),
        ("process_start_token", ""),
        ("expected_command_substring", 17),
        ("expected_command_substring", ""),
        ("created_at", 17),
        ("created_at", "2026-07-23T00:00:00"),
        ("heartbeat_at", 17),
        ("heartbeat_at", "not-a-time"),
        ("expires_at", 17),
        ("expires_at", "not-a-time"),
        ("status", 17),
        ("status", "active"),
        ("teardown", 17),
        ("teardown", "none"),
        ("closed_at", 17),
        ("closed_at", "not-a-time"),
        ("exit_code", False),
        ("exit_code", "0"),
    ],
)
def test_redigested_legacy_field_type_and_value_tampering_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    completed = _completed_process_lease(monkeypatch, tmp_path)
    completed.pop("process_cwd")
    completed[field] = value
    completed = _redigest(completed, "lease_digest")
    _write_process_lease(tmp_path, completed)
    monkeypatch.setattr(lifecycle, "process_identity", lambda _pid: None)
    with pytest.raises(DevLoopLifecycleError):
        lifecycle._repository_process_leases(tmp_path)


def test_legacy_completed_lease_rejects_extra_fields_bad_digest_and_time_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    completed = _completed_process_lease(monkeypatch, tmp_path)
    completed.pop("process_cwd")

    extra = {**completed, "unexpected": True}
    extra = _redigest(extra, "lease_digest")
    _write_process_lease(tmp_path, extra)
    monkeypatch.setattr(lifecycle, "process_identity", lambda _pid: None)
    with pytest.raises(DevLoopLifecycleError, match="malformed"):
        lifecycle._repository_process_leases(tmp_path)

    bad_digest = _redigest(completed, "lease_digest")
    bad_digest["lease_digest"] = "0" * 64
    _write_process_lease(tmp_path, bad_digest)
    with pytest.raises(DevLoopLifecycleError, match="digest mismatch"):
        lifecycle._repository_process_leases(tmp_path)

    inconsistent = copy.deepcopy(completed)
    inconsistent["closed_at"] = "2027-07-23T00:00:00+00:00"
    inconsistent = _redigest(inconsistent, "lease_digest")
    _write_process_lease(tmp_path, inconsistent)
    with pytest.raises(DevLoopLifecycleError, match="times are inconsistent"):
        lifecycle._repository_process_leases(tmp_path)


def test_malformed_current_process_lease_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    current = _completed_process_lease(monkeypatch, tmp_path)
    _write_process_lease(tmp_path, current)
    with pytest.raises(DevLoopLifecycleError, match="still matches a live process"):
        lifecycle._repository_process_leases(tmp_path)

    current["pid"] = "not-an-integer"
    current = _redigest(current, "lease_digest")
    _write_process_lease(tmp_path, current)
    monkeypatch.setattr(lifecycle, "process_identity", lambda _pid: None)
    with pytest.raises(ValueError, match="schema violation"):
        lifecycle._repository_process_leases(tmp_path)


def _terminal_repo(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    remote = tmp_path / "remote.git"
    plan = root / "docs/goals/plan.md"
    goal_loop = root / "docs/autonomous-workflow/goal-loop.md"
    plan.parent.mkdir(parents=True)
    goal_loop.parent.mkdir(parents=True)
    plan.write_text("# Plan\n", encoding="utf-8")
    goal_loop.write_text("# Goal loop\n", encoding="utf-8")
    state = {
        "schema_version": "sim2claw.autonomous_project_state.v1",
        "current_milestone": "D6_VERIFICATION_AND_CLOSEOUT",
        "autonomous_dev_loop": {
            "schema_version": "sim2claw.autonomous_dev_loop_state.v1",
            "status": "active",
            "plan": "docs/goals/plan.md",
            "plan_sha256": sha256_file(plan),
            "goal_loop": "docs/autonomous-workflow/goal-loop.md",
            "goal_loop_sha256": sha256_file(goal_loop),
            "branch": "main",
            "baseline_commit": "HEAD",
            "expected_remote": "origin/main",
            "state_machine": {"phase": "FULL_VERIFY", "terminal": False},
            "terminal_authority": {
                "mode": TERMINAL_AUTHORITY_MODE,
                "committed_state_may_be_terminal": False,
                "required_test_tiers": list(FINAL_REQUIRED_TEST_TIERS),
            },
            "milestones": {
                "D0": "completed",
                "D1": "completed",
                "D2": "completed",
                "D3": "completed",
                "D4": "completed",
                "D5": "completed",
                "D6": "in_progress",
            },
            "progress_ledger": {
                "remaining": list(FINAL_REMAINING_GATES),
                "next_step": "generate_terminal_packet",
                "external_readiness_blockers": {
                    "physical_measurement_and_motion": {
                        "status": "blocked_hardware_and_calibration_not_ready",
                        "physical_gateway_may_open": False,
                        "measurement_evidence_available": False,
                    }
                },
            },
            "authority": {
                "merge": True,
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
    state_path = root / "docs/autonomous-workflow/project_state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (root / "GOAL.md").write_text(
        "\n".join(
            [
                "# Goal",
                "docs/goals/plan.md",
                "docs/autonomous-workflow/goal-loop.md",
                "Current milestone: **D6 — verification**",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ledger = root / ".factory/orchestration-ledger.md"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        update_current_ledger_block(
            "# Orchestration Ledger\n",
            project_state=state,
        ),
        encoding="utf-8",
    )
    lifecycle.subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    lifecycle.subprocess.run(
        ["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True
    )
    lifecycle.subprocess.run(
        ["git", "config", "user.email", "terminal@example.invalid"],
        cwd=root,
        check=True,
    )
    lifecycle.subprocess.run(
        ["git", "config", "user.name", "Terminal Test"], cwd=root, check=True
    )
    lifecycle.subprocess.run(["git", "add", "."], cwd=root, check=True)
    lifecycle.subprocess.run(
        ["git", "commit", "-m", "verification candidate"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    lifecycle.subprocess.run(
        ["git", "remote", "add", "origin", str(remote)], cwd=root, check=True
    )
    lifecycle.subprocess.run(
        ["git", "push", "-u", "origin", "main"], cwd=root, check=True, capture_output=True
    )
    return root


def _final_test_receipts(root: Path, *, failed_tier: str | None = None) -> list[dict]:
    receipts: list[dict] = []
    for tier in FINAL_REQUIRED_TEST_TIERS:
        identity = build_test_identity(
            repo_root=root,
            command=["pytest", f"tests/{tier}.py"],
            relevant_paths=["docs/autonomous-workflow/project_state.json"],
        )
        failed = tier == failed_tier
        receipts.append(
            build_test_receipt(
                identity=identity,
                tier=tier,
                exit_code=1 if failed else 0,
                duration_seconds=1.0,
                counts={"passed": 0 if failed else 1, "failed": 1 if failed else 0},
                log_sha256="0" * 64,
            )
        )
    return receipts


def _final_review(
    root: Path,
    receipts: list[dict],
    *,
    decision: str = "PASS",
    state_sha256: str | None = None,
) -> dict:
    return build_review_receipt(
        task_contract=_task(root, role="reviewer"),
        reviewed_commit=lifecycle._git(root, "rev-parse", "HEAD"),
        decision=decision,
        findings=[
            {
                "anchor": 0 if decision == "PASS" else 100,
                "finding": "no blocking finding" if decision == "PASS" else "blocking",
            }
        ],
        test_receipt_digests=[row["receipt_digest"] for row in receipts],
        reviewed_state_sha256=state_sha256
        or sha256_file(root / "docs/autonomous-workflow/project_state.json"),
    )


def _write_final_review(root: Path, review: dict) -> str:
    path = root / CANONICAL_FINAL_REVIEW_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(review, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return CANONICAL_FINAL_REVIEW_PATH.as_posix()


def test_merge_readiness_requires_current_verified_audit_tests_and_pass_review(
    tmp_path: Path,
) -> None:
    root = _terminal_repo(tmp_path)
    receipts = _final_test_receipts(root)
    review = _final_review(root, receipts)
    review_path = _write_final_review(root, review)
    review_bytes = (root / review_path).read_bytes()
    audit = audit_dev_loop_authority(root)
    assert verify_authority_audit(audit)["status"] == "pass"
    packet = build_merge_readiness_packet(
        repo_root=root,
        authority_audit=audit,
        test_receipts=receipts,
        review_receipt_paths=[review_path],
        changed_paths=["src/sim2claw/dev_loop/lifecycle.py"],
    )
    assert packet["status"] == "merge_ready"
    assert packet["terminal_authority"] is True
    assert packet["required_test_tiers"] == list(FINAL_REQUIRED_TEST_TIERS)
    assert packet["authority"]["release"] is False
    assert (
        verify_merge_readiness_packet(packet, repo_root=root)["packet_digest"]
        == packet["packet_digest"]
    )
    assert packet["review_artifacts"] == [
        {
            "path": review_path,
            "file_sha256": sha256_file(root / review_path),
            "receipt_digest": review["receipt_digest"],
        }
    ]

    replacement = copy.deepcopy(review)
    replacement["findings"] = [
        {"anchor": 0, "finding": "different valid PASS receipt"}
    ]
    replacement = _redigest(replacement, "receipt_digest")
    _write_final_review(root, replacement)
    with pytest.raises(DevLoopLifecycleError, match="changed after packet generation"):
        verify_merge_readiness_packet(packet, repo_root=root)
    (root / review_path).write_bytes(review_bytes)
    assert verify_merge_readiness_packet(packet, repo_root=root) == packet

    state_path = root / "docs/autonomous-workflow/project_state.json"
    state_path.write_text(
        state_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DevLoopLifecycleError, match="stale"):
        verify_merge_readiness_packet(packet, repo_root=root)
    lifecycle.subprocess.run(["git", "add", str(state_path)], cwd=root, check=True)
    lifecycle.subprocess.run(
        ["git", "commit", "-m", "post-packet mutation"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    with pytest.raises(DevLoopLifecycleError, match="stale"):
        verify_merge_readiness_packet(packet, repo_root=root)


def test_merge_readiness_rejects_stop_stale_and_unverified_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = _terminal_repo(tmp_path)
    receipts = _final_test_receipts(root)
    audit = audit_dev_loop_authority(root)
    stopped = _final_review(root, receipts, decision="STOP")
    review_path = _write_final_review(root, stopped)
    packet = build_merge_readiness_packet(
        repo_root=root,
        authority_audit=audit,
        test_receipts=receipts,
        review_receipt_paths=[review_path],
        changed_paths=["src/sim2claw/dev_loop/lifecycle.py"],
    )
    assert packet["status"] == "not_ready"
    assert packet["terminal_authority"] is False

    bad_audit = copy.deepcopy(audit)
    bad_audit["audit_digest"] = "0" * 64
    with pytest.raises(DevLoopLifecycleError, match="authority audit digest mismatch"):
        build_merge_readiness_packet(
            repo_root=root,
            authority_audit=bad_audit,
            test_receipts=receipts,
            review_receipt_paths=[review_path],
            changed_paths=[],
        )

    malformed_audit = copy.deepcopy(audit)
    malformed_audit["checks"].append("not-a-check")
    malformed_audit = _redigest(malformed_audit, "audit_digest")
    with pytest.raises(DevLoopLifecycleError, match="check is malformed"):
        build_merge_readiness_packet(
            repo_root=root,
            authority_audit=malformed_audit,
            test_receipts=receipts,
            review_receipt_paths=[review_path],
            changed_paths=[],
        )

    fabricated = copy.deepcopy(audit)
    fabricated["checks"] = [
        {"name": "bogus", "passed": True, "detail": "self-asserted"}
    ]
    fabricated["active_milestone"] = "D999"
    fabricated["git_identity"]["expected_remote"] = "evil/remote"
    fabricated = _redigest(fabricated, "audit_digest")
    with pytest.raises(DevLoopLifecycleError, match="required check set changed"):
        build_merge_readiness_packet(
            repo_root=root,
            authority_audit=fabricated,
            test_receipts=receipts,
            review_receipt_paths=[review_path],
            changed_paths=[],
        )

    incomplete_review = _final_review(root, receipts[:-1])
    _write_final_review(root, incomplete_review)
    missing_tier = build_merge_readiness_packet(
        repo_root=root,
        authority_audit=audit,
        test_receipts=receipts[:-1],
        review_receipt_paths=[review_path],
        changed_paths=[],
    )
    assert missing_tier["status"] == "not_ready"

    missing_review = build_merge_readiness_packet(
        repo_root=root,
        authority_audit=audit,
        test_receipts=receipts,
        review_receipt_paths=[],
        changed_paths=[],
    )
    assert missing_review["status"] == "not_ready"

    pass_review = _final_review(root, receipts)
    _write_final_review(root, pass_review)
    with pytest.raises(ValueError, match="non-unique elements"):
        build_merge_readiness_packet(
            repo_root=root,
            authority_audit=audit,
            test_receipts=receipts,
            review_receipt_paths=[review_path, review_path],
            changed_paths=[],
        )

    with pytest.raises(ValueError, match="non-unique elements"):
        build_merge_readiness_packet(
            repo_root=root,
            authority_audit=audit,
            test_receipts=[*receipts, receipts[0]],
            review_receipt_paths=[review_path],
            changed_paths=[],
        )

    failed = _final_test_receipts(root, failed_tier="full_repository")
    _write_final_review(root, _final_review(root, failed))
    failed_packet = build_merge_readiness_packet(
        repo_root=root,
        authority_audit=audit,
        test_receipts=failed,
        review_receipt_paths=[review_path],
        changed_paths=[],
    )
    assert failed_packet["status"] == "not_ready"

    stale_review = _final_review(root, receipts, state_sha256="f" * 64)
    _write_final_review(root, stale_review)
    stale_review_packet = build_merge_readiness_packet(
        repo_root=root,
        authority_audit=audit,
        test_receipts=receipts,
        review_receipt_paths=[review_path],
        changed_paths=[],
    )
    assert stale_review_packet["status"] == "not_ready"

    lease_root = root / "outputs/dev-loop/final"
    lease_root.mkdir(parents=True)
    monkeypatch.setattr(
        lifecycle,
        "process_identity",
        lambda _pid: {
            "start_token": "test-token",
            "command": "pytest",
            "cwd": str(root),
        },
    )
    active_lease = build_process_lease(
        lease_id="still-active",
        task_contract=_task(root),
        pid=os.getpid(),
        expected_command_substring="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    (lease_root / "process-lease.json").write_text(
        json.dumps(active_lease),
        encoding="utf-8",
    )
    active_packet = build_merge_readiness_packet(
        repo_root=root,
        authority_audit=audit,
        test_receipts=receipts,
        review_receipt_paths=[
            _write_final_review(root, _final_review(root, receipts))
        ],
        changed_paths=[],
    )
    assert active_packet["status"] == "not_ready"


def test_merge_readiness_rejects_noncanonical_or_missing_review_artifact(
    tmp_path: Path,
) -> None:
    root = _terminal_repo(tmp_path)
    receipts = _final_test_receipts(root)
    audit = audit_dev_loop_authority(root)
    review = _final_review(root, receipts)
    noncanonical = root / "other-review.json"
    noncanonical.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(DevLoopLifecycleError, match="not the canonical"):
        build_merge_readiness_packet(
            repo_root=root,
            authority_audit=audit,
            test_receipts=receipts,
            review_receipt_paths=["other-review.json"],
            changed_paths=[],
        )
    with pytest.raises(DevLoopLifecycleError, match="missing"):
        build_merge_readiness_packet(
            repo_root=root,
            authority_audit=audit,
            test_receipts=receipts,
            review_receipt_paths=[CANONICAL_FINAL_REVIEW_PATH],
            changed_paths=[],
        )


@pytest.mark.parametrize("outside_root", [False, True])
def test_merge_readiness_rejects_symlinked_review_parent_for_builder_and_verifier(
    tmp_path: Path,
    outside_root: bool,
) -> None:
    root = _terminal_repo(tmp_path)
    receipts = _final_test_receipts(root)
    audit = audit_dev_loop_authority(root)
    review_path = _write_final_review(root, _final_review(root, receipts))
    packet = build_merge_readiness_packet(
        repo_root=root,
        authority_audit=audit,
        test_receipts=receipts,
        review_receipt_paths=[review_path],
        changed_paths=[],
    )
    canonical_parent = (root / CANONICAL_FINAL_REVIEW_PATH).parent
    relocated_parent = (
        tmp_path / "outside-final-review"
        if outside_root
        else root / "other-final-review"
    )
    canonical_parent.rename(relocated_parent)
    canonical_parent.symlink_to(relocated_parent, target_is_directory=True)

    with pytest.raises(DevLoopLifecycleError, match="symlink component"):
        build_merge_readiness_packet(
            repo_root=root,
            authority_audit=audit,
            test_receipts=receipts,
            review_receipt_paths=[review_path],
            changed_paths=[],
        )
    with pytest.raises(DevLoopLifecycleError, match="symlink component"):
        verify_merge_readiness_packet(packet, repo_root=root)
