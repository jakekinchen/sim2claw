"""Receipt-gated task, test, review, process, and closeout lifecycle."""

from __future__ import annotations

import copy
import hashlib
import os
import platform
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..learning_factory_artifacts import canonical_digest, sha256_file
from .contracts import validate_dev_loop_artifact
from .state import AUDIT_SCHEMA


TASK_SCHEMA = "sim2claw.dev_loop_task_contract.v1"
REVIEW_SCHEMA = "sim2claw.dev_loop_review_receipt.v1"
TEST_SCHEMA = "sim2claw.dev_loop_test_receipt.v1"
PROCESS_SCHEMA = "sim2claw.dev_loop_process_lease.v1"
MERGE_SCHEMA = "sim2claw.dev_loop_merge_readiness.v1"
REQUIRED_AUTHORITY_AUDIT_CHECKS = {
    "authority",
    "baseline_ancestry",
    "branch",
    "canonical_state",
    "goal_alignment",
    "goal_identity",
    "no_shadow_current_state",
    "plan_identity",
    "remote",
    "rendered_ledger",
}

EXTERNAL_AUTHORITY_FIELDS = (
    "release",
    "provider",
    "paid_compute",
    "training",
    "simulator_campaign",
    "simulator_promotion",
    "physical_capture",
    "robot_gateway",
    "robot_motion",
)
IGNORED_IDENTITY_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}


class DevLoopLifecycleError(ValueError):
    """A lifecycle artifact failed identity, lease, or authority checks."""


def _utc(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def _parse_time(value: object, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise DevLoopLifecycleError(f"invalid {label}") from error
    if parsed.tzinfo is None:
        raise DevLoopLifecycleError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _relative_paths(repo_root: Path, values: Sequence[Path | str]) -> list[str]:
    root = repo_root.resolve()
    result: list[str] = []
    for value in values:
        raw = Path(value)
        resolved = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        if resolved != root and root not in resolved.parents:
            raise DevLoopLifecycleError("allowed path escapes repository")
        relative = resolved.relative_to(root).as_posix()
        if relative in result:
            raise DevLoopLifecycleError("duplicate allowed path")
        result.append(relative)
    if not result:
        raise DevLoopLifecycleError("task contract requires allowed paths")
    return sorted(result)


def _authority(value: Mapping[str, Any] | None = None) -> dict[str, bool]:
    supplied = dict(value or {})
    normalized = {
        "commit": bool(supplied.get("commit", False)),
        "push_origin_main": bool(supplied.get("push_origin_main", False)),
        **{name: bool(supplied.get(name, False)) for name in EXTERNAL_AUTHORITY_FIELDS},
    }
    if any(normalized[name] for name in EXTERNAL_AUTHORITY_FIELDS):
        raise DevLoopLifecycleError("task widened external authority")
    return normalized


def _verify_authority(
    value: object, *, repository_write_allowed: bool, label: str
) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        raise DevLoopLifecycleError(f"{label} authority is missing")
    normalized = _authority(value)
    if dict(value) != normalized:
        raise DevLoopLifecycleError(f"{label} authority fields changed")
    expected = bool(repository_write_allowed)
    if normalized["commit"] is not expected or normalized["push_origin_main"] is not expected:
        raise DevLoopLifecycleError(f"{label} repository-write authority is invalid")
    return normalized


def _with_digest(unsigned: Mapping[str, Any], field: str) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(unsigned))
    return {**normalized, field: canonical_digest(normalized)}


def _verify_digest(payload: Mapping[str, Any], field: str, *, label: str) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(payload))
    observed = normalized.pop(field, None)
    expected = canonical_digest(normalized)
    if observed != expected:
        raise DevLoopLifecycleError(f"{label} digest mismatch")
    return {**normalized, field: str(observed)}


