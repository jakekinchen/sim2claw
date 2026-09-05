"""Real small pytest sessions verify developer-check failure semantics."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/check_operations.py"
spec = importlib.util.spec_from_file_location("check_operations_for_test", SCRIPT)
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)


def test_dependencies_are_derived_from_existing_lock_with_artifact_hashes() -> None:
    packages = runner.locked_dependencies(REPO)
    names = {package["name"] for package in packages}
    assert {"pytest", "jsonschema", "referencing", "rpds-py"} <= names
    assert not {"mujoco", "torch", "numpy", "genesis-world"} & names
    text = runner.requirements(packages)
    assert all("--hash=sha256:" in line for line in text.splitlines())
    assert all(package["hashes"] == sorted(set(package["hashes"])) for package in packages)


@pytest.mark.parametrize("kind", ["missing", "ambiguous", "missing_hash"])
def test_dependency_lock_problems_fail_cleanly(tmp_path: Path, kind: str) -> None:
    if kind == "missing":
        text = "package = []\n"
    else:
        package = '\n[[package]]\nname = "jsonschema"\nversion = "1.0"\n'
        text = package * (2 if kind == "ambiguous" else 1)
    (tmp_path / "uv.lock").write_text(text)
    with pytest.raises(ValueError, match="lock disambiguation|SHA-256 artifact lock"):
        runner.locked_dependencies(tmp_path)


def test_preflight_reports_missing_drift_and_missing_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def version(name: str) -> str:
        if name == "missing":
            raise runner.importlib.metadata.PackageNotFoundError(name)
        return "old"
    monkeypatch.setattr(runner.importlib.metadata, "version", version)
    monkeypatch.setattr(runner.shutil, "which", lambda name: None)
    errors = runner.preflight(tmp_path, [{"name": "missing", "version": "1"}, {"name": "drift", "version": "2"}], ("tests/absent.py",))
    assert any("Missing dependency: missing==1" in error for error in errors)
    assert any("Dependency drift: drift==old" in error for error in errors)
    assert any("git was not found" in error for error in errors)
    assert any("Required test file is missing" in error for error in errors)


def test_preflight_reports_wrong_python_sqlite_and_empty_selection(tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.sys, "version_info", (3, 11, 0))
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("no such module: fts5")
    monkeypatch.setattr(runner.sqlite3, "connect", unavailable)
    errors = runner.preflight(tmp_path, [], ())
    assert any("Python 3.12 is required" in error for error in errors)
    assert any("FTS5" in error for error in errors)
    assert any("No test files selected" in error for error in errors)


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A fresh source checkout shape, with no editable installation or runtime."""
    root = tmp_path / "fresh checkout"
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src").mkdir()
    shutil.copyfile(SCRIPT, root / "scripts/check_operations.py")
    shutil.copyfile(REPO / "uv.lock", root / "uv.lock")
    return root


def child_check(checkout: Path, body: str, env: dict | None = None) -> tuple[subprocess.CompletedProcess, dict]:
    (checkout / "tests/test_operations_contract_freeze.py").write_text(body)
    result = subprocess.run([sys.executable, str(checkout / "scripts/check_operations.py"),
                             "check", "--suite", "contracts"], cwd=checkout.parent,
                            capture_output=True, text=True, env=env, timeout=15)
    summary = [line.removeprefix("OPERATIONS_CHECK_RESULT ") for line in result.stdout.splitlines()
               if line.startswith("OPERATIONS_CHECK_RESULT ")]
    assert len(summary) == 1, result.stdout + result.stderr
    return result, json.loads(summary[0])


