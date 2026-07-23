"""Receipt-gated task, test, review, process, and closeout lifecycle."""

from __future__ import annotations

import copy
import hashlib
import json
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
from .state import (
    AUDIT_SCHEMA,
    FINAL_REMAINING_GATES,
    FINAL_REQUIRED_TEST_TIERS,
    TERMINAL_AUTHORITY_MODE,
    validate_dev_loop_state,
)


TASK_SCHEMA = "sim2claw.dev_loop_task_contract.v1"
REVIEW_SCHEMA = "sim2claw.dev_loop_review_receipt.v2"
TEST_SCHEMA = "sim2claw.dev_loop_test_receipt.v1"
PROCESS_SCHEMA = "sim2claw.dev_loop_process_lease.v1"
MERGE_SCHEMA = "sim2claw.dev_loop_merge_readiness.v2"
CANONICAL_FINAL_REVIEW_PATH = Path(
    "outputs/dev-loop/final-review/review-receipt.json"
)
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
    reviewed_state_sha256: str,
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
    if len(reviewed_state_sha256) != 64:
        raise DevLoopLifecycleError("reviewed project-state identity is invalid")
    unsigned = {
        "schema_version": REVIEW_SCHEMA,
        "task_contract_digest": task["contract_digest"],
        "reviewed_commit": reviewed_commit,
        "decision": decision,
        "findings": rows,
        "test_receipt_digests": sorted({str(value) for value in test_receipt_digests}),
        "reviewed_state_sha256": reviewed_state_sha256,
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
    state_sha256 = verified.get("reviewed_state_sha256")
    if not isinstance(state_sha256, str) or len(state_sha256) != 64:
        raise DevLoopLifecycleError("review receipt project-state identity is invalid")
    return validate_dev_loop_artifact("review", verified)


def _load_canonical_review_artifact(
    repo_root: Path, value: Path | str
) -> tuple[dict[str, Any], dict[str, str]]:
    raw_path = Path(value)
    if (
        raw_path.is_absolute()
        or raw_path.as_posix() != CANONICAL_FINAL_REVIEW_PATH.as_posix()
    ):
        raise DevLoopLifecycleError(
            "review receipt path is not the canonical reviewer artifact"
        )
    path = repo_root / CANONICAL_FINAL_REVIEW_PATH
    if path.is_symlink() or not path.is_file():
        raise DevLoopLifecycleError(
            "canonical reviewer artifact is missing or not a regular file"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DevLoopLifecycleError(
            "canonical reviewer artifact is unreadable"
        ) from error
    if not isinstance(payload, Mapping):
        raise DevLoopLifecycleError("canonical reviewer artifact is not an object")
    receipt = verify_review_receipt(payload)
    return receipt, {
        "path": CANONICAL_FINAL_REVIEW_PATH.as_posix(),
        "file_sha256": sha256_file(path),
        "receipt_digest": receipt["receipt_digest"],
    }


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


def _project_state_identity(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    path = root / "docs/autonomous-workflow/project_state.json"
    try:
        project_state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DevLoopLifecycleError("cannot read canonical project state") from error
    if not isinstance(project_state, dict):
        raise DevLoopLifecycleError("canonical project state is not an object")
    try:
        validated = validate_dev_loop_state(project_state, repo_root=root)
    except ValueError as error:
        raise DevLoopLifecycleError(str(error)) from error
    dev_state = validated["autonomous_dev_loop"]
    return {
        "path": "docs/autonomous-workflow/project_state.json",
        "sha256": sha256_file(path),
        "digest": canonical_digest(validated),
        "semantics": {
            "status": dev_state["status"],
            "phase": dev_state["state_machine"]["phase"],
            "terminal": dev_state["state_machine"]["terminal"],
            "d6_status": dev_state["milestones"]["D6"],
            "remaining": list(dev_state["progress_ledger"]["remaining"]),
            "terminal_authority_mode": dev_state["terminal_authority"]["mode"],
        },
    }


def _candidate_state_semantics(value: object) -> bool:
    return value == {
        "status": "active",
        "phase": "FULL_VERIFY",
        "terminal": False,
        "d6_status": "in_progress",
        "remaining": list(FINAL_REMAINING_GATES),
        "terminal_authority_mode": TERMINAL_AUTHORITY_MODE,
    }


def _repository_process_leases(repo_root: Path) -> list[dict[str, Any]]:
    lease_root = repo_root.resolve() / "outputs/dev-loop"
    if not lease_root.is_dir():
        return []
    leases: list[dict[str, Any]] = []
    for path in sorted(lease_root.rglob("process-lease.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DevLoopLifecycleError(f"cannot read process lease {path}") from error
        if not isinstance(payload, dict):
            raise DevLoopLifecycleError(f"process lease is not an object: {path}")
        if "process_cwd" in payload:
            lease = verify_process_lease(payload)
        else:
            lease = _verify_legacy_completed_process_lease(
                payload,
                repo_root=repo_root,
            )
        if lease["status"] != "active":
            identity = process_identity(int(lease["pid"]))
            if (
                identity is not None
                and identity["start_token"] == lease["process_start_token"]
            ):
                raise DevLoopLifecycleError(
                    f"closed process lease still matches a live process: {path}"
                )
        leases.append(lease)
    return leases


def _verify_legacy_completed_process_lease(
    payload: Mapping[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    """Accept only a closed pre-process_cwd lease whose process is no longer live."""

    verified = _verify_digest(
        payload,
        "lease_digest",
        label="legacy completed process lease",
    )
    required = {
        "schema_version",
        "lease_id",
        "task_contract_digest",
        "role",
        "repository",
        "pid",
        "process_start_token",
        "expected_command_substring",
        "created_at",
        "heartbeat_at",
        "expires_at",
        "status",
        "teardown",
        "closed_at",
        "exit_code",
        "lease_digest",
    }
    if (
        verified.get("schema_version") != PROCESS_SCHEMA
        or verified.get("status") != "completed"
    ):
        raise DevLoopLifecycleError(
            "legacy process lease is not a completed historical lease"
        )
    nonempty_strings = (
        "lease_id",
        "process_start_token",
        "expected_command_substring",
        "created_at",
        "heartbeat_at",
        "expires_at",
        "closed_at",
    )
    if set(verified) != required or any(
        not isinstance(verified.get(field), str) or not verified[field]
        for field in nonempty_strings
    ):
        raise DevLoopLifecycleError("legacy completed process lease is malformed")
    if (
        verified.get("teardown") != "terminate_after_verified_identity_on_expiry"
        or verified.get("role") not in {"executor", "reviewer", "manager"}
        or not isinstance(verified.get("repository"), str)
        or verified["repository"] != str(repo_root.resolve())
        or type(verified.get("pid")) is not int
        or verified["pid"] < 1
        or type(verified.get("exit_code")) is not int
    ):
        raise DevLoopLifecycleError("legacy completed process lease is malformed")
    for field in ("task_contract_digest", "lease_digest"):
        value = verified.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise DevLoopLifecycleError("legacy completed process lease is malformed")
    created = _parse_time(
        verified["created_at"],
        label="legacy process lease created_at",
    )
    heartbeat = _parse_time(
        verified["heartbeat_at"],
        label="legacy process lease heartbeat_at",
    )
    expires = _parse_time(
        verified["expires_at"],
        label="legacy process lease expires_at",
    )
    closed = _parse_time(
        verified["closed_at"],
        label="legacy process lease closed_at",
    )
    if not created <= heartbeat <= closed <= expires:
        raise DevLoopLifecycleError("legacy completed process lease times are inconsistent")
    return verified


def verify_authority_audit(
    payload: Mapping[str, Any], *, repo_root: Path | None = None
) -> dict[str, Any]:
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
    state_sha256 = verified.get("project_state_sha256")
    state_digest = verified.get("project_state_digest")
    if (
        not isinstance(state_sha256, str)
        or len(state_sha256) != 64
        or not isinstance(state_digest, str)
        or len(state_digest) != 64
        or not _candidate_state_semantics(verified.get("state_semantics"))
    ):
        raise DevLoopLifecycleError("authority audit project-state binding is invalid")
    if repo_root is not None:
        root = repo_root.resolve()
        current_state = _project_state_identity(root)
        if (
            state_sha256 != current_state["sha256"]
            or state_digest != current_state["digest"]
            or verified["state_semantics"] != current_state["semantics"]
        ):
            raise DevLoopLifecycleError("authority audit project-state binding is stale")
        if (
            git_identity["branch"] != _git(root, "branch", "--show-current")
            or git_identity["head"] != _git(root, "rev-parse", "HEAD")
            or git_identity["remote"] != _git(root, "rev-parse", "origin/main")
        ):
            raise DevLoopLifecycleError("authority audit repository identity is stale")
    return verified


def build_merge_readiness_packet(
    *,
    repo_root: Path,
    authority_audit: Mapping[str, Any],
    test_receipts: Sequence[Mapping[str, Any]],
    review_receipt_paths: Sequence[Path | str],
    changed_paths: Sequence[str],
) -> dict[str, Any]:
    root = repo_root.resolve()
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    remote_head = _git(root, "rev-parse", "origin/main")
    tracked_clean = not bool(_git(root, "status", "--porcelain", "--untracked-files=no"))
    state = _project_state_identity(root)
    audit = verify_authority_audit(authority_audit, repo_root=root)
    tests = [verify_test_receipt(value) for value in test_receipts]
    loaded_reviews = [
        _load_canonical_review_artifact(root, value)
        for value in review_receipt_paths
    ]
    reviews = [row[0] for row in loaded_reviews]
    review_artifacts = [row[1] for row in loaded_reviews]
    leases = _repository_process_leases(root)
    active_leases = [row for row in leases if row["status"] == "active"]
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
        and audit["project_state_sha256"] == state["sha256"]
        and audit["project_state_digest"] == state["digest"]
        and audit["state_semantics"] == state["semantics"]
    )
    tier_names = [str(row["tier"]) for row in tests]
    test_digests = [str(row["receipt_digest"]) for row in tests]
    test_identity_digests = [str(row["identity"]["identity_digest"]) for row in tests]
    exact_tiers = (
        set(tier_names) == set(FINAL_REQUIRED_TEST_TIERS)
        and len(tier_names) == len(FINAL_REQUIRED_TEST_TIERS)
    )
    tests_pass = (
        exact_tiers
        and len(test_digests) == len(set(test_digests))
        and len(test_identity_digests) == len(set(test_identity_digests))
        and all(
            row["status"] == "pass"
            and row["exit_code"] == 0
            and row["identity"]["commit"] == head
            and row["identity"]["branch"] == branch
            for row in tests
        )
    )
    test_digest_set = set(test_digests)
    reviews_pass = (
        len(reviews) == 1
        and reviews[0]["decision"] == "PASS"
        and reviews[0]["reviewed_commit"] == head
        and reviews[0]["reviewed_state_sha256"] == state["sha256"]
        and set(reviews[0]["test_receipt_digests"]) == test_digest_set
        and len(reviews[0]["test_receipt_digests"]) == len(test_digest_set)
    )
    ready = (
        branch == "main"
        and head == remote_head
        and tracked_clean
        and audit_pass
        and tests_pass
        and reviews_pass
        and not active_leases
        and _candidate_state_semantics(state["semantics"])
    )
    unsigned = {
        "schema_version": MERGE_SCHEMA,
        "status": "merge_ready" if ready else "not_ready",
        "branch": branch,
        "head": head,
        "remote_head": remote_head,
        "project_state_path": state["path"],
        "project_state_sha256": state["sha256"],
        "project_state_digest": state["digest"],
        "state_semantics": state["semantics"],
        "authority_audit_digest": audit["audit_digest"],
        "authority_audit": audit,
        "required_test_tiers": list(FINAL_REQUIRED_TEST_TIERS),
        "test_receipt_digests": test_digests,
        "test_receipts": tests,
        "test_evidence": [
            {
                "tier": row["tier"],
                "receipt_digest": row["receipt_digest"],
                "identity_digest": row["identity"]["identity_digest"],
                "commit": row["identity"]["commit"],
                "branch": row["identity"]["branch"],
                "status": row["status"],
                "exit_code": row["exit_code"],
            }
            for row in tests
        ],
        "review_receipt_digests": [row["receipt_digest"] for row in reviews],
        "review_receipts": reviews,
        "review_artifacts": review_artifacts,
        "review_evidence": [
            {
                "receipt_digest": row["receipt_digest"],
                "reviewed_commit": row["reviewed_commit"],
                "reviewed_state_sha256": row["reviewed_state_sha256"],
                "decision": row["decision"],
                "test_receipt_digests": row["test_receipt_digests"],
            }
            for row in reviews
        ],
        "process_lease_digests": [row["lease_digest"] for row in leases],
        "live_process_lease_count": len(active_leases),
        "tracked_worktree_clean": tracked_clean,
        "changed_paths": sorted({str(value) for value in changed_paths}),
        "authority": _authority({"commit": False, "push_origin_main": False}),
        "owner_gates": ["release_or_publication_beyond_repository_push"],
        "proof_class": "deterministic_repository_merge_readiness_no_release_authority",
        "terminal_authority": ready,
    }
    return validate_dev_loop_artifact("merge", _with_digest(unsigned, "packet_digest"))


def verify_merge_readiness_packet(
    payload: Mapping[str, Any], *, repo_root: Path | None = None
) -> dict[str, Any]:
    verified = _verify_digest(payload, "packet_digest", label="merge readiness")
    if verified.get("schema_version") != MERGE_SCHEMA:
        raise DevLoopLifecycleError("unexpected merge-readiness schema")
    _verify_authority(
        verified.get("authority"),
        repository_write_allowed=False,
        label="merge readiness",
    )
    verified = validate_dev_loop_artifact("merge", verified)
    if verified["status"] == "merge_ready":
        test_evidence = verified["test_evidence"]
        review_evidence = verified["review_evidence"]
        tiers = [row["tier"] for row in test_evidence]
        test_digests = [row["receipt_digest"] for row in test_evidence]
        exact_tests = (
            verified["required_test_tiers"] == list(FINAL_REQUIRED_TEST_TIERS)
            and set(tiers) == set(FINAL_REQUIRED_TEST_TIERS)
            and len(tiers) == len(FINAL_REQUIRED_TEST_TIERS)
            and len(test_digests) == len(set(test_digests))
            and verified["test_receipt_digests"] == test_digests
            and all(
                row["status"] == "pass"
                and row["exit_code"] == 0
                and row["commit"] == verified["head"]
                and row["branch"] == verified["branch"]
                for row in test_evidence
            )
        )
        exact_review = (
            len(review_evidence) == 1
            and verified["review_receipt_digests"]
            == [review_evidence[0]["receipt_digest"]]
            and review_evidence[0]["decision"] == "PASS"
            and review_evidence[0]["reviewed_commit"] == verified["head"]
            and review_evidence[0]["reviewed_state_sha256"]
            == verified["project_state_sha256"]
            and set(review_evidence[0]["test_receipt_digests"]) == set(test_digests)
            and len(review_evidence[0]["test_receipt_digests"]) == len(test_digests)
        )
        if not (
            verified["terminal_authority"] is True
            and verified["branch"] == "main"
            and verified["head"] == verified["remote_head"]
            and verified["tracked_worktree_clean"] is True
            and verified["live_process_lease_count"] == 0
            and exact_tests
            and exact_review
            and _candidate_state_semantics(verified["state_semantics"])
        ):
            raise DevLoopLifecycleError("merge-ready terminal semantics are invalid")
        if repo_root is None:
            raise DevLoopLifecycleError(
                "operational merge-ready verification requires a repository root"
            )
        root = repo_root.resolve()
        if len(verified["review_artifacts"]) != 1:
            raise DevLoopLifecycleError(
                "merge-ready packet must bind exactly one reviewer artifact"
            )
        external_review, external_artifact = _load_canonical_review_artifact(
            root, verified["review_artifacts"][0]["path"]
        )
        if (
            external_artifact != verified["review_artifacts"][0]
            or external_review != verified["review_receipts"][0]
            or external_review["receipt_digest"]
            != verified["review_evidence"][0]["receipt_digest"]
        ):
            raise DevLoopLifecycleError(
                "canonical reviewer artifact changed after packet generation"
            )
        state = _project_state_identity(root)
        if (
            verified["head"] != _git(root, "rev-parse", "HEAD")
            or verified["remote_head"] != _git(root, "rev-parse", "origin/main")
            or verified["branch"] != _git(root, "branch", "--show-current")
            or verified["project_state_sha256"] != state["sha256"]
            or verified["project_state_digest"] != state["digest"]
            or verified["state_semantics"] != state["semantics"]
            or bool(_git(root, "status", "--porcelain", "--untracked-files=no"))
            or any(row["status"] == "active" for row in _repository_process_leases(root))
        ):
            raise DevLoopLifecycleError("merge-readiness packet is stale")
        rebuilt = build_merge_readiness_packet(
            repo_root=root,
            authority_audit=verified["authority_audit"],
            test_receipts=verified["test_receipts"],
            review_receipt_paths=[
                row["path"] for row in verified["review_artifacts"]
            ],
            changed_paths=verified["changed_paths"],
        )
        if rebuilt != verified:
            raise DevLoopLifecycleError(
                "merge-readiness packet does not match its verified evidence bundle"
            )
    elif verified["terminal_authority"] is not False:
        raise DevLoopLifecycleError("not-ready packet cannot grant terminal authority")
    return verified


__all__ = [
    "DevLoopLifecycleError",
    "CANONICAL_FINAL_REVIEW_PATH",
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