def build_task_contract(
    *,
    task_id: str,
    role: str,
    repo_root: Path,
    branch: str,
    base_commit: str,
    allowed_paths: Sequence[Path | str],
    allowed_operations: Sequence[str],
    proof_target: str,
    max_attempts: int = 3,
    wall_time_seconds: int = 3600,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    if not task_id.strip() or role not in {"executor", "reviewer", "manager"}:
        raise DevLoopLifecycleError("invalid task identity or role")
    operations = sorted({str(value) for value in allowed_operations if str(value)})
    if not operations:
        raise DevLoopLifecycleError("task contract requires allowed operations")
    if role != "executor" and {"write", "commit", "push", "write_receipts"} & set(operations):
        raise DevLoopLifecycleError("non-executor task requested writer operations")
    if max_attempts < 1 or wall_time_seconds < 1:
        raise DevLoopLifecycleError("task bounds must be positive")
    unsigned = {
        "schema_version": TASK_SCHEMA,
        "task_id": task_id,
        "role": role,
        "repository": str(repo_root.resolve()),
        "branch": branch,
        "base_commit": base_commit,
        "allowed_paths": _relative_paths(repo_root, allowed_paths),
        "allowed_operations": operations,
        "proof_target": proof_target,
        "max_attempts": int(max_attempts),
        "wall_time_seconds": int(wall_time_seconds),
        "created_at": _utc(created_at),
        "authority": _authority(
            {
                "commit": role == "executor",
                "push_origin_main": role == "executor",
            }
        ),
    }
    return _with_digest(unsigned, "contract_digest")


def verify_task_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    verified = _verify_digest(payload, "contract_digest", label="task contract")
    if verified.get("schema_version") != TASK_SCHEMA:
        raise DevLoopLifecycleError("unexpected task contract schema")
    _verify_authority(
        verified.get("authority"),
        repository_write_allowed=verified.get("role") == "executor",
        label="task contract",
    )
    if not verified.get("allowed_paths") or not verified.get("allowed_operations"):
        raise DevLoopLifecycleError("task contract scope is empty")
    return validate_dev_loop_artifact("task", verified)


def build_review_receipt(
    *,
    task_contract: Mapping[str, Any],
    reviewed_commit: str,
    decision: str,
    findings: Sequence[Mapping[str, Any]],
    test_receipt_digests: Sequence[str],
) -> dict[str, Any]:
    task = verify_task_contract(task_contract)
    if task["role"] != "reviewer":
        raise DevLoopLifecycleError("review receipt requires a reviewer contract")
    if decision not in {"CONTINUE", "NUDGE", "REDIRECT", "STOP", "ESCALATE", "PASS"}:
        raise DevLoopLifecycleError("invalid review decision")
    rows = [copy.deepcopy(dict(row)) for row in findings]
    for row in rows:
        if row.get("anchor") not in {0, 25, 50, 75, 100}:
            raise DevLoopLifecycleError("review finding has invalid evidence anchor")
    unsigned = {
        "schema_version": REVIEW_SCHEMA,
        "task_contract_digest": task["contract_digest"],
        "reviewed_commit": reviewed_commit,
        "decision": decision,
        "findings": rows,
        "test_receipt_digests": sorted({str(value) for value in test_receipt_digests}),
        "authority": _authority({"commit": False, "push_origin_main": False}),
    }
    return _with_digest(unsigned, "receipt_digest")


def verify_review_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    verified = _verify_digest(payload, "receipt_digest", label="review receipt")
    if verified.get("schema_version") != REVIEW_SCHEMA:
        raise DevLoopLifecycleError("unexpected review receipt schema")
    _verify_authority(
        verified.get("authority"),
        repository_write_allowed=False,
        label="review receipt",
    )
    return validate_dev_loop_artifact("review", verified)


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise DevLoopLifecycleError(f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def _path_content_identity(path: Path) -> dict[str, Any]:
    if path.is_file():
        return {"kind": "file", "sha256": sha256_file(path)}
    if path.is_dir():
        files: dict[str, str] = {}
        for candidate in sorted(path.rglob("*")):
            relative = candidate.relative_to(path)
            if any(part in IGNORED_IDENTITY_PARTS for part in relative.parts):
                continue
            if candidate.is_file() and candidate.suffix != ".pyc":
                files[relative.as_posix()] = sha256_file(candidate)
        return {
            "kind": "directory",
            "file_count": len(files),
            "digest": canonical_digest(files),
        }
    return {"kind": "missing"}


def build_test_identity(
    *,
    repo_root: Path,
    command: Sequence[str],
    relevant_paths: Sequence[Path | str],
) -> dict[str, Any]:
    root = repo_root.resolve()
    if not command:
        raise DevLoopLifecycleError("test command is empty")
    relative_paths = _relative_paths(root, relevant_paths)
    path_hashes: dict[str, dict[str, Any]] = {}
    for relative in relative_paths:
        path = root / relative
        path_hashes[relative] = _path_content_identity(path)
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", *relative_paths],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if diff.returncode != 0:
        raise DevLoopLifecycleError("cannot compute relevant diff identity")
    dependencies = {}
    for relative in ("pyproject.toml", "uv.lock"):
        path = root / relative
        dependencies[relative] = sha256_file(path) if path.is_file() else None
    unsigned = {
        "commit": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "branch": _git(root, "branch", "--show-current"),
        "command": [str(value) for value in command],
        "relevant_paths": path_hashes,
        "relevant_diff_sha256": hashlib.sha256(diff.stdout).hexdigest(),
        "dependencies": dependencies,
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": str(Path(sys.executable).resolve()),
            "platform": platform.platform(),
        },
    }
    return {**unsigned, "identity_digest": canonical_digest(unsigned)}


def build_test_receipt(
    *,
    identity: Mapping[str, Any],
    tier: str,
    exit_code: int,
    duration_seconds: float,
    counts: Mapping[str, int],
    log_sha256: str,
) -> dict[str, Any]:
    if canonical_digest({k: v for k, v in identity.items() if k != "identity_digest"}) != identity.get("identity_digest"):
        raise DevLoopLifecycleError("test identity digest mismatch")
    if duration_seconds < 0 or any(int(value) < 0 for value in counts.values()):
        raise DevLoopLifecycleError("invalid test result metrics")
    unsigned = {
        "schema_version": TEST_SCHEMA,
        "identity": copy.deepcopy(dict(identity)),
        "tier": tier,
        "exit_code": int(exit_code),
        "duration_seconds": float(duration_seconds),
        "counts": {str(key): int(value) for key, value in sorted(counts.items())},
        "log_sha256": log_sha256,
        "status": "pass" if exit_code == 0 else "fail",
        "authority": _authority({"commit": False, "push_origin_main": False}),
    }
    return _with_digest(unsigned, "receipt_digest")


def verify_test_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    verified = _verify_digest(payload, "receipt_digest", label="test receipt")
    if verified.get("schema_version") != TEST_SCHEMA:
        raise DevLoopLifecycleError("unexpected test receipt schema")
    identity = verified.get("identity")
    if not isinstance(identity, dict):
        raise DevLoopLifecycleError("test receipt identity is missing")
    observed_identity = identity.get("identity_digest")
    unsigned_identity = {key: value for key, value in identity.items() if key != "identity_digest"}
    if observed_identity != canonical_digest(unsigned_identity):
        raise DevLoopLifecycleError("test receipt identity changed")
    _verify_authority(
        verified.get("authority"),
        repository_write_allowed=False,
        label="test receipt",
    )
    return validate_dev_loop_artifact("test", verified)


def is_test_receipt_reusable(payload: Mapping[str, Any], identity: Mapping[str, Any]) -> bool:
    try:
        verified = verify_test_receipt(payload)
    except DevLoopLifecycleError:
        return False
    return (
        verified["exit_code"] == 0
        and verified["status"] == "pass"
        and verified["identity"]["identity_digest"] == identity.get("identity_digest")
    )


def _process_cwd(pid: int) -> str | None:
    proc_cwd = Path(f"/proc/{pid}/cwd")
    if proc_cwd.exists():
        try:
            return str(proc_cwd.resolve(strict=True))
        except OSError:
            return None
    try:
        completed = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    for line in completed.stdout.splitlines():
        if line.startswith("n") and len(line) > 1:
            return str(Path(line[1:]).resolve())
    return None


def _cwd_owned_by_repository(cwd: object, repository: object) -> bool:
    current = Path(str(cwd)).resolve()
    root = Path(str(repository)).resolve()
    return current == root or root in current.parents


def process_identity(pid: int) -> dict[str, str] | None:
    completed = subprocess.run(
        ["ps", "-o", "lstart=", "-o", "command=", "-p", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    )
    line = completed.stdout.strip()
    if completed.returncode != 0 or not line:
        return None
    parts = line.split(None, 5)
    if len(parts) < 6:
        raise DevLoopLifecycleError("cannot parse process start identity")
    cwd = _process_cwd(pid)
    if cwd is None:
        raise DevLoopLifecycleError("cannot verify process repository ownership")
    return {
        "start_token": " ".join(parts[:5]),
        "command": parts[5],
        "cwd": cwd,
    }


def build_process_lease(
    *,
    lease_id: str,
    task_contract: Mapping[str, Any],
    pid: int,
    expected_command_substring: str,
    expires_at: datetime,
    now: datetime | None = None,
) -> dict[str, Any]:
    task = verify_task_contract(task_contract)
    identity = process_identity(pid)
    if (
        identity is None
        or expected_command_substring not in identity["command"]
        or not _cwd_owned_by_repository(identity.get("cwd"), task["repository"])
    ):
        raise DevLoopLifecycleError("process identity does not match requested lease")
    created = now or datetime.now(timezone.utc)
    if expires_at.astimezone(timezone.utc) <= created.astimezone(timezone.utc):
        raise DevLoopLifecycleError("process lease must expire in the future")
    unsigned = {
        "schema_version": PROCESS_SCHEMA,
        "lease_id": lease_id,
        "task_contract_digest": task["contract_digest"],
        "role": task["role"],
        "repository": task["repository"],
        "pid": int(pid),
        "process_start_token": identity["start_token"],
        "process_cwd": identity["cwd"],
        "expected_command_substring": expected_command_substring,
        "created_at": _utc(created),
        "heartbeat_at": _utc(created),
        "expires_at": _utc(expires_at),
        "status": "active",
        "teardown": "terminate_after_verified_identity_on_expiry",
    }
    return _with_digest(unsigned, "lease_digest")


def verify_process_lease(payload: Mapping[str, Any]) -> dict[str, Any]:
    verified = _verify_digest(payload, "lease_digest", label="process lease")
    if verified.get("schema_version") != PROCESS_SCHEMA:
        raise DevLoopLifecycleError("unexpected process lease schema")
    _parse_time(verified.get("created_at"), label="process lease creation")
    _parse_time(verified.get("expires_at"), label="process lease expiry")
    if verified.get("status") not in {"active", "completed", "expired", "orphaned", "resumable"}:
        raise DevLoopLifecycleError("invalid process lease status")
    return validate_dev_loop_artifact("process", verified)


def writer_lease_available(
    leases: Sequence[Mapping[str, Any]], *, now: datetime | None = None
) -> bool:
    del now
    for payload in leases:
        lease = verify_process_lease(payload)
        if lease["role"] == "executor" and lease["status"] == "active":
            return False
    return True


def cleanup_expired_process_lease(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
    terminate: bool = False,
) -> dict[str, Any]:
    lease = verify_process_lease(payload)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if lease["status"] != "active":
        return lease
    if _parse_time(lease["expires_at"], label="process lease expiry") > current:
        raise DevLoopLifecycleError("process lease has not expired")
    identity = process_identity(int(lease["pid"]))
    if identity is None:
        unsigned = {key: value for key, value in lease.items() if key != "lease_digest"}
        unsigned.update(status="orphaned", closed_at=_utc(current), process_present=False)
        return _with_digest(unsigned, "lease_digest")
    if identity["start_token"] != lease["process_start_token"]:
        raise DevLoopLifecycleError("refusing cleanup because PID start identity changed")
    if lease["expected_command_substring"] not in identity["command"]:
        raise DevLoopLifecycleError("refusing cleanup because process command changed")
    if identity.get("cwd") != lease["process_cwd"]:
        raise DevLoopLifecycleError("refusing cleanup because process cwd changed")
    if not _cwd_owned_by_repository(identity["cwd"], lease["repository"]):
        raise DevLoopLifecycleError("refusing cleanup because repository ownership changed")
    if terminate:
        os.kill(int(lease["pid"]), signal.SIGTERM)
    unsigned = {key: value for key, value in lease.items() if key != "lease_digest"}
    unsigned.update(
        status="expired",
        closed_at=_utc(current),
        process_present=True,
        termination_requested=bool(terminate),
    )
    return _with_digest(unsigned, "lease_digest")


def resume_process_lease(
    payload: Mapping[str, Any], *, attempt: int, max_attempts: int
) -> dict[str, Any]:
    lease = verify_process_lease(payload)
    if lease["status"] not in {"orphaned", "expired", "resumable"}:
        raise DevLoopLifecycleError("only closed or resumable leases may resume")
    if attempt < 1 or attempt > max_attempts:
        raise DevLoopLifecycleError("process resume exceeds attempt budget")
    unsigned = {key: value for key, value in lease.items() if key != "lease_digest"}
    unsigned.update(status="resumable", resume_attempt=attempt, max_attempts=max_attempts)
    return _with_digest(unsigned, "lease_digest")


def complete_process_lease(
    payload: Mapping[str, Any], *, exit_code: int, now: datetime | None = None
) -> dict[str, Any]:
    lease = verify_process_lease(payload)
    if lease["status"] != "active":
        raise DevLoopLifecycleError("only an active process lease may complete")
    unsigned = {key: value for key, value in lease.items() if key != "lease_digest"}
    unsigned.update(
        status="completed",
        closed_at=_utc(now),
        exit_code=int(exit_code),
    )
    return _with_digest(unsigned, "lease_digest")


def mark_missing_process_orphaned(
    payload: Mapping[str, Any], *, now: datetime | None = None
) -> dict[str, Any]:
    lease = verify_process_lease(payload)
    if lease["status"] != "active":
        return lease
    if process_identity(int(lease["pid"])) is not None:
        raise DevLoopLifecycleError("active leased process is still present")
    unsigned = {key: value for key, value in lease.items() if key != "lease_digest"}
    unsigned.update(
        status="orphaned",
        closed_at=_utc(now),
        process_present=False,
    )
    return _with_digest(unsigned, "lease_digest")


def verify_authority_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    verified = _verify_digest(payload, "audit_digest", label="authority audit")
    if verified.get("schema_version") != AUDIT_SCHEMA:
        raise DevLoopLifecycleError("unexpected authority audit schema")
    if verified.get("status") not in {"pass", "fail"}:
        raise DevLoopLifecycleError("invalid authority audit status")
    if verified.get("proof_class") != "deterministic_repository_authority_consistency":
        raise DevLoopLifecycleError("invalid authority audit proof class")
    if not isinstance(verified.get("active_milestone"), str):
        raise DevLoopLifecycleError("authority audit milestone is missing")
    checks = verified.get("checks")
    if not isinstance(checks, list) or not checks:
        raise DevLoopLifecycleError("authority audit checks are missing")
    for row in checks:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("passed"), bool)
            or not isinstance(row.get("detail"), str)
        ):
            raise DevLoopLifecycleError("authority audit check is malformed")
    check_names = [str(row["name"]) for row in checks]
    if len(check_names) != len(set(check_names)) or set(check_names) != REQUIRED_AUTHORITY_AUDIT_CHECKS:
        raise DevLoopLifecycleError("authority audit required check set changed")
    all_passed = all(row["passed"] for row in checks)
    if (verified["status"] == "pass") is not all_passed:
        raise DevLoopLifecycleError("authority audit status contradicts its checks")
    git_identity = verified.get("git_identity")
    if not isinstance(git_identity, dict):
        raise DevLoopLifecycleError("authority audit git identity is missing")
    for field in ("branch", "head", "remote", "expected_remote"):
        if not isinstance(git_identity.get(field), str) or not git_identity[field]:
            raise DevLoopLifecycleError("authority audit git identity is malformed")
    authority = verified.get("authority")
    if not isinstance(authority, dict):
        raise DevLoopLifecycleError("authority audit authority is missing")
    prohibited = (*EXTERNAL_AUTHORITY_FIELDS, "history_rewrite")
    if any(authority.get(name) is not False for name in prohibited):
        raise DevLoopLifecycleError("authority audit widened external authority")
    if verified["active_milestone"] not in {f"D{index}" for index in range(7)}:
        raise DevLoopLifecycleError("authority audit milestone is not permitted")
    return verified


