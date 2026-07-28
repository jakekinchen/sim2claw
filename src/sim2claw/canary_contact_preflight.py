"""Native-step forbidden-contact admission for one frozen P15 canary."""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .paths import REPO_ROOT
from .c922_exact_mode_calibration import DISTORTION_SCHEMA, INTRINSICS_SCHEMA
from .recorded_replay import (
    RecordedEpisode,
    canonical_json_sha256,
    load_sysid_config,
    sha256_file,
    simulate_and_align,
)
from .replay_eligibility import (
    ACTION_HASH_ENCODING,
    MANIFEST_SCHEMA,
    action_sha256,
    audit_exact_replay_manifest,
)
from .twin_candidate import (
    CANARY_INPUT_SCHEMA,
    CANARY_SCHEMA,
    CANDIDATE_SCHEMA,
    CANARY_MAX_ACCELERATION_RADIANS_S2,
    CANARY_MAX_VELOCITY_RADIANS_S,
    TwinCandidateError,
    _validate_p13,
    _validate_p9,
)


POLICY_SCHEMA = "sim2claw.zero_contact_forbidden_policy.v1"
ADMISSION_SCHEMA = "sim2claw.zero_contact_simulation_admission.v1"
DEFAULT_POLICY_PATH = (
    REPO_ROOT / "configs/evaluations/zero_contact_canary_policy_v1.json"
)


