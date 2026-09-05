"""Synthetic declaration and rejection checks; never construct a simulator."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sim2claw.ops import workcell

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_plan(root: Path, plan: dict) -> None:
    (root / workcell.PLAN_PATH).write_text(json.dumps(plan), encoding="utf-8")


def _write_source(root: Path, peer: Path, plan: dict, identifier: str, value: bytes | dict) -> None:
    source = next(item for item in plan["sources"] if item["id"] == identifier)
    producer = root if source["workspace_id"] == "sim2claw" else peer
    path = producer / source["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value).encode() if isinstance(value, dict) else value
    path.write_bytes(data)
    source["sha256"] = hashlib.sha256(data).hexdigest()
    _write_plan(root, plan)


def _model(names: tuple[str, ...], *, floating: bool) -> bytes:
    return ("<mujoco><compiler angle='radian'/><worldbody><body name='base'>"
            + ("<freejoint name='floating'/>" if floating else "")
            + "".join(f"<joint name='{name}' type='hinge'/>" for name in names)
            + "</body></worldbody><actuator>"
            + "".join(f"<position name='{name}' joint='{name}'/>" for name in names)
            + "</actuator></mujoco>").encode()


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, Path, dict]:
    root, peer = tmp_path / "arm-workspace", tmp_path / "duck-workspace"
    (root / workcell.PLAN_PATH).parent.mkdir(parents=True)
    peer.mkdir()
    plan = json.loads((REPO_ROOT / workcell.PLAN_PATH).read_text())
    sources = {
        "arm_model": _model(workcell.ARM_NAMES, floating=False),
        "duck_model": _model(workcell.DUCK_NAMES, floating=True),
        "arm_joints": ("ROBOT_JOINTS = " + repr(workcell.ARM_NAMES) + "\n").encode(),
        "arm_action": {"schema_version": "sim2claw.canonical_manipulation_source_contract.v4", "execution": {
            "action_dimension": 6, "action_representation": "absolute_joint_position_target", "action_unit": "rad",
            "sample_hold_hz": 20, "physics_timestep_seconds": 0.005, "physics_steps_per_action": 10,
            "exact_float32_action_replay_required_before_export": True, "replay_must_use_original_scene_and_reset_seed": True}},
        "duck_action": {"schema_version": "microduck.interface/v1", "interface_id": "microduck.action.v1",
            "dtype": "float32", "joint_order": list(workcell.DUCK_NAMES), "scale": 1.0,
            "semantics": "unfiltered_delta_from_home_rad", "shape": [1, 14]},
        "duck_observation": {"schema_version": "microduck.interface/v1", "interface_id": "microduck.obs.v1",
            "dtype": "float32", "joint_order": list(workcell.DUCK_NAMES), "shape": [1, 61],
            "home_joint_position_rad": [0.0] * 14},
        "duck_control": {"schema_version": "microduck.control/v1", "control_id": "microduck.control.50hz.v1",
            "action_filter": "none", "control_hz": 50, "decimation": 4, "physics_dt_s": 0.005},
        "battery_mesh": b"\x00Synthetic battery mesh identity only\xff",
        "mount_mesh": b"\x00Synthetic mount mesh identity only\xfe",
        "apple_runtime": b"Synthetic runtime lock identity only\n",
    }
    for identifier, data in sources.items():
        _write_source(root, peer, plan, identifier, data)
    return root, peer, plan


def _native_json(root: Path, peer: Path, plan: dict, identifier: str) -> dict:
    source = next(item for item in plan["sources"] if item["id"] == identifier)
    producer = root if source["workspace_id"] == "sim2claw" else peer
    return json.loads((producer / source["path"]).read_text())


def test_verified_declarations_leave_mechanical_and_execution_gates_unmet(workspace: tuple) -> None:
    root, peer, _ = workspace
    result = workcell.inspect_workcell(root, peer)
    assert result["plan_valid"] and result["source_verification"] == "hash_verified"
    assert len(result["sources"]) == 10
    assert result["gates"][0]["status"] == "passed"
    assert all(gate["status"] == "unmet" for gate in result["gates"][1:])
    assert result["mechanical_target"]["measurements_verified"] is False
    assert result["mechanical_target"]["redesign_allowed"] is False
    for flag in ("execution_authorized", "simulation_executed", "actions_dispatched", "training_authorized", "hardware_authorized", "paid_compute_authorized"):
        assert result[flag] is False
    assert "Transitive" in result["coverage"]
    assert [source["native_declaration"] for source in result["sources"][-3:]] == ["hash_only"] * 3


def test_schedule_keeps_different_native_rates_and_independent_named_buffers(workspace: tuple) -> None:
    root, peer, _ = workspace
    schedule = workcell.inspect_workcell(root, peer)["schedule"]
    assert [(event["tick"], event["due_buffers"]) for event in schedule["preview"]] == [
        (0, ["arm", "duck"]), (4, ["duck"]), (8, ["duck"]), (10, ["arm"]), (12, ["duck"]), (16, ["duck"])]
    assert [event["time_s"] for event in schedule["preview"]] == [0, .02, .04, .05, .06, .08]
    arm, duck = schedule["buffers"]
    assert (arm["dimension"], duck["dimension"]) == (6, 14)
    assert (arm["updates_per_200_ticks"], duck["updates_per_200_ticks"]) == (20, 50)
    assert set(arm["qualified_names"]).isdisjoint(duck["qualified_names"])
    assert arm["representation"] != duck["representation"]
    assert duck["home_offset_source_id"] == "duck_observation"
    assert all("values" not in buffer for buffer in schedule["buffers"])
    assert schedule["action_values_created"] is False
    assert schedule["actions_dispatched"] is False


def test_peer_root_is_never_guessed(workspace: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    root, peer, _ = workspace
    read = workcell._read
    observed = []
    def inspect_read(path: Path, limit: int) -> bytes:
        observed.append(path)
        return read(path, limit)
    monkeypatch.setattr(workcell, "_read", inspect_read)
    result = workcell.inspect_workcell(root)
    assert result["plan_valid"] and result["source_verification"] == "partial"
    assert len([source for source in result["sources"] if source["status"] == "unchecked"]) == 7
    assert result["gates"][0]["status"] == "unmet"
    assert not any(path.is_relative_to(peer) for path in observed)


@pytest.mark.parametrize("change", [
    lambda plan: plan.update(schema_version="robotics.arm_duck_workcell_plan.v2"),
    lambda plan: plan.update(extra="unsupported"),
    lambda plan: plan["clock"].update(tick_hz=200.0),
    lambda plan: plan["clock"].update(physics_dt_s=.01),
    lambda plan: plan["clock"].update(phase_period_ticks=10),
    lambda plan: plan["clock"].update(implicit_resampling_allowed=True),
    lambda plan: plan["actors"][0]["action"].update(dimension=True),
    lambda plan: plan["actors"][0]["action"].update(dimension=12),
    lambda plan: plan["actors"][0]["action"].update(unit="degree"),
    lambda plan: plan["actors"][0]["action"].update(ticks_per_action=4),
    lambda plan: plan["actors"][0]["action"]["ordered_names"].reverse(),
    lambda plan: plan["actors"][1]["action"].update(representation="absolute_joint_position_target"),
    lambda plan: plan["actors"][1].update(namespace="arm_"),
    lambda plan: plan["actors"][1].update(floating_base=False),
    lambda plan: plan["sources"][0].update(id="duck_model"),
    lambda plan: plan["sources"][0].update(path="../outside"),
    lambda plan: plan["sources"][0].update(path="/outside"),
    lambda plan: plan["sources"][0].update(path="C:\\outside"),
    lambda plan: plan["sources"][0].update(path="bad\x00path"),
    lambda plan: plan["sources"][0].update(sha256="z" * 64),
    lambda plan: plan["permissions"].update(simulate=True),
    lambda plan: plan["permissions"].update(inspect=1),
    lambda plan: plan["mechanical_target"].update(redesign_allowed=True),
    lambda plan: plan["mechanical_target"].update(measurements_verified=True),
    lambda plan: plan["world"].update(quaternion_order="xyzw"),
    lambda plan: plan["world"]["frames"][1].update(parent="service_fixture"),
    lambda plan: plan["world"]["frames"][4].update(parent="arm_base"),
    lambda plan: plan["unmet_gates"][0].update(requires=["controller_routing"]),
    lambda plan: plan["unmet_gates"].pop(),
    lambda plan: plan["unmet_gates"][-1].update(id="static_scene"),
    lambda plan: plan["unmet_gates"][-1].update(id="unknown_gate"),
    lambda plan: plan["unmet_gates"][3].update(requires=["hardware_measurements"] * 2),
    lambda plan: plan["unmet_gates"][3]["requires"].reverse(),
    lambda plan: plan["compute_policy"].update(remote_launch_authorized_by_plan=True),
    lambda plan: plan["compute_policy"].update(remote_role="default_training"),
    lambda plan: plan["compute_policy"].update(remote_provider="any_cloud"),
    lambda plan: plan["compute_policy"]["remote_request_fields"].pop(),
    lambda plan: plan["compute_policy"].update(remote_request_fields=["maximum_duration"] * 8),
])
def test_recipe_discrepancies_are_rejected(workspace: tuple, change) -> None:
    root, peer, plan = workspace
    change(plan)
    _write_plan(root, plan)
    result = workcell.inspect_workcell(root, peer)
    assert result["plan_valid"] is False and result["errors"]
    assert result["schedule"] is None


@pytest.mark.parametrize("gate_id,requires", [
    ("controller_routing", ["declaration_check"]),
    ("battery_mechanics", ["hardware_measurements"]),
    ("service_task", ["controller_routing"]),
    ("local_training", ["declaration_check"]),
    ("independent_validation", ["declaration_check"]),
])
def test_acyclic_gate_shortcuts_cannot_bypass_existing_hardware_measurement(workspace: tuple, gate_id: str, requires: list[str]) -> None:
    root, peer, plan = workspace
    next(gate for gate in plan["unmet_gates"] if gate["id"] == gate_id)["requires"] = requires
    _write_plan(root, plan)
    result = workcell.inspect_workcell(root, peer)
    assert not result["plan_valid"]
    assert any(f"gate {gate_id}.requires" in error for error in result["errors"])


def test_gate_presentation_order_does_not_change_declared_dependencies(workspace: tuple) -> None:
    root, peer, plan = workspace
    plan["unmet_gates"].reverse()
    _write_plan(root, plan)
    result = workcell.inspect_workcell(root, peer)
    assert result["plan_valid"] and result["source_verification"] == "hash_verified"
    assert result["gates"][0]["status"] == "passed"
    assert result["gates"][1:] == [{**gate, "status": "unmet"} for gate in plan["unmet_gates"]]


@pytest.mark.parametrize("identifier,field,value", [
    ("duck_action", "semantics", "absolute_joint_position_target"),
    ("duck_action", "shape", [True, 14]),
    ("duck_action", "dtype", "float64"),
    ("duck_action", "joint_order", list(reversed(workcell.DUCK_NAMES))),
    ("duck_control", "control_hz", 20),
    ("duck_control", "decimation", 10),
    ("duck_control", "action_filter", "lowpass"),
    ("duck_observation", "home_joint_position_rad", [0.0] * 13),
    ("duck_observation", "home_joint_position_rad", [True] * 14),
    ("duck_observation", "home_joint_position_rad", [10 ** 1000] * 14),
    ("duck_observation", "shape", [1, 60]),
])
def test_rehashed_native_contract_drift_is_still_rejected(workspace: tuple, identifier: str, field: str, value) -> None:
    root, peer, plan = workspace
    native = _native_json(root, peer, plan, identifier)
    native[field] = value
    _write_source(root, peer, plan, identifier, native)
    result = workcell.inspect_workcell(root, peer)
    assert not result["plan_valid"]
    assert any(identifier in error for error in result["errors"])


def test_arm_abi_model_mapping_and_literal_execution_are_checked(workspace: tuple) -> None:
    root, peer, plan = workspace
    native = _native_json(root, peer, plan, "arm_action")
    native["execution"]["exact_float32_action_replay_required_before_export"] = False
    _write_source(root, peer, plan, "arm_action", native)
    _write_source(root, peer, plan, "arm_model", _model(workcell.ARM_NAMES, floating=True))
    marker = root / "SHOULD_NOT_EXIST"
    _write_source(root, peer, plan, "arm_joints", f"ROBOT_JOINTS = __import__('pathlib').Path({str(marker)!r}).touch()\n".encode())
    result = workcell.inspect_workcell(root, peer)
    assert not result["plan_valid"] and len(result["errors"]) == 3
    assert not marker.exists()


def test_excessive_native_ast_depth_is_a_bounded_cli_rejection(workspace: tuple) -> None:
    root, peer, plan = workspace
    _write_source(root, peer, plan, "arm_joints", b"ROBOT_JOINTS = " + b"+".join([b"1"] * 10000) + b"\n")
    code = "import sys; from sim2claw.ops.cli import main; raise SystemExit(main(sys.argv[1:]))"
    result = subprocess.run([sys.executable, "-c", code, "--root", str(root), "--json", "workcell", "--peer-root", str(peer)], capture_output=True, text=True, timeout=5)
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert not payload["plan_valid"]
    assert any("native ROBOT_JOINTS literal" in error for error in payload["errors"])
    assert "Traceback" not in result.stderr


def test_source_hash_drift_and_missing_roots_are_not_accepted(workspace: tuple) -> None:
    root, peer, plan = workspace
    source = plan["sources"][0]
    (root / source["path"]).write_bytes(b"changed source")
    result = workcell.inspect_workcell(root, peer / "missing")
    assert not result["plan_valid"] and result["source_verification"] == "rejected"
    assert len(result["errors"]) == 8


@pytest.mark.parametrize("data", [b'{"schema_version":1,"schema_version":2}', b'{"x":NaN}', b'{"x":1e999}', b'\xff', b'{"x":' + b'[' * 40 + b'0' + b']' * 40 + b'}', b'{"x":' + b'[' * 20000 + b'0' + b']' * 20000 + b'}'])
def test_malformed_recipe_is_a_clean_invalid_result(workspace: tuple, data: bytes) -> None:
    root, peer, _ = workspace
    (root / workcell.PLAN_PATH).write_bytes(data)
    result = workcell.inspect_workcell(root, peer)
    assert not result["plan_valid"] and result["errors"]


def test_source_symlink_and_xml_entity_declarations_are_rejected(workspace: tuple) -> None:
    root, peer, plan = workspace
    source = root / plan["sources"][0]["path"]
    target = root / "external-model.xml"
    source.rename(target)
    source.symlink_to(target)
    _write_source(root, peer, plan, "duck_model", b'<!DOCTYPE mujoco [<!ENTITY a "x">]><mujoco>&a;</mujoco>')
    result = workcell.inspect_workcell(root, peer)
    assert not result["plan_valid"] and len(result["errors"]) == 2


@pytest.mark.parametrize("replacement", [
    lambda model: model.replace(b"angle='radian'", b"angle='degree'"),
    lambda model: model.replace(b"joint='gripper'", b"joint='shoulder_pan'"),
    lambda model: model.replace(b"type='hinge'", b"type='slide'", 1),
    lambda model: model.replace(b"type='hinge'", b"type='ball'", 1),
    lambda model: model.replace(b"<position ", b"<motor "),
])
def test_rehashed_model_units_and_cross_joint_routing_are_rejected(workspace: tuple, replacement) -> None:
    root, peer, plan = workspace
    _write_source(root, peer, plan, "arm_model", replacement(_model(workcell.ARM_NAMES, floating=False)))
    result = workcell.inspect_workcell(root, peer)
    assert not result["plan_valid"]
    assert result["errors"][0].startswith("arm_model:")


def test_oversize_recipe_and_parent_symlink_fail_before_native_inspection(workspace: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    root, peer, _ = workspace
    with monkeypatch.context() as patch:
        patch.setattr(workcell, "JSON_LIMIT", 128)
        result = workcell.inspect_workcell(root, peer)
        assert not result["plan_valid"] and "inspection limit" in result["errors"][0]
    directory = root / "configs" / "operations"
    moved = root / "outside-operations"
    directory.rename(moved)
    directory.symlink_to(moved, target_is_directory=True)
    result = workcell.inspect_workcell(root, peer)
    assert not result["plan_valid"] and "symlink" in result["errors"][0]


def test_file_inspection_and_module_import_need_no_robot_runtime(workspace: tuple) -> None:
    root, peer, _ = workspace
    code = """import builtins,json,sys