def build_merge_readiness_packet(
    *,
    branch: str,
    head: str,
    remote_head: str,
    authority_audit: Mapping[str, Any],
    test_receipts: Sequence[Mapping[str, Any]],
    review_receipts: Sequence[Mapping[str, Any]],
    changed_paths: Sequence[str],
) -> dict[str, Any]:
    audit = verify_authority_audit(authority_audit)
    tests = [verify_test_receipt(value) for value in test_receipts]
    reviews = [verify_review_receipt(value) for value in review_receipts]
    audit_git = audit["git_identity"]
    audit_pass = (
        audit["status"] == "pass"
        and all(row["passed"] for row in audit["checks"])
        and audit_git["branch"] == branch
        and audit_git["head"] == head
        and audit_git["remote"] == remote_head
        and audit_git["expected_remote"] == "origin/main"
        and audit["active_milestone"] == "D6"
        and audit["authority"].get("merge") is True
        and audit["authority"].get("push_origin_main") is True
        and audit["authority"].get("prior_sail_fast_forward_completed") is True
    )
    tests_pass = bool(tests) and all(
        row["status"] == "pass"
        and row["identity"]["commit"] == head
        and row["identity"]["branch"] == branch
        for row in tests
    )
    test_digests = {row["receipt_digest"] for row in tests}
    reviewed_test_digests = {
        digest for row in reviews for digest in row["test_receipt_digests"]
    }
    reviews_pass = (
        bool(reviews)
        and all(
            row["decision"] == "PASS"
            and row["reviewed_commit"] == head
            and bool(row["test_receipt_digests"])
            and set(row["test_receipt_digests"]) <= test_digests
            for row in reviews
        )
        and test_digests <= reviewed_test_digests
    )
    ready = branch == "main" and head == remote_head and audit_pass and tests_pass and reviews_pass
    unsigned = {
        "schema_version": MERGE_SCHEMA,
        "status": "merge_ready" if ready else "not_ready",
        "branch": branch,
        "head": head,
        "remote_head": remote_head,
        "authority_audit_digest": audit["audit_digest"],
        "test_receipt_digests": [row["receipt_digest"] for row in tests],
        "review_receipt_digests": [row["receipt_digest"] for row in reviews],
        "changed_paths": sorted({str(value) for value in changed_paths}),
        "authority": _authority({"commit": False, "push_origin_main": False}),
        "owner_gates": ["release_or_publication_beyond_repository_push"],
        "proof_class": "deterministic_repository_merge_readiness_no_release_authority",
    }
    return validate_dev_loop_artifact("merge", _with_digest(unsigned, "packet_digest"))