def test_script_uses_its_own_checkout_from_other_cwd_and_ignores_selection_options(checkout: Path) -> None:
    (checkout / "src/checkout_marker.py").write_text("IDENTITY = 'fresh checkout'\n")
    (checkout / "pytest.ini").write_text("[pytest]\naddopts = --collect-only -k nonexistent\n")
    env = dict(os.environ, PYTEST_ADDOPTS="--collect-only -k nonexistent",
               PYTEST_PLUGINS="plugin_that_does_not_exist", PYTHONPATH="/does/not/exist")
    result, summary = child_check(checkout, "from checkout_marker import IDENTITY\ndef test_source():\n    assert IDENTITY == 'fresh checkout'\n", env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert summary["root"] == str(checkout)
    assert summary["counts"]["collected"] == summary["counts"]["passed"] == 1
    assert summary["counts"]["deselected"] == 0
    assert summary["test_files"] == ["tests/test_operations_contract_freeze.py"]


@pytest.mark.parametrize("body,counter,expected_exit", [
    ("import pytest\n@pytest.mark.skip(reason='required platform unavailable')\ndef test_skip(): pass\n", "skipped", 1),
    ("import pytest\n@pytest.mark.xfail(reason='known required gap')\ndef test_xfail(): assert False\n", "xfailed", 1),
    ("import pytest\n@pytest.mark.xfail(reason='outcome changed')\ndef test_xpass(): pass\n", "xpassed", 1),
    ("import pytest\npytest.skip('module dependency unavailable',allow_module_level=True)\n", "collection_skipped", 5),
    ("def test_failure(): assert False\n", "failed", 1),
    ("raise RuntimeError('collection unavailable')\n", "collection_errors", 2),
    ("VALUE = 1\n", "collected", 5),
])
def test_incomplete_or_failed_sessions_never_report_success(checkout: Path, body: str, counter: str, expected_exit: int) -> None:
    result, summary = child_check(checkout, body)
    assert result.returncode == expected_exit, result.stdout + result.stderr
    assert summary["status"] == "incomplete_or_failed"
    assert summary["counts"][counter] == (0 if counter == "collected" else 1)


def test_deselection_by_project_hook_is_visible(checkout: Path) -> None:
    (checkout / "tests/conftest.py").write_text(
        "def pytest_collection_modifyitems(config,items):\n"
        "    config.hook.pytest_deselected(items=items[:1])\n"
        "    del items[:1]\n")
    result, summary = child_check(checkout, "def test_one(): pass\ndef test_two(): pass\n")
    assert result.returncode == 1
    assert summary["counts"]["passed"] == 1 and summary["counts"]["deselected"] == 1


def test_missing_dependency_exits_before_pytest_or_install(monkeypatch: pytest.MonkeyPatch,
                                                          capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(runner, "preflight", lambda *args: ["Missing dependency: pytest==required"])
    def forbidden(*args, **kwargs):
        pytest.fail("Preflight failure must not run tests")
    monkeypatch.setattr(runner, "run_pytest", forbidden)
    assert runner.main(["check"]) == 2
    output = capsys.readouterr()
    assert "No tests ran" in output.err and "Missing dependency" in output.err
    assert "OPERATIONS_CHECK_RESULT" not in output.out


def test_list_and_requirements_need_no_pytest_import_or_test_execution(monkeypatch: pytest.MonkeyPatch,
                                                                    capsys: pytest.CaptureFixture[str]) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("Discovery must not execute tests")
    monkeypatch.setattr(runner, "preflight", forbidden)
    monkeypatch.setattr(runner, "run_pytest", forbidden)
    assert runner.main(["list"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["tests_executed"] is False
    assert set(listing["suites"]) == set(runner.SUITES)
    assert runner.main(["requirements"]) == 0
    assert "pytest==" in capsys.readouterr().out


def test_no_arbitrary_pytest_argument_passthrough() -> None:
    with pytest.raises(SystemExit) as error:
        runner.main(["check", "--collect-only"])
    assert error.value.code == 2


def test_broken_installed_package_import_is_a_clean_setup_failure(monkeypatch: pytest.MonkeyPatch,
                                                               capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(runner, "preflight", lambda *args: [])
    def broken(*args, **kwargs):
        raise ImportError("broken pytest installation")
    monkeypatch.setattr(runner, "run_pytest", broken)
    assert runner.main(["check"]) == 2
    assert "broken pytest installation" in capsys.readouterr().err
