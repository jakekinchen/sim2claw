"""Inspect the arm/duck plan without constructing a world or dispatching actions."""

from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapter import JSON_LIMIT, SOURCE_LIMIT, _json, _literal, _read
from .core import _safe_path

PLAN_PATH = "configs/operations/arm_duck_workcell.v1.json"
VERSION = "robotics.arm_duck_workcell_plan.v1"
PERMISSIONS = {"inspect": True, "simulate": False, "train": False,
               "hardware": False, "paid_compute": False, "promote": False}
ARM_NAMES = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
DUCK_NAMES = ("left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
              "neck_pitch", "head_pitch", "head_yaw", "head_roll", "right_hip_yaw",
              "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle")
SOURCE_PATHS = {
    "arm_model": ("sim2claw", "third_party/mujoco_menagerie/robotstudio_so101/so101.xml"),
    "arm_action": ("sim2claw", "configs/tasks/chess_pick_place_source_episode_v4.json"),
    "arm_joints": ("sim2claw", "src/sim2claw/scene.py"),
    "duck_model": ("microduck-rl-genesis", "microduck/assets/microduck/robot_allcollisions.xml"),
    "duck_action": ("microduck-rl-genesis", "microduck_contract/interface/action-v1.json"),
    "duck_observation": ("microduck-rl-genesis", "microduck_contract/interface/observation-v1.json"),
    "duck_control": ("microduck-rl-genesis", "microduck_contract/interface/control-v1.json"),
    "battery_mesh": ("microduck-rl-genesis", "microduck/assets/microduck/assets/np_f970.stl"),
    "mount_mesh": ("microduck-rl-genesis", "microduck/assets/microduck/assets/power_support.stl"),
    "apple_runtime": ("microduck-rl-genesis", "environments/apple/requirements.lock"),
}
GATE_DEPENDENCIES = {
    "static_scene": ["declaration_check"], "controller_routing": ["static_scene"],
    "hardware_measurements": ["declaration_check"],
    "battery_mechanics": ["hardware_measurements", "controller_routing"],
    "service_task": ["battery_mechanics"], "local_training": ["service_task"],
    "independent_validation": ["local_training"],
}
GATE_IDS = set(GATE_DEPENDENCIES)
REMOTE_REQUEST_FIELDS = ["unresolved_local_gate", "exact_checkpoint_and_source_hashes", "fixed_cases_and_seeds",
                         "instance_identity", "maximum_duration", "maximum_cost", "retained_receipt_paths", "stop_or_delete_condition"]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _keys(value: Any, names: str, label: str) -> None:
    _require(isinstance(value, dict) and set(value) == set(names.split()), f"{label}: unsupported or missing fields")


def _equal(value: Any, expected: Any, label: str) -> None:
    # JSON booleans and integral floats must not masquerade as integer counters.
    _require(type(value) is type(expected) and value == expected, f"{label}: expected {expected!r}")
    if isinstance(expected, list):
        for index, (item, reference) in enumerate(zip(value, expected, strict=True)):
            _equal(item, reference, f"{label}[{index}]")


def _finite_number(value: Any) -> bool:
    try:
        return type(value) in {int, float} and math.isfinite(value)
    except OverflowError:
        return False


def _text(value: Any, label: str) -> None:
    _require(isinstance(value, str) and bool(value.strip()) and len(value) <= 8192, f"{label}: expected bounded text")


def _document(data: bytes) -> Any:
    value = _json(data)
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        _require(depth <= 32 and count <= 50000, "JSON structure exceeds the inspection limit")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, float):
            _require(math.isfinite(item), "JSON numbers must be finite")
    return value


def _relative(path: Any) -> None:
    _require(isinstance(path, str) and bool(path) and "\\" not in path and "\x00" not in path,
             "source path must be a repository-relative path")
    parsed = Path(path)
    _require(not parsed.is_absolute() and bool(parsed.parts) and ".." not in parsed.parts,
             "source path must be repository-relative without parent traversal")


