"""Inspect prospective Git payload growth using bounded metadata only.

This is advisory: it never changes an index, rewrites history, returns or
evaluates payload content, installs LFS, or grants permission to discard or
publish an evidence receipt. Git status may internally hash touched files.
Sizes are uncompressed Git blobs relative to HEAD, not disk or upload estimates.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 100_000
MAX_REPORTED_BLOBS = 20
MAX_REPORTED_PATHS = 5
GIT_TIMEOUT_SECONDS = 30
_OID = re.compile(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def _git(root: Path, *args: str, input_data: bytes | None = None,
         optional: bool = False, overrides: tuple[str, ...] = ()) -> bytes | None:
    """Spool command metadata outside the repository; bound in-memory results."""
    env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_NAMESPACE"):
        env.pop(name, None)
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    command = ["git", "--no-replace-objects", "-C", str(root),
               "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false"]
    for setting in overrides:
        command.extend(("-c", setting))
    command.extend(args)
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        try:
            result = subprocess.run(command, input=input_data, stdout=output, stderr=error,
                                    env=env, timeout=GIT_TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"Git metadata inspection failed: {type(exc).__name__}") from exc
        if result.returncode:
            if optional:
                return None
            error.seek(0)
            detail = error.read(1000).decode("utf-8", "replace").strip()
            raise ValueError(f"Git metadata inspection failed: {detail or 'command refused'}")
        if output.tell() > MAX_METADATA_BYTES:
            raise ValueError(f"Git metadata exceeds the {MAX_METADATA_BYTES}-byte inspection limit")
        output.seek(0)
        return output.read(MAX_METADATA_BYTES + 1)


def _entries(raw: bytes, *, index: bool) -> tuple[list[tuple[bytes, bytes]], int, int]:
    """Return blob/path pairs, gitlink count and unresolved path count."""
    records = raw.split(b"\0")
    if len(records) - 1 > MAX_ENTRIES:
        raise ValueError(f"Git metadata exceeds the {MAX_ENTRIES}-entry inspection limit")
    blobs: list[tuple[bytes, bytes]] = []
    submodules = 0
    conflicts: set[bytes] = set()
    for record in records:
        if not record:
            continue
        try:
            prefix, path = record.split(b"\t", 1)
            mode, second, third = prefix.split(b" ")
        except ValueError as exc:
            raise ValueError("Malformed Git tree/index metadata") from exc
        oid = second if index else third
        if not _OID.fullmatch(oid) or not path:
            raise ValueError("Malformed Git object ID or path metadata")
        if index and third != b"0":
            conflicts.add(path)
            continue
        if mode == b"160000":
            submodules += 1
            continue
        if mode not in (b"100644", b"100755", b"120000"):
            raise ValueError("Unsupported Git entry mode; inspection is incomplete")
        if not index and second != b"blob":
            raise ValueError("Expected Git blob metadata")
        blobs.append((oid, path))
    return blobs, submodules, len(conflicts)


def _summary(entries: list[tuple[bytes, bytes]], sizes: dict[bytes, int],
             submodules: int) -> dict[str, int]:
    ids = {oid for oid, _ in entries}
    return {"files": len(entries), "logical_bytes": sum(sizes[oid] for oid, _ in entries),
            "unique_blobs": len(ids), "unique_blob_bytes": sum(sizes[oid] for oid in ids),
            "submodules": submodules}


def inspect_git(root: Path, max_added_bytes: int = 32 * 1024 * 1024,
                max_blob_bytes: int = 10 * 1024 * 1024) -> dict[str, Any]:
    """Describe staged growth, never enforcing a retention or execution policy.

    Unresolved merge entries have no final stage-zero payload and are reported
    separately. Submodules are counted without inspecting their worktrees or
    trying to resolve their commits. Symlink blobs are measured without following
    links. All paths in JSON retain their exact filesystem spelling.
    """
    for name, value in (("max_added_bytes", max_added_bytes), ("max_blob_bytes", max_blob_bytes)):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    root = Path(root).resolve()
    top = _git(root, "rev-parse", "--show-toplevel")
    assert top is not None
    root = Path(os.fsdecode(top.removesuffix(b"\n")))
    head_raw = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}", optional=True)
    head = head_raw.strip().decode("ascii") if head_raw else None
    branch_raw = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", optional=True)
    upstream_raw = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
                        "@{upstream}", optional=True) if head else None
    branch = os.fsdecode(branch_raw.removesuffix(b"\n")) if branch_raw else None
    upstream = os.fsdecode(upstream_raw.removesuffix(b"\n")) if upstream_raw else None
    ahead = behind = None
    if upstream:
        distance = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
        assert distance is not None
        ahead, behind = map(int, distance.split())
    head_tree = _git(root, "ls-tree", "-r", "-z", head) if head else b""
    index_raw = _git(root, "ls-files", "--stage", "-z")
    assert head_tree is not None and index_raw is not None
    head_entries, head_submodules, _ = _entries(head_tree, index=False)
    index_entries, index_submodules, unmerged = _entries(index_raw, index=True)
    ids = sorted({oid for oid, _ in head_entries + index_entries})
    sizes: dict[bytes, int] = {}
    if ids:
        metadata = _git(root, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                        input_data=b"\n".join(ids) + b"\n")
        assert metadata is not None
        for line in metadata.splitlines():
            fields = line.split()
            if len(fields) != 3 or fields[1] != b"blob" or not fields[2].isdigit():
                raise ValueError("A Git blob is unavailable; metadata inspection is incomplete")
            sizes[fields[0]] = int(fields[2])
        if set(sizes) != set(ids):
            raise ValueError("Git object metadata does not cover every inspected blob")
    head_summary = _summary(head_entries, sizes, head_submodules)
    index_summary = _summary(index_entries, sizes, index_submodules)
    head_ids = {oid for oid, _ in head_entries}
    index_ids = {oid for oid, _ in index_entries}
    added = index_ids - head_ids
    removed = head_ids - index_ids
    added_bytes = sum(sizes[oid] for oid in added)
    removed_bytes = sum(sizes[oid] for oid in removed)
    largest_ids = sorted(added, key=lambda oid: (-sizes[oid], oid))[:MAX_REPORTED_BLOBS]
    paths: dict[bytes, list[bytes]] = {oid: [] for oid in largest_ids}
    path_counts = dict.fromkeys(largest_ids, 0)
    for oid, path in index_entries:
        if oid in paths:
            path_counts[oid] += 1
            if len(paths[oid]) < MAX_REPORTED_PATHS:
                paths[oid].append(path)
    largest = [{"sha": oid.decode("ascii"), "bytes": sizes[oid],
                "paths": [os.fsdecode(path) for path in paths[oid]],
                "path_count": path_counts[oid]} for oid in largest_ids]
    # Even porcelain status can invoke a repository's clean/process filter when
    # checking a touched file. Disable every configured filter in this command
    # only; never execute repository-defined programs during an advisory scan.
    filter_keys = _git(root, "config", "--null", "--name-only", "--get-regexp",
                       r"^filter\..*\.(clean|smudge|process|required)$", optional=True) or b""
    filter_overrides = tuple(
        os.fsdecode(key) + ("=false" if key.endswith(b".required") else "=")
        for key in filter_keys.split(b"\0") if key
    )
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal",
                  "--ignore-submodules=all", "--no-renames", "--no-ahead-behind",
                  overrides=filter_overrides)
    assert status is not None
    dirty = {"staged": 0, "unstaged": 0, "untracked": 0, "unmerged": unmerged}
    for record in status.split(b"\0"):
        if not record:
            continue
        code = record[:2]
        if code == b"??":
            dirty["untracked"] += 1
        elif code in (b"DD", b"AU", b"UD", b"UA", b"DU", b"AA", b"UU"):
            continue
        else:
            dirty["staged"] += code[:1] != b" "
            dirty["unstaged"] += code[1:2] != b" "
    # A concurrent writer can change HEAD or the index while metadata is read.
    head_end = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}", optional=True)
    consistent = (head_end == head_raw and _git(root, "ls-files", "--stage", "-z") == index_raw)
    reasons = []
    if added_bytes > max_added_bytes:
        reasons.append("added_unique_blob_bytes_exceed_budget")
    if any(sizes[oid] > max_blob_bytes for oid in added):
        reasons.append("new_blob_exceeds_budget")
    if unmerged:
        reasons.append("unmerged_index_has_no_complete_commit_payload")
    if not consistent:
        reasons.append("head_or_index_changed_during_inspection")
    return {
        "schema_version": "sim2claw.git_health/v1", "root": str(root), "branch": branch,
        "head_commit": head, "upstream": upstream, "ahead": ahead, "behind": behind,
        "head": head_summary, "index": index_summary, "dirty_counts": dirty,
        "staged_unique_byte_delta": index_summary["unique_blob_bytes"] - head_summary["unique_blob_bytes"],
        "added_unique_blob_bytes": added_bytes, "removed_unique_blob_bytes": removed_bytes,
        "added_unique_blobs": len(added), "largest_new_blobs": largest,
        "largest_new_blobs_truncated": len(added) > len(largest),
        "thresholds": {"max_added_bytes": max_added_bytes, "max_blob_bytes": max_blob_bytes},
        "snapshot_consistent": consistent, "review_required": bool(reasons), "reasons": reasons,
        "metric_basis": "uncompressed index blobs relative to HEAD; not disk or upload bytes",
        "untracked_count_basis": "Git normal mode counts untracked directories as one entry",
        "dirty_count_basis": "Git status with external filters and fsmonitor disabled; filtered files may appear modified",
        "advisory_only": True, "execution_authorized": False,
    }
