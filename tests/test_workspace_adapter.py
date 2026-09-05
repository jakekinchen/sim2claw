"""Independent read-only workspace exchange and rejection tests."""

from __future__ import annotations

import builtins
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator, FormatChecker
import pytest

from sim2claw.ops import adapter, cli as ops_cli


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_RELATIVE = "configs/operations/workspace_adapter.v1.schema.json"
FIXTURES_RELATIVE = "configs/operations/workspace_adapter.v1.fixtures.json"
CONFORMANCE_CASES = json.loads((REPO_ROOT / FIXTURES_RELATIVE).read_text(encoding="utf-8"))["cases"]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(scope="module")
def exported_workspace() -> dict:
    return adapter.export_workspace(REPO_ROOT)


@pytest.fixture
def bound_exchange(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "workspace"
    root.mkdir()
    schema = root / SCHEMA_RELATIVE
    schema.parent.mkdir(parents=True)
    schema.write_bytes((REPO_ROOT / SCHEMA_RELATIVE).read_bytes())
    source = root / "NATIVE_MANDATE.md"
    source.write_text("Read-only metadata inspection. Native execution is refused.\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init", "-q", "--initial-branch=fixture"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "NATIVE_MANDATE.md", SCHEMA_RELATIVE], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Workspace Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture source identity"],
        check=True,
        capture_output=True,
    )
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    payload = {
        "schema_version": "robotics.workspace_exchange.v1",
        "contract_sha256": _sha(schema.read_bytes()),
        "generated_at": "2026-09-05T00:00:00+00:00",
        "workspace": {
            "id": "test-workspace",
            "domain": "robotics-fixture",
            "repository": {"head": head, "branch": "fixture", "dirty": False},
            "mandate": {"summary": "Inspect metadata only", "source_priority": ["mandate"]},
            "owner_task": "Fixture test owner",
        },
        "sources": [{"id": "mandate", "path": "NATIVE_MANDATE.md", "sha256": _sha(source.read_bytes()), "role": "native mandate"}],
        "profiles": [
            {
                "id": "fixture-arm",
                "robot_family": "two-joint-test-arm",
                "native_schema": "fixture.robot_abi.v1",
                "scope": "metadata only",
                "action": {
                    "dimension": 2,
                    "ordered_names": ["shoulder", "elbow"],
                    "units": ["radian", "radian"],
                    "encoding": "float64-little-endian",
                    "representation": "absolute_joint_positions",
                    "transform_policy": "No transform or retargeting is authorized",
                },
                "observation": {"dimension": None, "description": "No observation tensor exported", "privileged_state_policy": "none"},
                "timing": {"control_hz": 20.0, "physics_step_s": None, "clock": "host_monotonic", "frame_policy": "No timestamp transformation"},
                "source_ids": ["mandate"],
            }
        ],
        "capabilities": [
            {
                "id": "inspect-metadata",
                "kind": "workspace",
                "native_schema": "fixture.workspace.v1",
                "availability": "implemented",
                "description": "Read native metadata",
                "read_only": True,
                "entrypoint": ["fixture-cli", "inspect"],
            }
        ],
        "evidence": {
            "native_classes": ["fixture_metadata"],
            "native_record_schemas": ["fixture.receipt.v1"],
            "integrity_meaning": "Matching bytes establish source identity only",
            "acceptance_meaning": "A native evaluator owns acceptance",
            "records_exported": False,
        },
        "permissions": {"inspect": True, "execute": False, "mutate_sources": False, "train": False, "hardware": False, "promote": False, "paid_compute": False},
        "native_gate": {"status": "refused", "detail": "Native branch prerequisite is not satisfied"},
        "limitations": ["No policy portability, execution, training, hardware or promotion authorization"],
    }
    return root, payload


def _validate(root: Path, payload: dict, *, verify: bool = True) -> dict:
    return adapter.validate_workspace(root, payload, source_root=root if verify else None)