def _acyclic(parents: dict[str, list[str]], anchor: str, label: str) -> None:
    complete = {anchor}
    pending = dict(parents)
    while pending:
        ready = [name for name, dependencies in pending.items() if set(dependencies) <= complete]
        _require(bool(ready), f"{label}: unresolved or cyclic dependencies")
        for name in ready:
            complete.add(name)
            del pending[name]


def _validate_plan(plan: Any) -> None:
    _keys(plan, "schema_version id status mechanical_target sources actors clock world contact_requirements unmet_gates compute_policy permissions claim", "plan")
    _equal(plan["schema_version"], VERSION, "schema_version")
    _equal(plan["id"], "arm-duck-existing-battery", "plan id")
    _equal(plan["status"], "declaration_only", "plan status")
    _keys(plan["permissions"], " ".join(PERMISSIONS), "permissions")
    for name, value in PERMISSIONS.items():
        _equal(plan["permissions"][name], value, f"permissions.{name}")
    target = plan["mechanical_target"]
    _keys(target, "hardware redesign_allowed battery_source_id mount_source_id measurements_verified", "mechanical_target")
    for name, value in {"hardware": "existing_duck_battery_and_mount", "redesign_allowed": False,
                        "battery_source_id": "battery_mesh", "mount_source_id": "mount_mesh",
                        "measurements_verified": False}.items():
        _equal(target[name], value, f"mechanical_target.{name}")
    _require(isinstance(plan["sources"], list) and len(plan["sources"]) == len(SOURCE_PATHS), "expected ten direct source bindings")
    seen = set()
    for source in plan["sources"]:
        _keys(source, "id workspace_id path sha256", "source")
        name = source["id"]
        _require(isinstance(name, str) and name in SOURCE_PATHS and name not in seen, "unsupported or duplicate source ID")
        seen.add(name)
        _relative(source["path"])
        _require((source["workspace_id"], source["path"]) == SOURCE_PATHS[name], f"{name}: unsupported native source location")
        _require(isinstance(source["sha256"], str) and bool(re.fullmatch("[0-9a-f]{64}", source["sha256"])), f"{name}: invalid SHA-256")
    _require(isinstance(plan["actors"], list) and len(plan["actors"]) == 2, "expected exactly two actors")
    for actor, name, names, workspace, rate, ticks, representation, refs in zip(
        plan["actors"], ("arm", "duck"), (ARM_NAMES, DUCK_NAMES), ("sim2claw", "microduck-rl-genesis"),
        (20, 50), (10, 4), ("absolute_joint_position_target", "unfiltered_delta_from_home_rad"),
        (["arm_action", "arm_joints"], ["duck_action", "duck_observation", "duck_control"]), strict=True,
    ):
        _keys(actor, "id namespace workspace_id model_source_id floating_base action", "actor")
        for field, expected in {"id": name, "namespace": name + "_", "workspace_id": workspace,
                                "model_source_id": name + "_model", "floating_base": name == "duck"}.items():
            _equal(actor[field], expected, f"{name}.{field}")
        action = actor["action"]
        _keys(action, "dimension ordered_names representation unit dtype control_hz ticks_per_action source_ids", f"{name}.action")
        for field, expected in {"dimension": len(names), "ordered_names": list(names), "representation": representation,
                                "unit": "rad", "dtype": "float32", "control_hz": rate,
                                "ticks_per_action": ticks, "source_ids": refs}.items():
            _equal(action[field], expected, f"{name}.action.{field}")
    clock = plan["clock"]
    _keys(clock, "physics_dt_s tick_hz timebase action_hold implicit_resampling_allowed phase_period_ticks", "clock")
    for field, expected in {"physics_dt_s": 0.005, "tick_hz": 200, "timebase": "integer_simulation_tick",
                            "action_hold": "zero_order_hold_per_actor", "implicit_resampling_allowed": False,
                            "phase_period_ticks": 20}.items():
        _equal(clock[field], expected, f"clock.{field}")
    world = plan["world"]
    _keys(world, "length_unit up_axis quaternion_order frames physical_poses_bound", "world")
    for field, expected in {"length_unit": "metre", "up_axis": "+Z", "quaternion_order": "wxyz", "physical_poses_bound": False}.items():
        _equal(world[field], expected, f"world.{field}")
    _require(isinstance(world["frames"], list) and len(world["frames"]) == 5, "expected five declared frames")
    frame_ids = {"world", "service_fixture", "arm_base", "duck_base", "battery_mount"}
    frames = {}
    for frame in world["frames"]:
        _keys(frame, "id parent pose_measured", "frame")
        _require(isinstance(frame["id"], str) and frame["id"] in frame_ids and frame["id"] not in frames, "invalid or duplicate frame ID")
        _equal(frame["pose_measured"], False, "frame.pose_measured")
        parent = frame["parent"]
        _require(parent is None if frame["id"] == "world" else isinstance(parent, str) and parent in frame_ids,
                 "frame parent must resolve to the declared world hierarchy")
        frames[frame["id"]] = [] if parent is None else [parent]
    _acyclic({name: dependencies for name, dependencies in frames.items() if name != "world"}, "world", "frames")
    _require(frames["battery_mount"] == ["duck_base"], "battery_mount must remain attached to duck_base")
    _require(isinstance(plan["contact_requirements"], list) and len(plan["contact_requirements"]) >= 3, "explicit contact requirements are required")
    for requirement in plan["contact_requirements"]:
        _text(requirement, "contact requirement")
    _require(isinstance(plan["unmet_gates"], list) and len(plan["unmet_gates"]) == len(GATE_IDS), "expected the seven unmet development gates")
    gates = {}
    for gate in plan["unmet_gates"]:
        _keys(gate, "id requires acceptance", "gate")
        name = gate["id"]
        _require(isinstance(name, str) and name in GATE_IDS and name not in gates, "invalid or duplicate gate ID")
        refs = gate["requires"]
        _require(isinstance(refs, list) and refs and all(isinstance(ref, str) for ref in refs) and len(refs) == len(set(refs)), "gate dependencies must be distinct IDs")
        _equal(refs, GATE_DEPENDENCIES[name], f"gate {name}.requires")
        _text(gate["acceptance"], "gate acceptance")
        gates[name] = refs
    _acyclic(gates, "declaration_check", "gates")
    compute = plan["compute_policy"]
    _keys(compute, "default physics_candidate learner_candidate reference_evaluator use_active_training_environment_directly benchmark_required_before_backend_selection remote_role remote_provider remote_training_default remote_launch_authorized_by_plan remote_request_fields shutdown_after_bounded_job", "compute_policy")
    for field, expected in {"default": "local_mac", "use_active_training_environment_directly": False,
                            "benchmark_required_before_backend_selection": True, "remote_training_default": False,
                            "remote_launch_authorized_by_plan": False, "shutdown_after_bounded_job": True,
                            "remote_role": "last_resort_inference_or_validation", "remote_provider": "NVIDIA/Brev",
                            "remote_request_fields": REMOTE_REQUEST_FIELDS}.items():
        _equal(compute[field], expected, f"compute_policy.{field}")
    for field in ("physics_candidate", "learner_candidate", "reference_evaluator"):
        _text(compute[field], f"compute_policy.{field}")
    _text(plan["claim"], "claim")