class CanaryContactError(RuntimeError):
    """The P16 input lineage or native-step contact audit failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CanaryContactError(message)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CanaryContactError(f"could not load {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    _require(not path.exists(), f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _name(
    model: mujoco.MjModel,
    object_type: mujoco.mjtObj,
    object_id: int,
) -> str:
    value = mujoco.mj_id2name(model, object_type, object_id)
    if value is None:
        return f"{object_type.name.lower()}#{object_id}"
    return value


def _body_subtree(model: mujoco.MjModel, root_name: str) -> set[int]:
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, root_name)
    _require(root >= 0, f"contact policy references unknown body: {root_name}")
    result: set[int] = set()
    for body_id in range(model.nbody):
        cursor = body_id
        while cursor > 0:
            if cursor == root:
                result.add(body_id)
                break
            cursor = int(model.body_parentid[cursor])
    _require(bool(result), f"contact policy body set is empty: {root_name}")
    return result


def _body_roots(model: mujoco.MjModel, values: Any, label: str) -> set[int]:
    _require(isinstance(values, list) and bool(values), f"{label} policy is empty")
    result: set[int] = set()
    for value in values:
        _require(isinstance(value, str) and bool(value), f"{label} body is invalid")
        result.update(_body_subtree(model, value))
    return result


def _id_ranges(values: set[int]) -> list[list[int]]:
    ordered = sorted(values)
    if not ordered:
        return []
    ranges: list[list[int]] = []
    start = previous = ordered[0]
    for value in ordered[1:]:
        if value != previous + 1:
            ranges.append([start, previous])
            start = value
        previous = value
    ranges.append([start, previous])
    return ranges


class NativeForbiddenContactAudit:
    """Compile one model-specific policy and inspect every native MuJoCo step."""

    def __init__(self, policy: Mapping[str, Any]) -> None:
        self.policy = copy.deepcopy(dict(policy))
        self.compiled: dict[str, Any] | None = None
        self.event_count = 0
        self.first_event: dict[str, Any] | None = None
        self.maximum_force_n: float | None = None
        self.step_count = 0
        self.first_time: float | None = None
        self.last_time: float | None = None
        self._observed_model: mujoco.MjModel | None = None

    def _compile(self, model: mujoco.MjModel) -> None:
        _require(
            self.policy.get("schema_version") == POLICY_SCHEMA,
            "contact policy schema changed",
        )
        _require(
            self.policy.get("model_kind") == "current_chess_scene",
            "contact policy model kind changed",
        )
        _require(
            isinstance(self.policy.get("policy_id"), str)
            and bool(self.policy["policy_id"]),
            "contact policy identity is empty",
        )
        root = self.policy.get("commanded_body_root")
        _require(isinstance(root, str) and bool(root), "commanded body policy is empty")
        commanded = _body_subtree(model, root)
        static = _body_roots(
            model,
            self.policy.get("forbidden_static_body_roots"),
            "static environment",
        )
        objects = _body_roots(
            model,
            self.policy.get("forbidden_object_body_roots"),
            "object",
        )
        other_arm = _body_roots(
            model,
            self.policy.get("forbidden_other_arm_body_roots"),
            "other arm",
        )
        category_bodies = {
            "commanded_arm": commanded,
            "static_environment": static,
            "objects": objects,
            "other_arm": other_arm,
        }
        collision_geoms = {
            geom_id
            for geom_id in range(model.ngeom)
            if int(model.geom_contype[geom_id]) != 0
            or int(model.geom_conaffinity[geom_id]) != 0
        }
        category_geoms = {
            category: {
                geom_id
                for geom_id in collision_geoms
                if int(model.geom_bodyid[geom_id]) in body_ids
            }
            for category, body_ids in category_bodies.items()
        }
        static_geom_names = self.policy.get("forbidden_static_geom_names")
        _require(
            isinstance(static_geom_names, list) and bool(static_geom_names),
            "static geom policy is empty",
        )
        for geom_name in static_geom_names:
            geom_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_GEOM, str(geom_name)
            )
            _require(
                geom_id >= 0,
                f"contact policy references unknown geom: {geom_name}",
            )
            _require(
                geom_id in collision_geoms,
                f"contact policy geom is not collision enabled: {geom_name}",
            )
            category_geoms["static_environment"].add(geom_id)

        covered = set().union(*category_geoms.values())
        covered_count = sum(len(values) for values in category_geoms.values())
        _require(
            covered_count == len(covered),
            "frozen contact-policy geom categories overlap",
        )
        unknown = collision_geoms.difference(covered)
        _require(
            not unknown,
            "collision-enabled model geoms are absent from the frozen policy: "
            f"{sorted(unknown)}",
        )
        for category, geom_ids in category_geoms.items():
            _require(bool(geom_ids), f"compiled {category} geom set is empty")

        exclusions = self.policy.get("excluded_internal_body_pairs")
        _require(
            isinstance(exclusions, list) and bool(exclusions),
            "internal exclusion policy is empty",
        )
        excluded_pairs: set[frozenset[int]] = set()
        for pair in exclusions:
            _require(
                isinstance(pair, list)
                and len(pair) == 2
                and all(isinstance(value, str) for value in pair),
                "internal exclusion pair is malformed",
            )
            ids = [
                mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, value)
                for value in pair
            ]
            _require(
                all(body_id >= 0 for body_id in ids),
                f"internal exclusion references unknown body: {pair}",
            )
            _require(
                set(ids).issubset(commanded),
                f"internal exclusion is outside the commanded arm: {pair}",
            )
            parent_child = (
                int(model.body_parentid[ids[0]]) == ids[1]
                or int(model.body_parentid[ids[1]]) == ids[0]
            )
            _require(parent_child, f"internal exclusion is not parent-child: {pair}")
            excluded_pairs.add(frozenset(ids))
        _require(
            isinstance(self.policy.get("internal_exclusion_rationale"), str)
            and bool(self.policy["internal_exclusion_rationale"]),
            "internal exclusion rationale is missing",
        )
        category_by_geom = {
            geom_id: category
            for category, geom_ids in category_geoms.items()
            for geom_id in geom_ids
        }
        self.compiled = {
            "category_bodies": category_bodies,
            "category_geoms": category_geoms,
            "category_by_geom": category_by_geom,
            "excluded_pairs": excluded_pairs,
        }

    def __call__(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        step_index: int,
    ) -> None:
        if self.compiled is None:
            self._compile(model)
            self._observed_model = model
        _require(step_index == self.step_count, "native-step observation is discontinuous")
        self.step_count += 1
        timestamp = float(data.time)
        self.first_time = timestamp if self.first_time is None else self.first_time
        self.last_time = timestamp
        compiled = self.compiled
        assert compiled is not None
        commanded = compiled["category_bodies"]["commanded_arm"]
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            geom_a, geom_b = (int(contact.geom[0]), int(contact.geom[1]))
            body_a = int(model.geom_bodyid[geom_a])
            body_b = int(model.geom_bodyid[geom_b])
            if body_a not in commanded and body_b not in commanded:
                continue
            if body_a in commanded and body_b in commanded:
                if body_a == body_b:
                    continue
                if frozenset((body_a, body_b)) in compiled["excluded_pairs"]:
                    continue
                reason = "forbidden_nonstructural_self_contact"
            else:
                other_geom = geom_b if body_a in commanded else geom_a
                category = compiled["category_by_geom"].get(other_geom)
                _require(
                    category in {"static_environment", "objects", "other_arm"},
                    "native contact includes an uncategorized forbidden geom",
                )
                reason = f"forbidden_commanded_arm_to_{category}"
            force = np.zeros(6, dtype=np.float64)
            mujoco.mj_contactForce(model, data, contact_index, force)
            force_n = float(np.linalg.norm(force[:3]))
            self.event_count += 1
            self.maximum_force_n = max(self.maximum_force_n or 0.0, force_n)
            if self.first_event is None:
                self.first_event = {
                    "native_step_index": step_index,
                    "time_seconds": timestamp,
                    "reason": reason,
                    "geom_a": _name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_a),
                    "geom_b": _name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_b),
                    "body_a": _name(model, mujoco.mjtObj.mjOBJ_BODY, body_a),
                    "body_b": _name(model, mujoco.mjtObj.mjOBJ_BODY, body_b),
                    "force_n": force_n,
                }

    def result(self, model: mujoco.MjModel) -> dict[str, Any]:
        _require(self.compiled is not None, "native-step contact policy was not compiled")
        _require(self.step_count > 0, "native-step contact observability is missing")
        compiled = self.compiled
        audited_sets = {}
        for category in (
            "commanded_arm",
            "static_environment",
            "objects",
            "other_arm",
        ):
            body_ids = compiled["category_bodies"][category]
            geom_ids = compiled["category_geoms"][category]
            audited_sets[category] = {
                "body_names": sorted(
                    _name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
                    for body_id in body_ids
                ),
                "collision_geom_count": len(geom_ids),
                "collision_geom_id_ranges": _id_ranges(geom_ids),
                "named_collision_geoms": sorted(
                    value
                    for geom_id in geom_ids
                    if (
                        value := mujoco.mj_id2name(
                            model, mujoco.mjtObj.mjOBJ_GEOM, geom_id
                        )
                    )
                    is not None
                ),
            }
        return {
            "policy_id": self.policy["policy_id"],
            "policy_digest": canonical_json_sha256(self.policy),
            "audited_sets": audited_sets,
            "internal_exclusions": {
                "body_pairs": self.policy["excluded_internal_body_pairs"],
                "rationale": self.policy["internal_exclusion_rationale"],
            },
            "native_step_count": self.step_count,
            "native_time_window_seconds": [self.first_time, self.last_time],
            "forbidden_contact_event_count": self.event_count,
            "first_forbidden_contact": self.first_event,
            "maximum_forbidden_contact_force_n": self.maximum_force_n,
            "passed": self.event_count == 0,
        }


def _validated_actions(canary: Mapping[str, Any]) -> np.ndarray:
    payload = canary.get("frozen_action_payload")
    _require(isinstance(payload, Mapping), "frozen action payload is missing")
    _require(
        payload.get("encoding") == ACTION_HASH_ENCODING,
        "frozen action encoding changed",
    )
    shape = payload.get("shape")
    _require(
        isinstance(shape, list)
        and len(shape) == 2
        and all(isinstance(value, int) and value > 0 for value in shape),
        "frozen action shape is invalid",
    )
    try:
        raw = base64.b64decode(str(payload["base64"]), validate=True)
        actions = np.frombuffer(raw, dtype="<f8").reshape(tuple(shape))
    except (KeyError, ValueError) as error:
        raise CanaryContactError("frozen action bytes are invalid") from error
    digest = action_sha256(actions)
    _require(payload.get("sha256") == digest, "frozen action payload hash drifted")
    _require(
        payload.get("simulation_consumer_sha256") == digest,
        "P15 simulation-consumer action hash drifted",
    )
    for field in ("requested_actions", "applied_actions"):
        try:
            value = np.asarray(canary[field], dtype="<f8", order="C")
        except (KeyError, TypeError, ValueError) as error:
            raise CanaryContactError(f"{field} is invalid") from error
        _require(
            value.shape == actions.shape
            and value.tobytes(order="C") == raw,
            f"{field} is not byte-identical to the frozen payload",
        )
    _require(
        canary.get("requested_action_sha256") == digest
        and canary.get("applied_action_sha256") == digest,
        "canary action hash lineage drifted",
    )
    return actions.copy()


def _candidate_digest(candidate: Mapping[str, Any]) -> str:
    sources = candidate.get("sources")
    _require(isinstance(sources, Mapping) and bool(sources), "candidate sources are missing")
    source_hashes = {}
    for name, value in sources.items():
        _require(
            isinstance(value, Mapping) and isinstance(value.get("sha256"), str),
            f"candidate source hash is missing: {name}",
        )
        source_hashes[name] = value["sha256"]
    core = {
        "identity": candidate["identity"],
        "source_hashes": source_hashes,
        "baseline_sha256": candidate["baseline"]["sha256"],
        "candidate_config_sha256": candidate["candidate_config_sha256"],
        "applied_parameters": candidate["applied_parameters"],
        "unapplied_fields": candidate["unapplied_fields"],
    }
    return canonical_json_sha256(core)


def evaluate_canary_contact_preflight(
    *,
    candidate_path: Path,
    canary_path: Path,
    baseline_path: Path,
    p8_intrinsics_path: Path | None = None,
    p8_distortion_path: Path | None = None,
    p9_admission_path: Path,
    p13_transform_path: Path | None = None,
    p13_board_fit_path: Path | None = None,
    policy_path: Path = DEFAULT_POLICY_PATH,
    output_path: Path,
    synthetic_fixture_mode: bool = False,
    simulation_only: bool = False,
) -> dict[str, Any]:
    """Evaluate exact P15 action bytes and stop before every hardware surface."""

    paths: dict[str, Path] = {
        "candidate": candidate_path.resolve(),
        "canary": canary_path.resolve(),
        "baseline": baseline_path.resolve(),
        "policy": policy_path.resolve(),
        "p9": p9_admission_path.resolve(),
    }
    if not simulation_only:
        _require(
            p8_intrinsics_path is not None
            and p8_distortion_path is not None
            and p13_transform_path is not None
            and p13_board_fit_path is not None,
            "exact contact preflight requires P8 and P13 artifacts",
        )
        paths.update(
            {
                "p8_intrinsics": p8_intrinsics_path.resolve(),
                "p8_distortion": p8_distortion_path.resolve(),
                "p13_transform": p13_transform_path.resolve(),
                "p13_board_fit": p13_board_fit_path.resolve(),
            }
        )
    output_path = output_path.resolve()
    _require(not output_path.exists(), f"refusing to overwrite existing output: {output_path}")
    baseline_before = paths["baseline"].read_bytes()
    candidate = _read_json(paths["candidate"], "P15 candidate")
    canary = _read_json(paths["canary"], "P15 canary")
    policy = _read_json(paths["policy"], "forbidden-contact policy")
    p9 = _read_json(paths["p9"], "P9 admission")
    p8_intrinsics = _read_json(paths["p8_intrinsics"], "P8 intrinsics") if not simulation_only else None
    p8_distortion = _read_json(paths["p8_distortion"], "P8 distortion") if not simulation_only else None
    p13_transform = _read_json(paths["p13_transform"], "P13 transform") if not simulation_only else None
    p13_board_fit = _read_json(paths["p13_board_fit"], "P13 board fit") if not simulation_only else None
    baseline = load_sysid_config(paths["baseline"])
    baseline.pop("_config_path", None)
    baseline.pop("_config_sha256", None)
    baseline_sha256 = sha256_file(paths["baseline"])
    _require(candidate.get("schema_version") == CANDIDATE_SCHEMA, "candidate schema changed")
    _require(canary.get("schema_version") == MANIFEST_SCHEMA, "canary replay schema changed")
    _require(canary.get("canary_schema_version") == CANARY_SCHEMA, "canary schema changed")
    expected_synthetic = bool(synthetic_fixture_mode)
    _require(
        canary.get("synthetic") is expected_synthetic,
        "canary synthetic proof class does not match fixture mode",
    )
    _require(
        candidate.get("status")
        == (
            "synthetic_fixture_valid"
            if expected_synthetic
            else ("simulation_only_partial" if simulation_only else "configuration_valid")
        ),
        "candidate proof class does not match fixture mode",
    )
    _require(
        candidate.get("identity") == canary.get("identity"),
        "candidate/canary identity drifted",
    )
    _require(
        candidate.get("physical_authority") is False
        and candidate.get("evaluator_admission") is False
        and canary.get("physical_authority") is False
        and canary.get("evaluator_admission") is False,
        "P15 candidate or canary widened authority",
    )
    _require(candidate.get("simulation_only", False) is simulation_only, "candidate simulation-only mode drifted")
    _require(canary.get("simulation_only", False) is simulation_only, "canary simulation-only mode drifted")
    if not simulation_only:
        for value, schema, label in (
            (p8_intrinsics, INTRINSICS_SCHEMA, "P8 intrinsics"),
            (p8_distortion, DISTORTION_SCHEMA, "P8 distortion"),
        ):
            assert value is not None
            _require(value.get("schema_version") == schema, f"{label} schema changed")
            _require(
                value.get("camera_id") == candidate["identity"]["camera_id"]
                and value.get("evaluator_owned") is True
                and value.get("self_scored") is False,
                f"{label} identity or ownership changed",
            )
            _require(
                bool(value.get("synthetic", False)) is expected_synthetic,
                f"{label} synthetic proof class does not match fixture mode",
            )
    try:
        _validate_p9(
            p9,
            baseline,
            baseline_sha256=baseline_sha256,
            synthetic_fixture_mode=synthetic_fixture_mode,
        )
        p13_identity = (
            _validate_p13(
                p13_transform,
                p13_board_fit,
                synthetic_fixture_mode=synthetic_fixture_mode,
            )
            if not simulation_only
            else None
        )
    except TwinCandidateError as error:
        raise CanaryContactError(str(error)) from error
    _require(
        p9.get("identity")
        == {
            "robot": candidate["identity"]["robot"],
            "workspace_pose_id": candidate["identity"]["workspace_pose_id"],
        },
        "P9 robot/workspace identity drifted",
    )
    if not simulation_only:
        assert p13_identity is not None and p13_transform is not None
        _require(
            p13_identity
            == {
                "camera_id": candidate["identity"]["camera_id"],
                "workspace_pose_id": candidate["identity"]["workspace_pose_id"],
                "board_pose_id": candidate["identity"]["board_pose_id"],
            },
            "P13 camera/workspace/board identity drifted",
        )
        _require(
            candidate.get("sources", {}).get("p13_transform", {}).get("sha256")
            == sha256_file(paths["p13_transform"])
            and candidate.get("sources", {}).get("p13_board_fit", {}).get("sha256")
            == sha256_file(paths["p13_board_fit"]),
            "P13 source hashes drifted from the candidate",
        )
        p13_hashes = p13_transform.get("input_hashes")
        _require(
            isinstance(p13_hashes, Mapping)
            and p13_hashes.get("intrinsics_sha256")
            == sha256_file(paths["p8_intrinsics"])
            and p13_hashes.get("distortion_sha256")
            == sha256_file(paths["p8_distortion"]),
            "P8 source hashes drifted from P13",
        )
    else:
        for name, descriptor in candidate.get("sources", {}).items():
            if name == "p9":
                continue
            _require(
                isinstance(descriptor, Mapping)
                and isinstance(descriptor.get("path"), str)
                and sha256_file(Path(descriptor["path"])) == descriptor.get("sha256"),
                f"simulation-only source hash drifted: {name}",
            )
        geometry = candidate.get("geometry_provenance")
        _require(
            isinstance(geometry, Mapping)
            and geometry.get("transform_applied") is False
            and geometry.get("metric_geometry_available") is False
            and geometry.get("physical_promotion_requires_p13") is True,
            "simulation-only geometry provenance is invalid",
        )
    _require(
        candidate.get("sources", {}).get("p9", {}).get("sha256") == sha256_file(paths["p9"]),
        "P9 source hash drifted from the candidate",
    )
    _require(
        candidate.get("candidate_config_sha256")
        == canonical_json_sha256(candidate.get("candidate_config")),
        "candidate config hash drifted",
    )
    candidate_config_before = candidate["candidate_config_sha256"]
    _require(
        candidate.get("candidate_digest") == _candidate_digest(candidate)
        and canary.get("candidate_digest") == candidate.get("candidate_digest"),
        "candidate digest drifted",
    )
    _require(
        candidate.get("baseline", {}).get("sha256") == baseline_sha256
        and candidate.get("sources", {}).get("baseline", {}).get("sha256")
        == baseline_sha256
        and baseline.get("config_id")
        == candidate.get("candidate_config", {}).get("config_id"),
        "baseline config hash or identity drifted",
    )
    _require(
        candidate["candidate_config"].get("model", {}).get("kind")
        == policy.get("model_kind"),
        "candidate model kind drifted from contact policy",
    )
    actions = _validated_actions(canary)
    _require(
        audit_exact_replay_manifest(paths["canary"])["exact_replay_eligible"] is True,
        "canary no longer passes exact replay eligibility",
    )
    timestamps = np.asarray(canary.get("timestamps_seconds"), dtype=np.float64)
    _require(
        timestamps.shape == (actions.shape[0],)
        and np.all(np.isfinite(timestamps))
        and np.all(np.diff(timestamps) > 0),
        "canary timestamps are invalid",
    )
    initial = canary.get("initial_state")
    _require(isinstance(initial, Mapping), "canary initial state is missing")
    start = np.asarray(initial.get("joint_position"), dtype=np.float64)
    velocity = np.asarray(initial.get("joint_velocity"), dtype=np.float64)
    _require(
        start.shape == (actions.shape[1],)
        and velocity.shape == start.shape
        and np.all(np.isfinite(start))
        and np.all(np.isfinite(velocity))
        and actions[0].tobytes() == start.astype("<f8").tobytes(),
        "canary initial state drifted from frozen actions",
    )
    _require(
        isinstance(initial.get("measurement_id"), str)
        and bool(initial["measurement_id"])
        and isinstance(initial.get("measurement_sha256"), str)
        and len(initial["measurement_sha256"]) == 64,
        "canary measured initial-state evidence is missing",
    )
    delta_t = np.diff(timestamps)
    velocities = np.diff(actions, axis=0) / delta_t[:, None]
    accelerations = np.diff(velocities, axis=0) / delta_t[1:, None]
    maximum_velocity = float(np.max(np.abs(velocities)))
    maximum_acceleration = float(np.max(np.abs(accelerations)))
    _require(
        maximum_velocity <= CANARY_MAX_VELOCITY_RADIANS_S + 1e-12
        and maximum_acceleration <= CANARY_MAX_ACCELERATION_RADIANS_S2 + 1e-12,
        "canary kinematic bounds failed",
    )
    _require(
        actions[-1].tobytes() == actions[0].tobytes(),
        "canary does not return byte-exactly to start",
    )
    _require(
        np.all(actions[:, -1] == actions[0, -1]),
        "canary changes the gripper",
    )
    episode = RecordedEpisode(
        episode_id=str(canary["episode_id"]),
        proof_class=str(canary["proof_class"]),
        proof_class_category="synthetic" if expected_synthetic else "replay",
        column=None,
        joint_names=tuple(candidate["candidate_config"]["bindings"]["joint_names"]),
        initial_joint_position=start.copy(),
        initial_joint_position_units=("radian",) * actions.shape[1],
        initial_joint_velocity=velocity.copy(),
        initial_joint_velocity_units=("radian_per_second",) * actions.shape[1],
        timestamps=timestamps,
        original_timestamps=timestamps.copy(),
        commands=actions.copy(),
        measured=tuple({"joint_position": row.tolist()} for row in actions),
        initial_object_state={"status": "unavailable"},
        unavailable_observables={},
        source_path=paths["canary"],
        source_sha256=sha256_file(paths["canary"]),
        source_schema_version=CANARY_INPUT_SCHEMA,
        source_provenance={"chain_complete": True},
        joint_transform=None,
    )
    audit = NativeForbiddenContactAudit(policy)
    replay = simulate_and_align(
        episode,
        candidate["candidate_config"],
        model_base_directory=paths["baseline"].parent,
        native_step_observer=audit,
    )
    action_hash = action_sha256(actions)
    _require(
        replay["control_diagnostics"]["replay_input_action_sha256"] == action_hash
        and action_sha256(episode.commands) == action_hash,
        "simulation action-consumer hash drifted",
    )
    native = audit.result(audit_model(audit))
    _require(
        native["native_step_count"] == replay["timing"]["native_sample_count"],
        "native-step contact observability is incomplete",
    )
    _require(
        paths["baseline"].read_bytes() == baseline_before,
        "baseline config mutated during contact evaluation",
    )
    _require(
        canonical_json_sha256(candidate["candidate_config"])
        == candidate_config_before,
        "candidate config mutated during contact evaluation",
    )
    passed = bool(native["passed"])
    evaluator_path = Path(__file__).resolve()
    status = (
        "synthetic_fixture_no_contact_passed"
        if expected_synthetic and passed
        else "rejected_forbidden_contact"
        if not passed
        else "simulation_only_no_contact_passed"
        if simulation_only
        else "ready_for_operator_hardware_preflight"
    )
    receipt = {
        "schema_version": ADMISSION_SCHEMA,
        "status": status,
        "proof_class": "synthetic_fixture" if expected_synthetic else "simulation",
        "inputs": {
            name: {"sha256": sha256_file(path)}
            for name, path in paths.items()
        },
        "identity": copy.deepcopy(candidate["identity"]),
        "candidate_digest": candidate["candidate_digest"],
        "candidate_config_sha256": candidate["candidate_config_sha256"],
        "action_consumer_sha256": action_hash,
        "runtime": "cpu_mujoco_fp64_native_steps",
        "evaluator_identity": {
            "name": "sim2claw-native-step-zero-contact-admission",
            "version": "1",
            "executable_path": str(evaluator_path.relative_to(REPO_ROOT)),
            "executable_sha256": sha256_file(evaluator_path),
        },
        "evaluator_owned": True,
        "self_scored": False,
        "kinematic_gates": {
            "maximum_velocity_radians_s": maximum_velocity,
            "maximum_acceleration_radians_s2": maximum_acceleration,
            "return_to_exact_start": True,
            "gripper_unchanged": True,
            "passed": True,
        },
        "native_contact_audit": native,
        "simulation_no_contact_admitted": passed and not expected_synthetic,
        "ready_for_operator_hardware_preflight": passed and not expected_synthetic and not simulation_only,
        "p13_required_for_metric_or_physical": simulation_only,
        "stop_before_robot_gateway": True,
        "next_operator_command_display_only": (
            "uv run sim2claw physical-gateway-preflight"
            if status == "ready_for_operator_hardware_preflight"
            else "STOP: resolve the native forbidden-contact verdict before any hardware preflight"
        ),
        "gateway_constructed": False,
        "physical_execution_admitted": False,
        "physical_authority": False,
    }
    _write_once(output_path, receipt)
    return {
        **receipt,
        "receipt_path": str(output_path),
        "receipt_sha256": sha256_file(output_path),
    }


def audit_model(audit: NativeForbiddenContactAudit) -> mujoco.MjModel:
    """Return the observed model without exposing a simulator construction API."""

    model = getattr(audit, "_observed_model", None)
    _require(model is not None, "native-step model observation is missing")
    return model