def verify_merge_readiness_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    verified = _verify_digest(payload, "packet_digest", label="merge readiness")
    if verified.get("schema_version") != MERGE_SCHEMA:
        raise DevLoopLifecycleError("unexpected merge-readiness schema")
    _verify_authority(
        verified.get("authority"),
        repository_write_allowed=False,
        label="merge readiness",
    )
    return validate_dev_loop_artifact("merge", verified)


__all__ = [
    "DevLoopLifecycleError",
    "MERGE_SCHEMA",
    "PROCESS_SCHEMA",
    "REQUIRED_AUTHORITY_AUDIT_CHECKS",
    "REVIEW_SCHEMA",
    "TASK_SCHEMA",
    "TEST_SCHEMA",
    "build_merge_readiness_packet",
    "build_process_lease",
    "build_review_receipt",
    "build_task_contract",
    "build_test_identity",
    "build_test_receipt",
    "cleanup_expired_process_lease",
    "complete_process_lease",
    "mark_missing_process_orphaned",
    "process_identity",
    "resume_process_lease",
    "is_test_receipt_reusable",
    "verify_process_lease",
    "verify_authority_audit",
    "verify_merge_readiness_packet",
    "verify_review_receipt",
    "verify_task_contract",
    "verify_test_receipt",
    "writer_lease_available",
]