def _model(data: bytes, actor: dict[str, Any]) -> None:
    text = data.decode("utf-8")
    _require("<!DOCTYPE" not in text.upper() and "<!ENTITY" not in text.upper(), "model DTD/entity declarations are not admitted")
    try:
        model = ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError(f"invalid native model XML: {error}") from error
    _require(model.tag == "mujoco", "expected a native MJCF model")
    compiler = model.find("compiler")
    _require(compiler is not None and compiler.get("angle") == "radian", "native model joint angles must explicitly use radians")
    names = actor["action"]["ordered_names"]
    world = model.find("worldbody")
    _require(world is not None, "native model has no worldbody")
    driven_joints = world.findall(".//joint")
    joints = [joint.get("name") for joint in driven_joints]
    _require(set(names) == set(joints) and len(names) == len(joints), "native model joint names differ from actor action names")
    _require(all(joint.get("type") == "hinge" for joint in driven_joints), "native driven joints must explicitly be scalar radian hinges")
    actuators = model.find("actuator")
    _require(actuators is not None and len(actuators) == len(names), "native model actuator count differs from action dimension")
    _require({item.get("joint") for item in actuators} == set(names), "native actuator joint bindings differ from named action buffer")
    _require(all(item.tag == "position" for item in actuators), "native actuators must explicitly be position-target actuators")
    free_count = len(world.findall(".//freejoint")) + sum(joint.get("type") == "free" for joint in world.findall(".//joint"))
    _require(free_count == int(actor["floating_base"]), "native free-base declaration differs from actor")


