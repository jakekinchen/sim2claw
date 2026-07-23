from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sim2claw.dev_loop import lifecycle
from sim2claw.dev_loop.contracts import SCHEMA_PATHS, load_dev_loop_schema
from sim2claw.dev_loop.lifecycle import (
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
from sim2claw.learning_factory_artifacts import canonical_digest


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


def _authority_audit(*, head: str, branch: str = "main") -> dict:
    unsigned = {
        "schema_version": "sim2claw.autonomous_dev_loop_authority_audit.v1",
        "status": "pass",
        "proof_class": "deterministic_repository_authority_consistency",
        "active_milestone": "D6",
        "git_identity": {
            "branch": branch,
            "head": head,
            "remote": head,
            "expected_remote": "origin/main",
        },
        "checks": [
            {"name": name, "passed": True, "detail": "ok"}
            for name in sorted(REQUIRED_AUTHORITY_AUDIT_CHECKS)
        ],
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
    }
    return {**unsigned, "audit_digest": canonical_digest(unsigned)}


def test_merge_readiness_requires_current_verified_audit_tests_and_pass_review(
    tmp_path: Path,
) -> None:
    identity = _identity()
    head = identity["commit"]
    test_receipt = _test_receipt(identity)
    reviewer = _task(tmp_path, role="reviewer")
    review = build_review_receipt(
        task_contract=reviewer,
        reviewed_commit=head,
        decision="PASS",
        findings=[{"anchor": 0, "finding": "no blocking finding"}],
        test_receipt_digests=[test_receipt["receipt_digest"]],
    )
    audit = _authority_audit(head=head)
    assert verify_authority_audit(audit)["status"] == "pass"
    packet = build_merge_readiness_packet(
        branch="main",
        head=head,
        remote_head=head,
        authority_audit=audit,
        test_receipts=[test_receipt],
        review_receipts=[review],
        changed_paths=["src/sim2claw/dev_loop/lifecycle.py"],
    )
    assert packet["status"] == "merge_ready"
    assert packet["authority"]["release"] is False
    assert verify_merge_readiness_packet(packet)["packet_digest"] == packet["packet_digest"]

    not_ready = build_merge_readiness_packet(
        branch="main",
        head=head,
        remote_head="other",
        authority_audit=audit,
        test_receipts=[test_receipt],
        review_receipts=[review],
        changed_paths=[],
    )
    assert not_ready["status"] == "not_ready"


def test_merge_readiness_rejects_stop_stale_and_unverified_evidence(
    tmp_path: Path,
) -> None:
    identity = _identity()
    head = identity["commit"]
    test_receipt = _test_receipt(identity)
    reviewer = _task(tmp_path, role="reviewer")
    stopped = build_review_receipt(
        task_contract=reviewer,
        reviewed_commit=head,
        decision="STOP",
        findings=[{"anchor": 100, "finding": "blocking"}],
        test_receipt_digests=[test_receipt["receipt_digest"]],
    )
    packet = build_merge_readiness_packet(
        branch="main",
        head=head,
        remote_head=head,
        authority_audit=_authority_audit(head=head),
        test_receipts=[test_receipt],
        review_receipts=[stopped],
        changed_paths=["src/sim2claw/dev_loop/lifecycle.py"],
    )
    assert packet["status"] == "not_ready"

    bad_audit = _authority_audit(head=head)
    bad_audit["audit_digest"] = "0" * 64
    with pytest.raises(DevLoopLifecycleError, match="authority audit digest mismatch"):
        build_merge_readiness_packet(
            branch="main",
            head=head,
            remote_head=head,
            authority_audit=bad_audit,
            test_receipts=[test_receipt],
            review_receipts=[stopped],
            changed_paths=[],
        )

    malformed_audit = _authority_audit(head=head)
    malformed_audit["checks"].append("not-a-check")
    malformed_audit = _redigest(malformed_audit, "audit_digest")
    with pytest.raises(DevLoopLifecycleError, match="check is malformed"):
        build_merge_readiness_packet(
            branch="main",
            head=head,
            remote_head=head,
            authority_audit=malformed_audit,
            test_receipts=[test_receipt],
            review_receipts=[stopped],
            changed_paths=[],
        )

    fabricated = _authority_audit(head=head)
    fabricated["checks"] = [
        {"name": "bogus", "passed": True, "detail": "self-asserted"}
    ]
    fabricated["active_milestone"] = "D999"
    fabricated["git_identity"]["expected_remote"] = "evil/remote"
    fabricated = _redigest(fabricated, "audit_digest")
    with pytest.raises(DevLoopLifecycleError, match="required check set changed"):
        build_merge_readiness_packet(
            branch="main",
            head=head,
            remote_head=head,
            authority_audit=fabricated,
            test_receipts=[test_receipt],
            review_receipts=[stopped],
            changed_paths=[],
        )

    wrong_gate = _authority_audit(head=head)
    wrong_gate["active_milestone"] = "D5"
    wrong_gate["git_identity"]["expected_remote"] = "evil/remote"
    wrong_gate = _redigest(wrong_gate, "audit_digest")
    wrong_gate_packet = build_merge_readiness_packet(
        branch="main",
        head=head,
        remote_head=head,
        authority_audit=wrong_gate,
        test_receipts=[test_receipt],
        review_receipts=[stopped],
        changed_paths=[],
    )
    assert wrong_gate_packet["status"] == "not_ready"

    stale = build_merge_readiness_packet(
        branch="main",
        head="f" * 40,
        remote_head="f" * 40,
        authority_audit=_authority_audit(head="f" * 40),
        test_receipts=[test_receipt],
        review_receipts=[stopped],
        changed_paths=[],
    )
    assert stale["status"] == "not_ready"