def test_real_export_satisfies_independent_json_schema_and_resolves_all_references(exported_workspace: dict) -> None:
    schema = json.loads((REPO_ROOT / SCHEMA_RELATIVE).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(exported_workspace)
    assert exported_workspace["contract_sha256"] == _sha((REPO_ROOT / SCHEMA_RELATIVE).read_bytes())
    for kind in ("sources", "profiles", "capabilities"):
        ids = [item["id"] for item in exported_workspace[kind]]
        assert len(ids) == len(set(ids))
    source_ids = {source["id"] for source in exported_workspace["sources"]}
    assert set(exported_workspace["workspace"]["mandate"]["source_priority"]) <= source_ids
    assert all(set(profile["source_ids"]) <= source_ids for profile in exported_workspace["profiles"])
    for profile in exported_workspace["profiles"]:
        action = profile["action"]
        assert len(action["ordered_names"]) == len(action["units"]) == action["dimension"]
    assert exported_workspace["evidence"]["records_exported"] is False
    assert exported_workspace["permissions"]["inspect"] is True
    assert all(value is False for key, value in exported_workspace["permissions"].items() if key != "inspect")


def test_positive_source_verification_is_separate_from_metadata_validation(bound_exchange: tuple[Path, dict]) -> None:
    root, payload = bound_exchange
    unchecked = _validate(root, payload, verify=False)
    assert unchecked["valid"] is True
    assert unchecked["errors"] == []
    assert unchecked["source_verification"]["status"] == "unchecked"
    verified = _validate(root, payload)
    assert verified["valid"] is True
    assert verified["source_verification"]["status"] == "hash_verified"
    assert verified["source_verification"]["checks"]
    assert verified["workspace_id"] == payload["workspace"]["id"]


@pytest.mark.parametrize("payload", [None, [], "not-an-object", 42, True])
def test_nonobject_payloads_return_explicit_validation_errors(bound_exchange: tuple[Path, dict], payload) -> None:
    root, _ = bound_exchange
    result = adapter.validate_workspace(root, payload)
    assert result["valid"] is False
    assert result["errors"]
    assert result["execution_authorized"] is False
    assert result["policy_portable"] is False


@pytest.mark.parametrize("kind", ["sources", "profiles", "capabilities"])
def test_duplicate_declared_ids_are_rejected(bound_exchange: tuple[Path, dict], kind: str) -> None:
    root, payload = bound_exchange
    payload[kind].append(deepcopy(payload[kind][0]))
    result = _validate(root, payload)
    assert result["valid"] is False
    assert result["errors"]


@pytest.mark.parametrize("reference", ["profile", "mandate"])
def test_dangling_source_references_are_rejected(bound_exchange: tuple[Path, dict], reference: str) -> None:
    root, payload = bound_exchange
    if reference == "profile":
        payload["profiles"][0]["source_ids"] = ["missing-source"]
    else:
        payload["workspace"]["mandate"]["source_priority"] = ["missing-source"]
    assert _validate(root, payload)["valid"] is False


@pytest.mark.parametrize("path", ["../outside.md", "/etc/passwd", "folder/../../outside.md"])
def test_source_paths_cannot_escape_the_declared_workspace(bound_exchange: tuple[Path, dict], path: str) -> None:
    root, payload = bound_exchange
    payload["sources"][0]["path"] = path
    assert _validate(root, payload, verify=False)["valid"] is False
    assert _validate(root, payload)["valid"] is False


def test_source_symlink_is_rejected_even_when_target_bytes_match(bound_exchange: tuple[Path, dict], tmp_path: Path) -> None:
    root, payload = bound_exchange
    source = root / payload["sources"][0]["path"]
    target = tmp_path / "outside.md"
    target.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(target)
    result = _validate(root, payload)
    assert result["valid"] is False
    assert result["source_verification"]["status"] == "drift"


def test_foreign_source_syntax_is_not_judged_by_unrelated_local_symlinks(bound_exchange: tuple[Path, dict], tmp_path: Path) -> None:
    root, payload = bound_exchange
    outside = tmp_path / "unrelated-local-directory"
    outside.mkdir()
    (root / "peer-docs").symlink_to(outside, target_is_directory=True)
    payload["sources"][0]["path"] = "peer-docs/native-mandate.md"
    unchecked = _validate(root, payload, verify=False)
    assert unchecked["valid"] is True
    assert unchecked["source_verification"]["status"] == "unchecked"
    assert _validate(root, payload)["valid"] is False


@pytest.mark.parametrize("change", ["modified", "missing"])
def test_stale_or_missing_sources_fail_hash_verification(bound_exchange: tuple[Path, dict], change: str) -> None:
    root, payload = bound_exchange
    source = root / payload["sources"][0]["path"]
    if change == "modified":
        source.write_text("new source bytes", encoding="utf-8")
    else:
        source.unlink()
    result = _validate(root, payload)
    assert result["valid"] is False
    assert result["source_verification"]["status"] == "drift"


@pytest.mark.parametrize("field", ["ordered_names", "units"])
def test_action_abi_vector_lengths_must_equal_dimension(bound_exchange: tuple[Path, dict], field: str) -> None:
    root, payload = bound_exchange
    payload["profiles"][0]["action"][field] = ["only-one"]
    assert _validate(root, payload)["valid"] is False


def test_action_names_must_not_alias_one_another(bound_exchange: tuple[Path, dict]) -> None:
    root, payload = bound_exchange
    payload["profiles"][0]["action"]["ordered_names"] = ["shoulder", "shoulder"]
    assert _validate(root, payload)["valid"] is False


@pytest.mark.parametrize("section,field,value", [("action", "dimension", True), ("observation", "dimension", True), ("timing", "control_hz", True), ("timing", "physics_step_s", True)])
def test_boolean_values_do_not_masquerade_as_numeric_abi_fields(bound_exchange: tuple[Path, dict], section: str, field: str, value: bool) -> None:
    root, payload = bound_exchange
    payload["profiles"][0][section][field] = value
    assert _validate(root, payload)["valid"] is False


@pytest.mark.parametrize("section,field,value", [("action", "dimension", 0), ("action", "dimension", 129), ("observation", "dimension", 0), ("timing", "control_hz", 0), ("timing", "physics_step_s", -0.01)])
def test_invalid_numeric_abi_bounds_are_rejected(bound_exchange: tuple[Path, dict], section: str, field: str, value: float) -> None:
    root, payload = bound_exchange
    payload["profiles"][0][section][field] = value
    assert _validate(root, payload)["valid"] is False


@pytest.mark.parametrize("mutation", ["contract_hash", "schema_version", "schema_file"])
def test_contract_identity_and_schema_version_must_match(bound_exchange: tuple[Path, dict], mutation: str) -> None:
    root, payload = bound_exchange
    if mutation == "contract_hash":
        payload["contract_sha256"] = "0" * 64
    elif mutation == "schema_version":
        payload["schema_version"] = "robotics.workspace_exchange.v999"
    else:
        path = root / SCHEMA_RELATIVE
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert _validate(root, payload)["valid"] is False


@pytest.mark.parametrize("timestamp", ["2026-09-05", "2026-09-05T00:00:00", "2026-02-30T00:00:00Z"])
def test_invalid_timestamps_fail_even_without_optional_jsonschema_format_checks(bound_exchange: tuple[Path, dict], monkeypatch: pytest.MonkeyPatch, timestamp: str) -> None:
    root, payload = bound_exchange
    payload["generated_at"] = timestamp
    monkeypatch.setattr("jsonschema.FormatChecker", lambda: FormatChecker(formats=[]))
    result = _validate(root, payload, verify=False)
    assert result["valid"] is False
    assert any("generated_at" in error for error in result["errors"])


@pytest.mark.parametrize("permission", ["execute", "mutate_sources", "train", "hardware", "promote", "paid_compute"])
def test_exchange_cannot_escalate_any_execution_permission(bound_exchange: tuple[Path, dict], permission: str) -> None:
    root, payload = bound_exchange
    payload["permissions"][permission] = True
    assert _validate(root, payload)["valid"] is False


@pytest.mark.parametrize("permission", ["inspect", "execute", "mutate_sources", "train", "hardware", "promote", "paid_compute"])
def test_integer_permission_impostors_are_rejected(bound_exchange: tuple[Path, dict], permission: str) -> None:
    root, payload = bound_exchange
    payload["permissions"][permission] = int(payload["permissions"][permission])
    assert _validate(root, payload)["valid"] is False


@pytest.mark.parametrize("mutation", ["writable_capability", "numeric_read_only", "numeric_permission", "records_exported", "numeric_records_exported"])
def test_read_only_constants_are_strict_json_booleans(bound_exchange: tuple[Path, dict], mutation: str) -> None:
    root, payload = bound_exchange
    if mutation == "writable_capability":
        payload["capabilities"][0]["read_only"] = False
    elif mutation == "numeric_read_only":
        payload["capabilities"][0]["read_only"] = 1
    elif mutation == "numeric_permission":
        payload["permissions"]["hardware"] = 0
    elif mutation == "records_exported":
        payload["evidence"]["records_exported"] = True
    else:
        payload["evidence"]["records_exported"] = 0
    assert _validate(root, payload)["valid"] is False


def test_dirty_head_does_not_substitute_for_source_hash_identity(bound_exchange: tuple[Path, dict]) -> None:
    root, payload = bound_exchange
    payload["workspace"]["repository"]["dirty"] = True
    assert _validate(root, payload, verify=False)["source_verification"]["status"] == "unchecked"
    assert _validate(root, payload)["source_verification"]["status"] == "hash_verified"
    head = payload["workspace"]["repository"]["head"]
    (root / payload["sources"][0]["path"]).write_text("same Git head, different source", encoding="utf-8")
    result = _validate(root, payload)
    assert payload["workspace"]["repository"]["head"] == head
    assert result["valid"] is False
    assert result["source_verification"]["status"] == "drift"


def test_native_branch_refusal_remains_a_valid_refusal_record(bound_exchange: tuple[Path, dict]) -> None:
    root, payload = bound_exchange
    before = deepcopy(payload)
    result = _validate(root, payload)
    assert result["valid"] is True
    assert result["errors"] == []
    assert payload == before
    assert payload["native_gate"]["status"] == "refused"
    assert payload["permissions"]["execute"] is False


@pytest.mark.parametrize("data", ['{"id": 1, "id": 2}', '{"nested": {"id": 1, "id": 2}}', '{"value": NaN}', '{"value": Infinity}', '{"value": -Infinity}', '{"value": 1e9999}'])
def test_exchange_loader_rejects_ambiguous_or_nonfinite_json(tmp_path: Path, data: str) -> None:
    source = tmp_path / "exchange.json"
    source.write_text(data, encoding="utf-8")
    with pytest.raises(ValueError):
        adapter.load_exchange(source)


def test_exchange_loader_is_bounded_and_requires_an_object(tmp_path: Path, bound_exchange: tuple[Path, dict]) -> None:
    _, payload = bound_exchange
    source = tmp_path / "exchange.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert adapter.load_exchange(source) == payload
    source.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        adapter.load_exchange(source)
    # A sparse oversized file checks the read bound without allocating a large payload.
    with source.open("wb") as stream:
        stream.truncate(65 * 1024 * 1024)
    with pytest.raises(ValueError):
        adapter.load_exchange(source)


def test_twenty_thousand_nested_arrays_are_rejected_as_a_clean_input_error(tmp_path: Path) -> None:
    source = tmp_path / "deep-exchange.json"
    source.write_text('{"nested":' + "[" * 20000 + "0" + "]" * 20000 + "}", encoding="utf-8")
    with pytest.raises(ValueError):
        adapter.load_exchange(source)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Named pipes are unavailable on this platform")
def test_exchange_loader_rejects_a_fifo_without_waiting_for_a_writer(tmp_path: Path) -> None:
    source = tmp_path / "exchange.json"
    os.mkfifo(source)
    script = """
from pathlib import Path
import sys
from sim2claw.ops.adapter import load_exchange
try:
    load_exchange(Path(sys.argv[1]))
except ValueError:
    raise SystemExit(0)
raise SystemExit(1)
"""
    # The subprocess timeout kills a broken blocking reader rather than hanging
    # pytest; there is deliberately no writer or background process to clean up.
    result = subprocess.run([sys.executable, "-c", script, str(source)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=3)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kind", ["recursive", "deeply_nested", "nonfinite"])
def test_programmatic_nonjson_payloads_return_clean_invalid_results(bound_exchange: tuple[Path, dict], kind: str) -> None:
    root, payload = bound_exchange
    if kind == "recursive":
        payload["cycle"] = payload
    elif kind == "deeply_nested":
        value = 0
        for _ in range(20000):
            value = [value]
        payload["nested"] = value
    else:
        payload["profiles"][0]["timing"]["control_hz"] = float("inf")
    result = adapter.validate_workspace(root, payload)
    assert result["valid"] is False
    assert result["errors"]
    assert result["execution_authorized"] is False
    assert result["policy_portable"] is False


def test_equal_dimensions_on_different_robots_never_imply_policy_portability(exported_workspace: dict) -> None:
    peer = deepcopy(exported_workspace)
    peer["workspace"]["id"] = "different-robot-peer"
    for profile in peer["profiles"]:
        profile["robot_family"] = "completely-different-robot"
    result = adapter.compare_workspaces(REPO_ROOT, peer)
    assert result["metadata_compatible"] is True
    assert result["policy_portable"] is False
    assert result["execution_authorized"] is False
    assert result["profile_comparisons"]
    assert result["peer_validation"]["source_verification"]["status"] == "unchecked"


def test_validators_never_execute_declared_commands(bound_exchange: tuple[Path, dict], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root, payload = bound_exchange
    marker = tmp_path / "command-must-not-run"
    payload["capabilities"][0]["entrypoint"] = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('executed')"]
    invoked = []
    real_run = subprocess.run

    def forbidden(*args, **kwargs):
        if args and args[0] == ["git", "-C", str(root), "rev-parse", "HEAD"]:
            return real_run(*args, **kwargs)
        invoked.append(args)
        raise AssertionError("Metadata validation must not invoke a declared command")

    monkeypatch.setattr("subprocess.run", forbidden)
    result = _validate(root, payload)
    assert result["valid"] is True
    monkeypatch.setattr(adapter, "export_workspace", lambda _root: deepcopy(payload))
    compared = adapter.compare_workspaces(root, deepcopy(payload))
    assert compared["execution_authorized"] is False
    assert compared["policy_portable"] is False
    assert invoked == []
    assert not marker.exists()


def test_adapter_module_import_does_not_load_heavy_runtimes_in_a_fresh_process() -> None:
    script = """
import builtins
original = builtins.__import__
forbidden = {"mujoco", "torch", "genesis", "openai", "anthropic", "pyrealsense2", "serial"}
def guarded(name, *args, **kwargs):
    if name.split(".")[0] in forbidden:
        raise AssertionError("Unexpected runtime import: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from sim2claw.ops import adapter
print("safe metadata module import")
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "safe metadata module import"


def test_export_validate_and_compare_do_not_import_simulator_or_provider_runtimes(exported_workspace: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden_roots = {"mujoco", "torch", "genesis", "openai", "anthropic", "pyrealsense2", "serial"}
    imported = []

    def guarded(name, *args, **kwargs):
        imported.append(name)
        if name.split(".")[0] in forbidden_roots:
            raise AssertionError(f"Workspace metadata imported runtime {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    fresh = adapter.export_workspace(REPO_ROOT)
    result = adapter.validate_workspace(REPO_ROOT, fresh, source_root=REPO_ROOT)
    assert result["valid"] is True
    compared = adapter.compare_workspaces(REPO_ROOT, deepcopy(exported_workspace))
    assert compared["policy_portable"] is False
    assert compared["execution_authorized"] is False
    assert all(name.split(".")[0] not in forbidden_roots for name in imported)


def test_shared_fixture_pack_is_bound_to_the_current_contract() -> None:
    pack = json.loads((REPO_ROOT / FIXTURES_RELATIVE).read_text(encoding="utf-8"))
    assert pack["schema_version"] == "robotics.workspace_conformance_fixtures.v1"
    assert pack["contract_sha256"] == _sha((REPO_ROOT / SCHEMA_RELATIVE).read_bytes())
    assert len(pack["cases"]) == 30
    assert len({case["id"] for case in pack["cases"]}) == 30
    assert all(type(case["expected_valid"]) is bool for case in pack["cases"])


@pytest.mark.parametrize("case", CONFORMANCE_CASES, ids=[case["id"] for case in CONFORMANCE_CASES])
def test_shared_data_only_fixtures_match_expected_validation_without_execution(case: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    invoked = []

    def forbidden(*args, **kwargs):
        invoked.append(args)
        raise AssertionError("Data-only fixture validation must not execute a process")

    monkeypatch.setattr(subprocess, "run", forbidden)
    before = deepcopy(case["payload"])
    result = adapter.validate_workspace(REPO_ROOT, case["payload"])
    assert result["valid"] is case["expected_valid"]
    assert result["source_verification"]["status"] == "unchecked"
    assert result["policy_portable"] is False
    assert result["execution_authorized"] is False
    assert case["payload"] == before
    assert invoked == []


def test_cli_adapter_export_emits_schema_valid_nonexecuting_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = ops_cli.main(["--root", str(REPO_ROOT), "--json", "adapter", "export"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    result = json.loads(captured.out)
    schema = json.loads((REPO_ROOT / SCHEMA_RELATIVE).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
    assert result["permissions"]["execute"] is False
    assert result["permissions"]["hardware"] is False
    assert result["evidence"]["records_exported"] is False


@pytest.mark.parametrize("verify_sources", [False, True])
def test_cli_adapter_check_valid_refusal_succeeds(bound_exchange: tuple[Path, dict], capsys: pytest.CaptureFixture[str], tmp_path: Path, verify_sources: bool) -> None:
    root, payload = bound_exchange
    peer = tmp_path / "peer.json"
    peer.write_text(json.dumps(payload), encoding="utf-8")
    argv = ["--root", str(root), "--json", "adapter", "check", str(peer)]
    if verify_sources:
        argv += ["--source-root", str(root)]
    code = ops_cli.main(argv)
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["valid"] is True
    assert result["source_verification"]["status"] == ("hash_verified" if verify_sources else "unchecked")
    assert result["execution_authorized"] is False
    assert result["policy_portable"] is False


@pytest.mark.parametrize("failure", ["authority", "source_drift", "strict_json"])
def test_cli_adapter_check_invalid_peer_returns_exit_one(bound_exchange: tuple[Path, dict], capsys: pytest.CaptureFixture[str], tmp_path: Path, failure: str) -> None:
    root, payload = bound_exchange
    peer = tmp_path / "peer.json"
    argv = ["--root", str(root), "--json", "adapter", "check", str(peer)]
    if failure == "authority":
        payload["permissions"]["execute"] = True
    elif failure == "source_drift":
        (root / payload["sources"][0]["path"]).write_text("changed source", encoding="utf-8")
        argv += ["--source-root", str(root)]
    peer.write_text('{"bad":1e9999}' if failure == "strict_json" else json.dumps(payload), encoding="utf-8")
    code = ops_cli.main(argv)
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == ""
    result = json.loads(captured.out)
    if failure == "strict_json":
        assert result["status"] == "error"
        assert result["error"]
    else:
        assert result["valid"] is False
        assert result["errors"]
        assert result["execution_authorized"] is False


@pytest.mark.parametrize("valid", [True, False])
def test_cli_adapter_compare_returns_metadata_outcome_without_portability(exported_workspace: dict, capsys: pytest.CaptureFixture[str], tmp_path: Path, valid: bool) -> None:
    peer = deepcopy(exported_workspace)
    peer["workspace"]["id"] = "cli-peer"
    for profile in peer["profiles"]:
        profile["robot_family"] = "different-test-robot"
    if not valid:
        peer["permissions"]["train"] = True
    path = tmp_path / "peer.json"
    path.write_text(json.dumps(peer), encoding="utf-8")
    code = ops_cli.main(["--root", str(REPO_ROOT), "--json", "adapter", "compare", str(path)])
    captured = capsys.readouterr()
    assert code == (0 if valid else 1)
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["passed"] is valid
    assert result["metadata_compatible"] is valid
    assert result["policy_portable"] is False
    assert result["execution_authorized"] is False


def test_conformance_command_reports_all_shared_cases_without_authority(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Synthetic conformance must not execute commands")

    monkeypatch.setattr(subprocess, "run", forbidden)
    code = ops_cli.main(["--root", str(REPO_ROOT), "--json", "adapter", "conformance"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["passed"] is True
    assert len(result["cases"]) == 30
    assert all(case["passed"] for case in result["cases"])
    assert result["fixtures_sha256"] == _sha((REPO_ROOT / FIXTURES_RELATIVE).read_bytes())
    assert result["contract_sha256"] == _sha((REPO_ROOT / SCHEMA_RELATIVE).read_bytes())
    assert result["execution_authorized"] is False
    assert result["policy_portable"] is False


@pytest.mark.parametrize("failure", ["wrong_expectation", "fixture_contract_drift"])
def test_conformance_command_returns_exit_one_on_a_failed_or_unbound_pack(bound_exchange: tuple[Path, dict], capsys: pytest.CaptureFixture[str], failure: str) -> None:
    root, _ = bound_exchange
    pack = json.loads((REPO_ROOT / FIXTURES_RELATIVE).read_text(encoding="utf-8"))
    if failure == "wrong_expectation":
        pack["cases"][0]["expected_valid"] = not pack["cases"][0]["expected_valid"]
    else:
        pack["contract_sha256"] = "0" * 64
    (root / FIXTURES_RELATIVE).write_text(json.dumps(pack), encoding="utf-8")
    code = ops_cli.main(["--root", str(root), "--json", "adapter", "conformance"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err == ""
    result = json.loads(captured.out)
    if failure == "wrong_expectation":
        assert result["passed"] is False
        assert result["cases"][0]["passed"] is False
        assert result["execution_authorized"] is False
        assert result["policy_portable"] is False
    else:
        assert result["status"] == "error"


def test_export_follows_manifest_and_graph_source_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    read = adapter._read
    manifest_path = "configs/agent/current_state_v1.json"
    manifest = json.loads((REPO_ROOT / manifest_path).read_text(encoding="utf-8"))
    graph = json.loads((REPO_ROOT / manifest["campaign_graph_path"]).read_text(encoding="utf-8"))
    virtual = {
        "virtual/native-goal.md": (REPO_ROOT / manifest["goal_path"]).read_bytes(),
        "virtual/native-project-state.json": (REPO_ROOT / manifest["project_state_path"]).read_bytes(),
        "virtual/native-queue.md": (REPO_ROOT / graph["source_bindings"]["queue"]["path"]).read_bytes(),
    }
    manifest["goal_path"] = "virtual/native-goal.md"
    manifest["project_state_path"] = "virtual/native-project-state.json"
    manifest["campaign_graph_path"] = "virtual/native-campaign.json"
    graph["source_bindings"]["queue"]["path"] = "virtual/native-queue.md"
    virtual["virtual/native-campaign.json"] = json.dumps(graph).encode("utf-8")
    virtual[manifest_path] = json.dumps(manifest).encode("utf-8")

    def read_virtual(path: Path, limit: int) -> bytes:
        relative = path.relative_to(REPO_ROOT).as_posix()
        return virtual[relative] if relative in virtual else read(path, limit)

    monkeypatch.setattr(adapter, "_read", read_virtual)
    payload = adapter.export_workspace(REPO_ROOT)
    sources = {source["id"]: source for source in payload["sources"]}
    expected = {"goal": "virtual/native-goal.md", "project_state": "virtual/native-project-state.json", "campaign": "virtual/native-campaign.json", "queue": "virtual/native-queue.md"}
    for identifier, path in expected.items():
        assert sources[identifier]["path"] == path
        assert sources[identifier]["sha256"] == _sha(virtual[path])
    assert "project_state" in payload["workspace"]["mandate"]["source_priority"]


def test_export_reads_native_replay_constants_from_source_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    read = adapter._read
    relative = "src/sim2claw/replay_eligibility.py"
    source = (REPO_ROOT / relative).read_bytes()
    source += b'\n'  # Keep the synthetic source identity distinct even before replacements.
    source = source.replace(b'MANIFEST_SCHEMA = "sim2claw.exact_replay_eligibility_manifest.v1"', b'MANIFEST_SCHEMA = "fixture.exact_manifest.v7"')
    source = source.replace(b'REPORT_SCHEMA = "sim2claw.exact_replay_eligibility_report.v1"', b'REPORT_SCHEMA = "fixture.exact_report.v7"')
    source = source.replace(b'ACTION_HASH_ENCODING = "little_endian_float64_c_order"', b'ACTION_HASH_ENCODING = "fixture_encoding_v7"')
    source = source.replace(b'"action": "radian"', b'"action": "fixture_native_unit"')

    def read_virtual(path: Path, limit: int) -> bytes:
        return source if path == REPO_ROOT / relative else read(path, limit)

    monkeypatch.setattr(adapter, "_read", read_virtual)
    payload = adapter.export_workspace(REPO_ROOT)
    profile = next(profile for profile in payload["profiles"] if profile["id"] == "so101.exact_replay.v1")
    assert profile["native_schema"] == "fixture.exact_manifest.v7"
    assert profile["action"]["encoding"] == "fixture_encoding_v7"
    assert profile["action"]["units"] == ["fixture_native_unit"] * profile["action"]["dimension"]
    assert "fixture.exact_report.v7" in payload["evidence"]["native_record_schemas"]
    assert next(source for source in payload["sources"] if source["id"] == "exact_replay")["sha256"] == _sha(source)