def _native(source_id: str, data: bytes, plan: dict[str, Any]) -> None:
    arm, duck = plan["actors"]
    if source_id in {"arm_model", "duck_model"}:
        _model(data, arm if source_id == "arm_model" else duck)
    elif source_id == "arm_joints":
        try:
            names = list(_literal(data, "ROBOT_JOINTS"))
        except (SyntaxError, TypeError, RecursionError) as error:
            raise ValueError("cannot inspect native ROBOT_JOINTS literal") from error
        _equal(names, arm["action"]["ordered_names"], "native ROBOT_JOINTS")
    elif source_id in {"arm_action", "duck_action", "duck_observation", "duck_control"}:
        native = _document(data)
        _require(isinstance(native, dict), "native declaration must be an object")
        if source_id == "arm_action":
            _equal(native.get("schema_version"), "sim2claw.canonical_manipulation_source_contract.v4", "native arm schema")
            execution = native.get("execution", {})
            _require(isinstance(execution, dict), "native arm execution must be an object")
            for field, expected in {"action_dimension": 6, "action_representation": arm["action"]["representation"],
                                    "action_unit": "rad", "sample_hold_hz": 20, "physics_timestep_seconds": 0.005,
                                    "physics_steps_per_action": 10, "exact_float32_action_replay_required_before_export": True,
                                    "replay_must_use_original_scene_and_reset_seed": True}.items():
                _equal(execution.get(field), expected, f"native arm execution.{field}")
        elif source_id == "duck_action":
            for field, expected in {"schema_version": "microduck.interface/v1", "interface_id": "microduck.action.v1",
                                    "dtype": "float32", "joint_order": list(DUCK_NAMES), "scale": 1.0,
                                    "semantics": duck["action"]["representation"], "shape": [1, 14]}.items():
                _equal(native.get(field), expected, f"native duck action.{field}")
        elif source_id == "duck_observation":
            for field, expected in {"schema_version": "microduck.interface/v1", "interface_id": "microduck.obs.v1",
                                    "dtype": "float32", "joint_order": list(DUCK_NAMES), "shape": [1, 61]}.items():
                _equal(native.get(field), expected, f"native duck observation.{field}")
            home = native.get("home_joint_position_rad")
            _require(isinstance(home, list) and len(home) == 14 and all(_finite_number(value) for value in home), "native duck home offsets must contain fourteen finite radian values")
        else:
            for field, expected in {"schema_version": "microduck.control/v1", "control_id": "microduck.control.50hz.v1",
                                    "action_filter": "none", "control_hz": 50, "decimation": 4, "physics_dt_s": 0.005}.items():
                _equal(native.get(field), expected, f"native duck control.{field}")


