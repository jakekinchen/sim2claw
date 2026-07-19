"""Complete, reviewable code/runtime/tool identities for factory reuse keys."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

from .learning_factory_artifacts import canonical_digest, sha256_file


DEPENDENCY_DISTRIBUTIONS = (
    "mujoco",
    "numpy",
    "opencv-python-headless",
    "pillow",
    "pyarrow",
    "torch",
)


def _module_row(module_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    origin = None if spec is None else spec.origin
    if origin is None or origin in {"built-in", "frozen"}:
        return {"module": module_name, "present": False}
    path = Path(origin).resolve()
    if not path.is_file():
        return {"module": module_name, "present": False}
    return {
        "module": module_name,
        "present": True,
        "filename": path.name,
        "sha256": sha256_file(path),
        "path": str(path),
    }


def _tool_row(command: str) -> dict[str, Any]:
    located = shutil.which(command)
    if located is None:
        return {"command": command, "present": False}
    path = Path(located).resolve()
    row: dict[str, Any] = {
        "command": command,
        "present": True,
        "path": str(path),
    }
    if path.is_file():
        try:
            row["sha256"] = sha256_file(path)
        except OSError as error:
            row["sha256_error"] = type(error).__name__
    version_args = {
        "ffmpeg": ["-version"],
        "ffprobe": ["-version"],
        "colmap": ["-h"],
        "brush": ["--version"],
        "git": ["--version"],
    }.get(command, ["--version"])
    try:
        completed = subprocess.run(
            [str(path), *version_args],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        version_text = (completed.stdout or completed.stderr).strip().splitlines()
        row["version"] = version_text[0] if version_text else ""
        row["version_exit_code"] = completed.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        row["version_error"] = type(error).__name__
    return row


def _git_identity(repo_root: Path, files: Iterable[dict[str, Any]]) -> dict[str, Any]:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

    try:
        top = run("rev-parse", "--show-toplevel")
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "error": type(error).__name__}
    if top.returncode != 0:
        return {"available": False}
    git_root = Path(top.stdout.strip()).resolve()
    head = run("rev-parse", "HEAD")
    relevant: list[str] = []
    for row in files:
        raw = row.get("path")
        if not isinstance(raw, str):
            continue
        path = Path(raw).resolve()
        if path.is_relative_to(git_root):
            relevant.append(path.relative_to(git_root).as_posix())
    for fixed in ("pyproject.toml", "uv.lock"):
        if (git_root / fixed).is_file():
            relevant.append(fixed)
    status_rows: list[str] = []
    if relevant:
        status = run(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *sorted(set(relevant)),
        )
        if status.returncode == 0:
            status_rows = sorted(
                line.rstrip() for line in status.stdout.splitlines() if line.strip()
            )
    return {
        "available": True,
        "root": str(git_root),
        "head": head.stdout.strip() if head.returncode == 0 else None,
        "relevant_worktree_status": status_rows,
        "relevant_worktree_clean": not status_rows,
    }


def build_implementation_identity(
    *,
    repo_root: Path,
    component_modules: Iterable[str],
    external_tools: Iterable[str],
) -> dict[str, Any]:
    modules = sorted(
        set(
            (
                "sim2claw.learning_factory",
                "sim2claw.learning_factory_artifacts",
                "sim2claw.learning_factory_contracts",
                "sim2claw.learning_factory_identity",
            )
            + tuple(component_modules)
        )
    )
    files = [_module_row(name) for name in modules]
    dependencies = []
    for distribution in DEPENDENCY_DISTRIBUTIONS:
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            version = None
        dependencies.append({"distribution": distribution, "version": version})
    tools = [_tool_row(name) for name in sorted(set(("git",) + tuple(external_tools)))]
    unsigned = {
        "schema_version": "sim2claw.factory_implementation_identity.v2",
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "abi": getattr(sys, "abiflags", ""),
            "platform": platform.platform(),
        },
        "modules": files,
        "dependencies": dependencies,
        "external_tools": tools,
        "git": _git_identity(repo_root, files),
    }
    return {**unsigned, "sha256": canonical_digest(unsigned)}
