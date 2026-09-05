#!/usr/bin/env python3
"""One local/CI entry point for software operations checks; no implicit install.

The existing uv.lock owns dependency versions and hashes. This script owns only
the small, explicit inspection test groups; it does not admit native campaigns.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time

try:
    import tomllib
except ImportError:  # Give older system Python an actionable diagnostic.
    tomllib = None

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    "operations": ("tests/test_ops.py", "tests/test_ops_cli.py"),
    "adapter": ("tests/test_workspace_adapter.py",),
    "workcell": ("tests/test_workcell.py",),
    "git": ("tests/test_git_health.py",),
    "contracts": ("tests/test_operations_contract_freeze.py",),
    "runner": ("tests/test_check_operations.py",),
}


def locked_dependencies(root: Path) -> list[dict]:
    """Reuse CI's conservative transitive closure; ambiguous locks fail closed."""
    if tomllib is None:
        raise ValueError("Python 3.12 is required; this interpreter has no tomllib")
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    by_name: dict[str, list[dict]] = {}
    for package in lock["package"]:
        by_name.setdefault(package["name"], []).append(package)
    pending = ["pytest", "jsonschema"]
    selected = {}
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        matches = by_name.get(name, [])
        if len(matches) != 1:
            raise ValueError(f"Inspection dependency needs explicit lock disambiguation: {name}")
        package = matches[0]
        version = package["version"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+!_-]*", version):
            raise ValueError("Unsupported dependency name/version in uv.lock")
        artifacts = [*package.get("wheels", []), *([package["sdist"]] if "sdist" in package else [])]
        hashes = sorted({artifact.get("hash", "") for artifact in artifacts})
        if not hashes or any(not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) for digest in hashes):
            raise ValueError(f"Inspection dependency has no complete SHA-256 artifact lock: {name}")
        selected[name] = {"name": name, "version": version, "hashes": hashes}
        pending.extend(dependency["name"] for dependency in package.get("dependencies", []))
    return [selected[name] for name in sorted(selected)]


def requirements(dependencies: list[dict]) -> str:
    return "\n".join(f"{package['name']}=={package['version']} " +
                     " ".join(f"--hash={digest}" for digest in package["hashes"])
                     for package in dependencies) + "\n"


def selected_tests(suite: str) -> tuple[str, ...]:
    return tuple(path for paths in SUITES.values() for path in paths) if suite == "all" else SUITES[suite]


def preflight(root: Path, dependencies: list[dict], paths: tuple[str, ...]) -> list[str]:
    errors = []
    if sys.version_info[:2] != (3, 12):
        errors.append(f"Python 3.12 is required; current interpreter is {sys.version.split()[0]} ({sys.executable})")
    for dependency in dependencies:
        name, expected = dependency["name"], dependency["version"]
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"Missing dependency: {name}=={expected}")
        else:
            if actual != expected:
                errors.append(f"Dependency drift: {name}=={actual}; uv.lock requires {expected}")
    if shutil.which("git") is None:
        errors.append("Git is required for disposable repository fixtures; git was not found on PATH")
    try:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
    except sqlite3.Error as error:
        errors.append(f"This Python's SQLite lacks required FTS5 support: {error}")
    if not paths:
        errors.append("No test files selected; no checks were run")
    for path in paths:
        if not (root / path).is_file():
            errors.append(f"Required test file is missing in this checkout: {path}")
    return errors


class Outcomes:
    """Observe real pytest results, including collection-only and skip failures."""

    def __init__(self) -> None:
        self.counts: Counter = Counter()

    def pytest_collection_finish(self, session) -> None:
        self.counts["collected"] = len(session.items)

    def pytest_deselected(self, items) -> None:
        self.counts["deselected"] += len(items)

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self.counts["collection_errors"] += 1
        elif report.skipped:
            self.counts["collection_skipped"] += 1

    def pytest_runtest_logreport(self, report) -> None:
        if report.failed:
            self.counts["failed" if report.when == "call" else "errors"] += 1
        elif report.skipped:
            self.counts["xfailed" if hasattr(report, "wasxfail") else "skipped"] += 1
        elif report.when == "call" and report.passed:
            self.counts["xpassed" if hasattr(report, "wasxfail") else "passed"] += 1


def run_pytest(root: Path, paths: tuple[str, ...]) -> tuple[int, dict]:
    # Ignore user/plugin test-selection flags so this named suite stays exact.
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ.pop("PYTEST_ADDOPTS", None)
    os.environ.pop("PYTEST_PLUGINS", None)
    os.environ["PYTHONPATH"] = os.pathsep.join((str(root / "src"), str(root)))
    sys.path[:0] = [str(root / "src"), str(root)]
    os.chdir(root)
    import pytest

    outcomes = Outcomes()
    started = time.monotonic()
    pytest_code = int(pytest.main([*paths, "-q", "-ra", "--strict-config", "--strict-markers",
                                  "-o", "addopts=", "-p", "no:cacheprovider"], plugins=[outcomes]))
    counts = {name: outcomes.counts[name] for name in ("collected", "passed", "failed", "errors", "skipped",
              "xfailed", "xpassed", "deselected", "collection_errors", "collection_skipped")}
    complete = (pytest_code == 0 and counts["collected"] > 0 and counts["passed"] == counts["collected"]
                and not any(value for name, value in counts.items() if name not in {"collected", "passed"}))
    code = 0 if complete else pytest_code or 1
    return code, {"status": "passed" if complete else "incomplete_or_failed", "counts": counts,
                  "pytest_exit_code": pytest_code, "exit_code": code,
                  "duration_s": round(time.monotonic() - started, 3)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("requirements", help="print hash-locked inspection dependencies from uv.lock; install nothing")
    subcommands.add_parser("list", help="show named test groups and runtime requirements; run no tests")
    check = subcommands.add_parser("check", help="run the selected required tests; skips, deselection and zero tests are not success")
    check.add_argument("--suite", choices=("all", *SUITES), default="all")
    args = parser.parse_args(argv)
    try:
        dependencies = locked_dependencies(ROOT)
        if args.command == "requirements":
            print(requirements(dependencies), end="")
            return 0
        if args.command == "list":
            print(json.dumps({"root": str(ROOT), "python": "3.12", "tests_executed": False,
                              "default_suite": "all", "suites": SUITES,
                              "dependencies": [{"name": p["name"], "version": p["version"]} for p in dependencies]}, indent=2))
            return 0
        paths = selected_tests(args.suite)
        errors = preflight(ROOT, dependencies, paths)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            print("No tests ran. Follow docs/DEVELOPMENT.md for the isolated operations environment.", file=sys.stderr)
            return 2
        print(f"Operations checks: suite={args.suite}; checkout={ROOT}; Python={sys.executable}", flush=True)
        print("Software inspection tests only; native campaign admission is separate.", flush=True)
        code, summary = run_pytest(ROOT, paths)
        summary.update(suite=args.suite, root=str(ROOT), python=sys.version.split()[0],
                       executable=sys.executable, test_files=list(paths),
                       lock_sha256=hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest())
        print("OPERATIONS_CHECK_RESULT " + json.dumps(summary, sort_keys=True), flush=True)
        return code
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print(f"Operations check setup failed: {error}. No passing result is available.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