def _schedule(plan: dict[str, Any]) -> dict[str, Any]:
    actors = plan["actors"]
    return {
        "mode": "planning_only", "tick_hz": 200, "physics_dt_s": 0.005, "phase_period_ticks": 20,
        "preview_interval": "0 <= tick < 20; phases repeat every 20 ticks",
        "preview": [{"tick": tick, "time_s": tick / 200,
                     "due_buffers": [actor["id"] for actor in actors if tick % actor["action"]["ticks_per_action"] == 0]}
                    for tick in range(20) if any(tick % actor["action"]["ticks_per_action"] == 0 for actor in actors)],
        "buffers": [{"id": actor["id"], "dimension": actor["action"]["dimension"],
                     "qualified_names": [actor["namespace"] + name for name in actor["action"]["ordered_names"]],
                     "representation": actor["action"]["representation"], "dtype": "float32", "unit": "rad",
                     "ticks_per_action": actor["action"]["ticks_per_action"],
                     "updates_per_200_ticks": 200 // actor["action"]["ticks_per_action"],
                     "home_offset_source_id": "duck_observation" if actor["id"] == "duck" else None}
                    for actor in actors],
        "action_values_created": False, "actions_dispatched": False,
        "note": "Named buffers describe independent interfaces, not a portable 20-axis policy or total simulator state dimension.",
    }


def inspect_workcell(root: Path, peer_root: Path | None = None) -> dict[str, Any]:
    """Inspect only explicitly supplied roots; unverified mechanics stay unmet."""
    result: dict[str, Any] = {
        "schema_version": "robotics.arm_duck_workcell_inspection.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(), "plan_valid": False,
        "errors": [], "sources": [], "source_verification": "unchecked", "gates": [], "schedule": None,
        "execution_authorized": False, "simulation_executed": False, "actions_dispatched": False,
        "training_authorized": False, "hardware_authorized": False, "paid_compute_authorized": False,
        "claim": "Planning and direct-source declaration inspection only; no shared scene, mechanical fidelity or task acceptance is established.",
        "coverage": "Ten direct source bindings only. Transitive MJCF meshes/includes, runtime installation and native campaign admission are not verified.",
    }
    try:
        raw = _read(_safe_path(root, PLAN_PATH), JSON_LIMIT)
        result["plan_sha256"] = hashlib.sha256(raw).hexdigest()
        plan = _document(raw)
        _validate_plan(plan)
    except (OSError, ValueError) as error:
        result["errors"].append(str(error))
        return result
    result["plan_id"] = plan["id"]
    result["schedule"] = _schedule(plan)
    result["mechanical_target"] = plan["mechanical_target"]
    for source in plan["sources"]:
        check = {**source, "status": "unchecked", "native_declaration": "not_checked"}
        result["sources"].append(check)
        producer = root if source["workspace_id"] == "sim2claw" else peer_root
        if producer is None:
            check["reason"] = "Explicit peer root was not supplied"
            continue
        try:
            data = _read(_safe_path(producer, source["path"]), SOURCE_LIMIT)
            check["observed_sha256"] = hashlib.sha256(data).hexdigest()
            _require(check["observed_sha256"] == source["sha256"], "source SHA-256 drift")
            check["status"] = "hash_verified"
            _native(source["id"], data, plan)
            check["native_declaration"] = "checked" if source["id"] not in {"battery_mesh", "mount_mesh", "apple_runtime"} else "hash_only"
        except (OSError, ValueError) as error:
            check["status"] = "rejected"
            check["reason"] = str(error)
            result["errors"].append(f"{source['id']}: {error}")
    result["plan_valid"] = not result["errors"]
    complete = result["plan_valid"] and all(source["status"] == "hash_verified" for source in result["sources"])
    result["source_verification"] = "hash_verified" if complete else "rejected" if result["errors"] else "partial"
    result["gates"] = [{"id": "declaration_check", "status": "passed" if complete else "unmet",
                        "requires": [], "acceptance": "Plan and all ten direct native source declarations verified against explicit roots."}]
    result["gates"].extend({**gate, "status": "unmet"} for gate in plan["unmet_gates"])
    return result
