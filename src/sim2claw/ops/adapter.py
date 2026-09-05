"""Versioned, non-executing exchange between robot-specific workspaces.

An envelope describes native interfaces. It never transforms actions, loads a
policy, runs a capability command, or turns schema validity into task authority.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import _git, _safe_path

VERSION = "robotics.workspace_exchange.v1"
SCHEMA_PATH = "configs/operations/workspace_adapter.v1.schema.json"
FIXTURE_PATH = "configs/operations/workspace_adapter.v1.fixtures.json"
JSON_LIMIT = 1024 * 1024
SOURCE_LIMIT = 4 * 1024 * 1024
PERMISSIONS = {"inspect": True, "execute": False, "mutate_sources": False,
               "train": False, "hardware": False, "promote": False, "paid_compute": False}


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _json(data: bytes) -> Any:
    def reject(value: str) -> None:
        raise ValueError(f"non-finite JSON value: {value}")
    def finite_float(value: str) -> float:
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("non-finite JSON number")
        return result
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_object_pairs,
                          parse_constant=reject, parse_float=finite_float)
    except RecursionError as error:
        raise ValueError("JSON nesting exceeds the inspection limit") from error


def _read(path: Path, limit: int) -> bytes:
    if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
        raise ValueError("inspection input must be a regular file")
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("inspection input must be a regular file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"input exceeds {limit} byte inspection limit: {path.name}")
    return data


def load_exchange(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("exchange file cannot be a symlink")
    value = _json(_read(path, JSON_LIMIT))
    if not isinstance(value, dict):
        raise ValueError("workspace exchange must contain an object")
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _schema(root: Path) -> tuple[dict[str, Any], str]:
    data = _read(_safe_path(root, SCHEMA_PATH), JSON_LIMIT)
    return _json(data), _sha(data)


def validate_workspace(root: Path, payload: dict[str, Any], source_root: Path | None = None) -> dict[str, Any]:
    """Schema and source identity inspection; commands remain inert strings."""
    from jsonschema import Draft202012Validator, FormatChecker

    schema, digest = _schema(root)
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"schema_version": "robotics.workspace_validation.v1", "valid": False,
                "workspace_id": None, "errors": ["workspace exchange must contain an object"],
                "source_verification": {"status": "unchecked", "checks": []},
                "execution_authorized": False, "policy_portable": False}
    try:
        encoded = json.dumps(payload, allow_nan=False).encode("utf-8")
        if len(encoded) > JSON_LIMIT:
            errors.append("exchange exceeds the inspection size limit")
    except (ValueError, TypeError, RecursionError):
        return {"schema_version": "robotics.workspace_validation.v1", "valid": False,
                "workspace_id": None, "errors": ["exchange must contain finite JSON values within the nesting limit"],
                "source_verification": {"status": "unchecked", "checks": []},
                "execution_authorized": False, "policy_portable": False}
    for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload):
        location = ".".join(str(value) for value in error.absolute_path) or "<root>"
        errors.append(f"{location}: {error.message}")
    timestamp = payload.get("generated_at", "")
    try:
        if not isinstance(timestamp, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})", timestamp):
            raise ValueError("timezone and full date/time are required")
        datetime.fromisoformat(timestamp.upper().replace("Z", "+00:00"))
    except ValueError:
        errors.append("generated_at: invalid timezone-qualified date-time")
    if payload.get("schema_version") != VERSION:
        errors.append("unsupported workspace exchange version")
    if payload.get("contract_sha256") != digest:
        errors.append("shared schema digest mismatch")
    permissions = payload.get("permissions")
    if (permissions != PERMISSIONS or not isinstance(permissions, dict)
            or any(type(value) is not bool for value in permissions.values())):
        errors.append("metadata exchange cannot grant execution or external authority")
    checks = []
    if not errors:
        ids = [item["id"] for item in payload["sources"]]
        if len(ids) != len(set(ids)):
            errors.append("duplicate source IDs")
        for group in ("profiles", "capabilities"):
            keys = [item["id"] for item in payload[group]]
            if len(keys) != len(set(keys)):
                errors.append(f"duplicate {group} IDs")
        references = list(payload["workspace"]["mandate"]["source_priority"])
        for profile in payload["profiles"]:
            references.extend(profile["source_ids"])
            action = profile["action"]
            dimension = action["dimension"]
            if type(dimension) is not int or len(action["ordered_names"]) != dimension or len(action["units"]) != dimension:
                errors.append(f"{profile['id']}: action names and per-axis units must match integer dimension")
            if len(set(action["ordered_names"])) != len(action["ordered_names"]):
                errors.append(f"{profile['id']}: action names are duplicated")
            observation = profile["observation"]["dimension"]
            if observation is not None and type(observation) is not int:
                errors.append(f"{profile['id']}: observation dimension must be an integer or null")
        if set(references) - set(ids):
            errors.append("source references do not resolve")
        for source in payload["sources"]:
            try:
                # A declared source path is always relative to its own producer.
                declared_path = Path(source["path"])
                if (declared_path.is_absolute() or ".." in declared_path.parts
                        or not declared_path.parts or "\\" in source["path"]
                        or "\x00" in source["path"]):
                    raise ValueError("path must be repository-relative without parent traversal")
                if source_root is not None:
                    data = _read(_safe_path(source_root, source["path"]), SOURCE_LIMIT)
                    matches = _sha(data) == source["sha256"]
                    checks.append({"id": source["id"], "path": source["path"], "matches": matches})
                    if not matches:
                        errors.append(f"source hash drift: {source['path']}")
            except (OSError, ValueError) as error:
                errors.append(f"source {source['id']}: {error}")
                checks.append({"id": source["id"], "path": source["path"], "matches": False})
        if source_root is not None:
            try:
                observed_head = _git(source_root, "rev-parse", "HEAD").strip()
                if observed_head != payload["workspace"]["repository"]["head"]:
                    errors.append("producer HEAD changed or source root belongs to another revision")
            except ValueError as error:
                errors.append(str(error))
    return {"schema_version": "robotics.workspace_validation.v1", "valid": not errors,
            "workspace_id": payload.get("workspace", {}).get("id") if isinstance(payload.get("workspace"), dict) else None,
            "errors": errors, "source_verification": {"status": "unchecked" if source_root is None else "drift" if errors else "hash_verified", "checks": checks},
            "claim": "Metadata schema and optional source-byte identity only; native ABI semantics and task acceptance remain native.",
            "execution_authorized": False, "policy_portable": False}


def _literal(source: bytes, name: str) -> Any:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"native declaration not found: {name}")


def export_workspace(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = _json(_read(_safe_path(root, "configs/agent/current_state_v1.json"), SOURCE_LIMIT))
    graph = _json(_read(_safe_path(root, manifest["campaign_graph_path"]), SOURCE_LIMIT))
    declarations = [
        ("agent_rules", "AGENTS.md", "native_work_mode"),
        ("goal", manifest["goal_path"], "current_status_projection"),
        ("manifest", "configs/agent/current_state_v1.json", "current_source_order"),
        ("campaign", manifest["campaign_graph_path"], "campaign_authority"),
        ("project_state", manifest["project_state_path"], "native_project_state"),
        ("queue", graph["source_bindings"]["queue"]["path"], "campaign_queue"),
        ("operations_plan", "docs/operations/plan.md", "separate_software_integration_lane"),
        ("adapter_design", "docs/operations/DOJO_ADAPTER.md", "bilateral_ownership_and_growth_contract"),
        ("adapter_schema", SCHEMA_PATH, "shared_metadata_schema"),
        ("adapter_fixtures", FIXTURE_PATH, "shared_synthetic_conformance_cases"),
        ("adapter_implementation", "src/sim2claw/ops/adapter.py", "native_metadata_export_and_validation"),
        ("source_episode", "configs/tasks/chess_pick_place_source_episode_v4.json", "native_source_episode_contract"),
        ("act_state", "configs/tasks/chess_pick_place_act_state_v1.json", "native_policy_observation_contract"),
        ("scene", "src/sim2claw/scene.py", "ordered_robot_joint_definition"),
        ("gateway", "src/sim2claw/physical_gateway.py", "physical_gateway_input_semantics"),
        ("physical_replay", "src/sim2claw/physical_sim_replay.py", "physical_to_sim_conversion_boundary"),
        ("exact_replay", "src/sim2claw/replay_eligibility.py", "timestamped_exact_replay_semantics"),
        ("proof_classes", "configs/sail/proof_classes_v1.json", "native_proof_classes"),
    ]
    sources, contents = [], {}
    for name, path, role in declarations:
        data = _read(_safe_path(root, path), SOURCE_LIMIT)
        contents[name] = data
        sources.append({"id": name, "path": path, "sha256": _sha(data), "role": role})
    native = _json(contents["source_episode"])
    act = _json(contents["act_state"])
    joints = list(_literal(contents["scene"], "ROBOT_JOINTS"))
    execution = native["execution"]
    if execution["action_dimension"] != len(joints):
        raise ValueError("native action dimension differs from native joint order")
    _, schema_digest = _schema(root)
    def profile(identifier: str, native_schema: str, scope: str, names: list[str], units: list[str],
                encoding: str, representation: str, transform: str, dimension: int | None,
                observation: str, hz: float | None, dt: float | None, clock: str,
                source_ids: list[str]) -> dict[str, Any]:
        return {"id": identifier, "robot_family": "so101", "native_schema": native_schema, "scope": scope,
                "action": {"dimension": len(names), "ordered_names": names, "units": units, "encoding": encoding,
                           "representation": representation, "transform_policy": transform},
                "observation": {"dimension": dimension, "description": observation,
                                "privileged_state_policy": "Evaluator-owned privileged state is never supplied by this metadata adapter."},
                "timing": {"control_hz": hz, "physics_step_s": dt, "clock": clock,
                           "frame_policy": "Native source/model binding; world poses use metres and wxyz quaternions where declared. No implicit conversion."},
                "source_ids": source_ids}
    profiles = [
        profile("so101.source_episode.v4", native["schema_version"], "one selected arm; combined scene has two six-actuator arms",
                joints, [execution["action_unit"]] * len(joints), "float32", execution["action_representation"],
                "Exact source actions; original scene and reset seed; no conversion by exchange.", None,
                "Model-agnostic RGB/language/robot/goal source fields; adapter-specific observation dimensionality.",
                execution["sample_hold_hz"], execution["physics_timestep_seconds"], native["episode"]["timebase"], ["source_episode", "scene"]),
        profile("so101.act_state.v1", act["schema_version"], "left-arm historical ACT state task; distinct from source episode v4 scene",
                act["action"]["features"], [act["action"]["unit"]] * act["action"]["dimension"], "float32",
                act["action"]["representation"], "Native ACT task declares actuator-range clipping; this is not an exact-replay claim.",
                act["observation"]["dimension"], "Frozen named robot/goal/contact features; same dimension as MicroDuck does not imply matching semantics.",
                None, None, "native_task_execution; no global control rate inferred", ["act_state", "scene"]),
        profile("so101.physical_gateway.v2", _literal(contents["gateway"], "GATEWAY_SCHEMA"), "single physical follower; description only",
                joints, ["degree"] * 5 + ["calibrated_gripper_0_100"], "little_endian_float64_c_order", "physical_follower_targets",
                "First five degree conversions and calibrated gripper mapping are separate; existing gripper clipping precludes silent exact-action reuse.",
                None, "Measured robot/camera state is artifact-specific and unavailable through this exchange.", None, None,
                "observed_host_intervals; exposure and actuator application timing not implied", ["gateway", "physical_replay", "scene"]),
        profile("so101.exact_replay.v1", _literal(contents["exact_replay"], "MANIFEST_SCHEMA"), "one timestamped arm action tensor",
                joints, [_literal(contents["exact_replay"], "EXPECTED_UNITS")["action"]] * len(joints),
                _literal(contents["exact_replay"], "ACTION_HASH_ENCODING"), "joint_position_target",
                "Identity transform only; no clipping, IK, offset, corrective suffix or assistance.", None,
                "Measured initial joint position and velocity plus declared action/source hashes.", None, None,
                "manifest_source_timestamps; no resampling or exposure-time inference", ["exact_replay", "scene"]),
    ]
    try:
        from ..agent_context import compile_agent_context
        current = compile_agent_context(root, role="manager")
        gate = {"status": "verified", "detail": f"Native role context {current['context_digest']}; execution_admitted={current['execution_admitted']}"}
    except ValueError as error:
        gate = {"status": "refused", "detail": str(error)}
    except (OSError, ImportError) as error:
        gate = {"status": "unavailable", "detail": str(error)}
    capabilities = [
        ("ops.status", "workspace", "sim2claw.ops.v1", "Current native authority refusal/state and local evidence coverage.", ["uv", "run", "--locked", "sim2claw", "ops", "--json", "status"]),
        ("ops.brief", "evidence", "sim2claw.ops.brief.v1", "Bounded cited context and advisory lessons; never execution authority.", ["uv", "run", "--locked", "sim2claw", "ops", "--json", "brief", "<query>"]),
        ("ops.map", "scene", "sim2claw.ops.architecture.v1", "Responsibilities and native scene/replay/evaluation component paths, with proposed gates distinct.", ["uv", "run", "--locked", "sim2claw", "ops", "--json", "map"]),
    ]
    payload = {"schema_version": VERSION, "contract_sha256": schema_digest, "generated_at": datetime.now(timezone.utc).isoformat(),
               "workspace": {"id": "sim2claw", "domain": "SO-101 manipulation simulation, reconstruction/metrology, replay and evidence validation",
                             "repository": {"head": _git(root, "rev-parse", "HEAD").strip(), "branch": _git(root, "branch", "--show-current").strip() or "detached", "dirty": bool(_git(root, "status", "--porcelain").strip())},
                             "mandate": {"summary": "Build interpretable manipulation simulation/evidence tools while preserving native campaign, evaluator and physical-gateway authority. The operations lane does not reactivate OR156.",
                                         "source_priority": ["agent_rules", "manifest", "project_state", "campaign", "queue", "goal", "operations_plan"]},
                             "owner_task": "01a070d8-106e-7e92-9867-7fe1ab6c7e8f"},
               "sources": sources, "profiles": profiles,
               "capabilities": [{"id": name, "kind": kind, "native_schema": schema, "availability": "implemented", "description": description, "read_only": True, "entrypoint": command} for name, kind, schema, description, command in capabilities],
               "evidence": {"native_classes": [row["id"] for row in _json(contents["proof_classes"])["classes"]],
                            "native_record_schemas": [native["episode"]["receipt_schema_version"], _literal(contents["exact_replay"], "REPORT_SCHEMA")],
                            "integrity_meaning": "Source hashes identify exported declaration bytes; no run artifact or evaluator receipt is verified by this export.",
                            "acceptance_meaning": "Native evaluator and campaign own acceptance. Metadata conformance grants no simulation, task or physical success.", "records_exported": False},
               "permissions": dict(PERMISSIONS), "native_gate": gate,
               "limitations": ["Capability entrypoints are inert descriptions; consumers never execute them from this envelope.",
                               "SO-101 profiles are not MicroDuck 14-action policies; matching observation dimensions do not imply shared feature meaning.",
                               "No scene, policy, action tensor, training log, media or held-out data is transferred in v1.",
                               "Native source declarations can drift during active work. Re-export and reverify exact bytes before using an updated contract.",
                               "Runtime environments, active processes and all physical/paid authority remain native."]}
    result = validate_workspace(root, payload, source_root=root)
    if not result["valid"]:
        raise ValueError("native export failed conformance: " + "; ".join(result["errors"]))
    return payload


def compare_workspaces(root: Path, peer: dict[str, Any], peer_root: Path | None = None) -> dict[str, Any]:
    local = export_workspace(root)
    local_validation = validate_workspace(root, local, root)
    peer_validation = validate_workspace(root, peer, peer_root)
    comparisons = []
    if peer_validation["valid"]:
        for left in local["profiles"]:
            for right in peer["profiles"]:
                fields = [name for name in ("robot_family", "native_schema", "scope", "action", "observation", "timing") if left[name] != right[name]]
                comparisons.append({"local": left["id"], "peer": right["id"], "matching_declared_fields": not fields,
                                    "differences": fields, "policy_portable": False,
                                    "reason": "Actual model, observation, action, reset and evaluator conformance require a separately reviewed robot-specific adapter."})
    compatible = local_validation["valid"] and peer_validation["valid"]
    return {"schema_version": "robotics.workspace_compatibility.v1", "passed": compatible,
            "metadata_compatible": compatible, "level": "source_bound_metadata" if peer_root is not None else "schema_only_metadata",
            "local_workspace": "sim2claw", "peer_workspace": peer_validation["workspace_id"],
            "local_validation": local_validation, "peer_validation": peer_validation, "profile_comparisons": comparisons,
            "policy_portable": False, "execution_authorized": False,
            "next_gate": "Versioned robot-specific scene/task/trace adapters with independent units, clock, reset/model and evaluator conformance."}


def check_conformance(root: Path) -> dict[str, Any]:
    """Run the shared synthetic corpus without reading producer source paths."""
    data = _read(_safe_path(root, FIXTURE_PATH), JSON_LIMIT)
    pack = _json(data)
    _, digest = _schema(root)
    if (pack.get("schema_version") != "robotics.workspace_conformance_fixtures.v1"
            or pack.get("contract_sha256") != digest or not pack.get("cases")):
        raise ValueError("conformance fixture version, shared schema digest or cases are invalid")
    cases = []
    for case in pack["cases"]:
        result = validate_workspace(root, case["payload"])
        passed = (type(case["expected_valid"]) is bool and result["valid"] is case["expected_valid"]
                  and result["source_verification"]["status"] == "unchecked"
                  and result["execution_authorized"] is False and result["policy_portable"] is False)
        cases.append({"id": case["id"], "expected_valid": case["expected_valid"],
                      "actual_valid": result["valid"], "passed": passed, "errors": result["errors"]})
    return {"schema_version": "robotics.workspace_conformance.v1", "passed": all(case["passed"] for case in cases),
            "contract_sha256": digest, "fixtures_sha256": _sha(data), "cases": cases,
            "claim": "Synthetic metadata rejection/acceptance only; real exports require separate source-bound checks.",
            "execution_authorized": False, "policy_portable": False}