from pathlib import Path
original = builtins.__import__
blocked = {'mujoco','genesis','torch','numpy','jax','lerobot','jsonschema'}
def guarded(name,*args,**kwargs):
    if name.split('.')[0] in blocked:
        raise AssertionError('Runtime import attempted: '+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from sim2claw.ops.workcell import inspect_workcell
result=inspect_workcell(Path(sys.argv[1]),Path(sys.argv[2]))
print(json.dumps({'plan_valid':result['plan_valid'],'sources':result['source_verification']}))
"""
    result = subprocess.run([sys.executable, "-c", code, str(root), str(peer)], capture_output=True, text=True, timeout=10, check=True)
    assert json.loads(result.stdout) == {"plan_valid": True, "sources": "hash_verified"}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Named pipes unavailable")
def test_fifo_input_cannot_wait_for_an_external_writer(workspace: tuple) -> None:
    root, peer, _ = workspace
    path = root / workcell.PLAN_PATH
    path.unlink()
    os.mkfifo(path)
    code = "from pathlib import Path; import json,sys; from sim2claw.ops.workcell import inspect_workcell; print(json.dumps(inspect_workcell(Path(sys.argv[1]),Path(sys.argv[2]))))"
    result = subprocess.run([sys.executable, "-c", code, str(root), str(peer)], capture_output=True, text=True, timeout=5, check=True)
    payload = json.loads(result.stdout)
    assert not payload["plan_valid"]
    assert "regular file" in payload["errors"][0]


@pytest.mark.parametrize("mode,expected_code,verification", [
    ("partial", 0, "partial"), ("complete", 0, "hash_verified"), ("rejected", 1, "rejected"),
])
def test_cli_exit_status_preserves_partial_full_and_rejected_metadata(workspace: tuple, capsys: pytest.CaptureFixture[str], mode: str, expected_code: int, verification: str) -> None:
    from sim2claw.ops import cli
    root, peer, plan = workspace
    if mode == "rejected":
        (peer / next(source["path"] for source in plan["sources"] if source["id"] == "duck_action")).write_bytes(b"source changed")
    args = ["--root", str(root), "--json", "workcell"]
    if mode != "partial":
        args.extend(["--peer-root", str(peer)])
    assert cli.main(args) == expected_code
    result = json.loads(capsys.readouterr().out)
    assert result["source_verification"] == verification
    assert result["gates"][0]["status"] == ("passed" if mode == "complete" else "unmet")
    assert result["execution_authorized"] is False


def test_cli_human_output_keeps_existing_hardware_and_unmet_gates_visible(workspace: tuple, capsys: pytest.CaptureFixture[str]) -> None:
    from sim2claw.ops import cli
    root, peer, _ = workspace
    assert cli.main(["--root", str(root), "workcell", "--peer-root", str(peer)]) == 0
    output = capsys.readouterr().out
    assert "existing duck battery and mount" in output
    assert "measurements still required" in output
    assert "static_scene: unmet" in output
    assert "no shared scene" in output
