"""Guarded staged follower reposition for a D405 AprilTag view.

The compiler freezes three direct physical-space interpolations from one fresh
torque-off follower read.  Every stage is previewed in the current MuJoCo
scene, executed separately through the reviewed follower-only gateway, and
closed with torque off before the next stage can be considered.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import mujoco
import numpy as np

from .physical_canary import (
    EXCITATION_CONTROL_SOURCE,
    GATEWAY_SCHEMA,
    _default_gateway,
    _default_preflight,
    _gateway_identity,
    _physical_to_model_position,
)
from .recorded_replay import _compile_model
from .replay_eligibility import ACTION_HASH_ENCODING, action_sha256
from .scene import ROBOT_JOINTS


WRIST_VIEW_PACKET_SCHEMA = "sim2claw.wrist_view_reposition_packet.v1"
WRIST_VIEW_REVIEW_SCHEMA = "sim2claw.wrist_view_reposition_review.v1"
WRIST_VIEW_EXECUTION_SCHEMA = "sim2claw.wrist_view_reposition_execution.v1"
SAMPLE_HZ = 40
SAMPLES_PER_STAGE = 361
MAX_STAGE_EXCURSION_DEGREES = 90.0
MAX_SLEW_DEGREES_S = 10.0
EXPECTED_LIVE_ANCHOR_DEGREES = np.asarray(
    [-4.131868, -106.901099, 99.912088, -106.153846, -74.769231, 2.969121],
    dtype=np.float64,
)
STAGE_TARGETS_DEGREES = np.asarray(
    [
        [-20.383827, -64.520994, 31.204886, -16.153846, -86.104261, 2.969121],
        [-20.383827, -64.520994, 31.204886, 73.846154, -86.104261, 2.969121],
        [-20.383827, -64.520994, 31.204886, 90.0, -86.104261, 2.969121],
    ],
    dtype=np.float64,
)
COMPILE_ANCHOR_TOLERANCE_DEGREES = np.asarray(
    [0.5, 0.5, 0.5, 0.5, 0.5, 0.1], dtype=np.float64
)
STAGE_ANCHOR_TOLERANCE_DEGREES = np.asarray(
    [3.0, 3.0, 3.0, 3.0, 3.0, 0.5], dtype=np.float64
)
FINAL_TOLERANCE_DEGREES = np.asarray(
    [3.0, 3.0, 3.0, 3.0, 3.0, 5.0], dtype=np.float64
)
BASELINE_SELF_CONTACT_PAIRS = {
    tuple(sorted(("left_shoulder", "left_lower_arm"))),
    tuple(sorted(("left_shoulder", "left_wrist"))),
}


class WristViewRepositionError(RuntimeError):
    """A staged reposition contract or safety check failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WristViewRepositionError(message)


def _canonical(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WristViewRepositionError(f"could not load {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    _require(not path.exists(), f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _identity_and_limits(
    preflight: Mapping[str, Any],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray]:
    _require(
        preflight.get("passed") is True
        and preflight.get("schema_version") == GATEWAY_SCHEMA
        and preflight.get("control_source") == EXCITATION_CONTROL_SOURCE
        and preflight.get("real_leader_opened") is False
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False,
        "fresh follower-only torque-off preflight did not pass",
    )
    port = str(preflight.get("follower_port") or "")
    calibration = str(preflight.get("follower_calibration_sha256") or "")
    _require(port and len(calibration) == 64, "follower hardware identity is incomplete")
    values = [
        np.asarray(preflight.get(field), dtype=np.float64)
        for field in (
            "follower_start_degrees",
            "follower_calibrated_minimum",
            "follower_calibrated_maximum",
        )
    ]
    _require(
        all(value.shape == (6,) and np.all(np.isfinite(value)) for value in values),
        "follower preflight vectors must be finite six-vectors",
    )
    current, lower, upper = values
    _require(np.all(lower < upper), "follower calibrated limits are unordered")
    return (
        {
            "gateway_schema": GATEWAY_SCHEMA,
            "follower_port": port,
            "follower_calibration_sha256": calibration,
        },
        current,
        lower,
        upper,
    )


def _joint_delta(current: np.ndarray, expected: np.ndarray) -> np.ndarray:
    delta = current - expected
    delta[4] = (float(current[4]) - float(expected[4]) + 180.0) % 360.0 - 180.0
    return delta


def _contact_pair(model: mujoco.MjModel, contact: Any) -> tuple[str, str]:
    body_ids = [
        int(model.geom_bodyid[int(contact.geom1)]),
        int(model.geom_bodyid[int(contact.geom2)]),
    ]
    names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        or f"body#{body_id}"
        for body_id in body_ids
    ]
    return tuple(sorted((names[0], names[1])))


def preview_wrist_view_actions(
    stages: list[np.ndarray],
    candidate_manifest_path: Path,
) -> dict[str, Any]:
    """Preview exact staged float64 actions without dynamics or action repair."""

    candidate_manifest_path = candidate_manifest_path.resolve()
    manifest = _read_json(candidate_manifest_path, "candidate manifest")
    candidate_config = manifest.get("candidate_config")
    _require(
        isinstance(candidate_config, Mapping),
        "candidate manifest lacks its compiled config",
    )
    _require(
        (candidate_config.get("model") or {}).get("kind") == "current_chess_scene",
        "wrist-view preview requires the current chess scene",
    )
    model, _ = _compile_model(dict(candidate_config), base_directory=None)
    data = mujoco.MjData(model)
    joint_names = list((candidate_config.get("bindings") or {}).get("joint_names") or [])
    transform_joints = (
        ((candidate_config.get("physical_adapter") or {}).get("joint_transform") or {})
        .get("joints")
    )
    _require(
        len(joint_names) == len(ROBOT_JOINTS)
        and isinstance(transform_joints, list)
        and [joint.get("source_joint") for joint in transform_joints]
        == list(ROBOT_JOINTS)
        and [joint.get("simulator_joint") for joint in transform_joints]
        == joint_names,
        "candidate physical/simulator joint order changed",
    )
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    _require(all(joint_id >= 0 for joint_id in joint_ids), "candidate joint is missing")

    model_stages = [
        _physical_to_model_position(actions, candidate_config) for actions in stages
    ]
    initial_pairs: set[tuple[str, str]] | None = None
    initial_minimum: float | None = None
    global_minimum: float | None = None
    stage_reports: list[dict[str, Any]] = []
    for stage_index, (physical_actions, model_actions) in enumerate(
        zip(stages, model_stages, strict=True), start=1
    ):
        stage_pairs: set[tuple[str, str]] = set()
        stage_minimum: float | None = None
        for row_index, row in enumerate(model_actions):
            for joint_index, joint_id in enumerate(joint_ids):
                data.qpos[int(model.jnt_qposadr[joint_id])] = float(row[joint_index])
            data.qvel[:] = 0.0
            mujoco.mj_forward(model, data)
            row_pairs: set[tuple[str, str]] = set()
            row_distances: list[float] = []
            for contact_index in range(data.ncon):
                contact = data.contact[contact_index]
                row_pairs.add(_contact_pair(model, contact))
                row_distances.append(float(contact.dist))
            if stage_index == 1 and row_index == 0:
                initial_pairs = row_pairs
                initial_minimum = min(row_distances) if row_distances else None
                _require(
                    initial_pairs.issubset(BASELINE_SELF_CONTACT_PAIRS),
                    "initial pose has external or unexpected model contact",
                )
            _require(initial_pairs is not None, "preview initial contact was not observed")
            _require(
                row_pairs.issubset(initial_pairs),
                "staged reposition creates a new model contact pair",
            )
            stage_pairs.update(row_pairs)
            if row_distances:
                row_minimum = min(row_distances)
                stage_minimum = (
                    row_minimum
                    if stage_minimum is None
                    else min(stage_minimum, row_minimum)
                )
                global_minimum = (
                    row_minimum
                    if global_minimum is None
                    else min(global_minimum, row_minimum)
                )
        if initial_minimum is not None and stage_minimum is not None:
            _require(
                stage_minimum >= initial_minimum - 1e-9,
                "staged reposition worsens baseline model penetration",
            )
        stage_reports.append(
            {
                "stage_index": stage_index,
                "exact_physical_action_sha256": action_sha256(physical_actions),
                "sample_count": int(physical_actions.shape[0]),
                "observed_contact_pairs": [list(pair) for pair in sorted(stage_pairs)],
                "minimum_distance_m": stage_minimum,
                "external_contact_pairs": [],
                "no_new_or_worsened_kinematic_contact": True,
            }
        )
    return {
        "runtime": "cpu_mujoco_mj_forward",
        "candidate_manifest_path": str(candidate_manifest_path),
        "candidate_manifest_sha256": _sha256(candidate_manifest_path),
        "candidate_digest": manifest.get("candidate_digest"),
        "baseline_contact_pairs": [list(pair) for pair in sorted(initial_pairs or set())],
        "baseline_minimum_distance_m": initial_minimum,
        "minimum_distance_m": global_minimum,
        "contact_pairs_unchanged_or_removed_only": True,
        "external_contact_pairs": [],
        "no_new_or_worsened_kinematic_contact": True,
        "stages": stage_reports,
    }


def _decode_stage(stage: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, bytes]:
    payload = stage.get("frozen_action_payload") or {}
    _require(payload.get("encoding") == ACTION_HASH_ENCODING, "stage encoding changed")
    try:
        raw = base64.b64decode(str(payload["base64"]), validate=True)
        actions = np.frombuffer(raw, dtype="<f8").reshape(tuple(payload["shape"]))
        timestamps = np.asarray(stage["timestamps_seconds"], dtype="<f8")
    except (KeyError, TypeError, ValueError) as error:
        raise WristViewRepositionError("stage payload is malformed") from error
    _require(
        actions.shape == (SAMPLES_PER_STAGE, 6)
        and timestamps.shape == (SAMPLES_PER_STAGE,)
        and np.all(np.isfinite(actions))
        and np.all(np.isfinite(timestamps)),
        "stage arrays changed shape or contain non-finite values",
    )
    _require(
        action_sha256(actions) == stage.get("action_sha256")
        == payload.get("sha256")
        == payload.get("simulation_consumer_sha256")
        and hashlib.sha256(raw).hexdigest() == stage.get("action_bytes_sha256"),
        "stage exact action bytes drifted",
    )
    return actions, timestamps, raw


def _validate_packet(packet_path: Path) -> dict[str, Any]:
    packet = _read_json(packet_path.resolve(), "wrist-view packet")
    _require(
        packet.get("schema_version") == WRIST_VIEW_PACKET_SCHEMA
        and packet.get("plan_sha256")
        == _canonical({key: value for key, value in packet.items() if key != "plan_sha256"}),
        "wrist-view packet digest changed",
    )
    stages = packet.get("stages")
    _require(isinstance(stages, list) and len(stages) == 3, "packet must contain three stages")
    previous = np.asarray(packet["compile_anchor_degrees"], dtype=np.float64)
    for stage_index, stage in enumerate(stages, start=1):
        _require(stage.get("stage_index") == stage_index, "stage order changed")
        actions, timestamps, _ = _decode_stage(stage)
        target = np.asarray(stage["target_degrees"], dtype=np.float64)
        _require(
            actions[0].tobytes() == previous.astype("<f8").tobytes()
            and actions[-1].tobytes() == target.astype("<f8").tobytes(),
            "stage endpoints drifted",
        )
        _require(
            np.array_equal(
                timestamps,
                (np.arange(SAMPLES_PER_STAGE, dtype="<f8") + 1.0) / SAMPLE_HZ,
            ),
            "stage timestamps changed",
        )
        _require(
            float(np.max(np.abs(target - previous)))
            <= MAX_STAGE_EXCURSION_DEGREES + 1e-9,
            "stage excursion exceeds 90 degrees",
        )
        preview = stage.get("simulation_preview") or {}
        _require(
            preview.get("exact_physical_action_sha256") == stage["action_sha256"]
            and preview.get("no_new_or_worsened_kinematic_contact") is True
            and not preview.get("external_contact_pairs"),
            "stage simulation preview is not admitted",
        )
        previous = target
    return packet


def compile_wrist_view_reposition_packet(
    packet_path: Path,
    *,
    candidate_manifest_path: Path,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    preview_fn: Callable[[list[np.ndarray], Path], dict[str, Any]] = (
        preview_wrist_view_actions
    ),
) -> dict[str, Any]:
    """Freeze the three reviewed direct-interpolation stages from a fresh anchor."""

    preflight = (preflight_fn or _default_preflight)()
    identity, anchor, lower, upper = _identity_and_limits(preflight)
    _require(
        np.all(
            np.abs(_joint_delta(anchor, EXPECTED_LIVE_ANCHOR_DEGREES))
            <= COMPILE_ANCHOR_TOLERANCE_DEGREES
        ),
        "fresh follower pose no longer matches the reviewed live torque-off pose",
    )
    targets = STAGE_TARGETS_DEGREES.copy()
    _require(
        np.all(targets >= lower[None, :]) and np.all(targets <= upper[None, :]),
        "reviewed wrist-view target exceeds fresh calibrated limits",
    )
    timestamps = (np.arange(SAMPLES_PER_STAGE, dtype="<f8") + 1.0) / SAMPLE_HZ
    action_stages: list[np.ndarray] = []
    previous = anchor.astype("<f8")
    for target in targets:
        delta = target - previous
        _require(
            float(np.max(np.abs(delta))) <= MAX_STAGE_EXCURSION_DEGREES + 1e-9,
            "reviewed wrist-view stage exceeds 90 degrees",
        )
        actions = np.linspace(
            previous, target.astype("<f8"), SAMPLES_PER_STAGE, dtype=np.float64
        ).astype("<f8", copy=False)
        rates = np.abs(np.diff(actions, axis=0) / np.diff(timestamps)[:, None])
        _require(
            float(np.max(rates)) <= MAX_SLEW_DEGREES_S + 1e-9,
            "reviewed wrist-view stage exceeds 10 degrees/s",
        )
        _require(
            np.all(actions >= lower[None, :]) and np.all(actions <= upper[None, :]),
            "frozen wrist-view action exceeds calibrated limits",
        )
        action_stages.append(actions)
        previous = target.astype("<f8")
    preview = preview_fn(action_stages, candidate_manifest_path)
    _require(
        preview.get("no_new_or_worsened_kinematic_contact") is True
        and not preview.get("external_contact_pairs"),
        "simulation preview rejected the staged reposition",
    )
    preview_stages = preview.get("stages")
    _require(
        isinstance(preview_stages, list) and len(preview_stages) == len(action_stages),
        "simulation preview stage count changed",
    )
    stages: list[dict[str, Any]] = []
    previous = anchor.astype("<f8")
    for stage_index, (target, actions, stage_preview) in enumerate(
        zip(targets, action_stages, preview_stages, strict=True), start=1
    ):
        raw = actions.tobytes(order="C")
        digest = action_sha256(actions)
        _require(
            stage_preview.get("exact_physical_action_sha256") == digest,
            "simulation preview did not consume the exact stage bytes",
        )
        stages.append(
            {
                "stage_index": stage_index,
                "expected_anchor_degrees": previous.tolist(),
                "target_degrees": target.tolist(),
                "maximum_joint_excursion_degrees": float(
                    np.max(np.abs(target - previous))
                ),
                "timestamps_seconds": timestamps.tolist(),
                "frozen_action_payload": {
                    "encoding": ACTION_HASH_ENCODING,
                    "shape": list(actions.shape),
                    "base64": base64.b64encode(raw).decode("ascii"),
                    "sha256": digest,
                    "simulation_consumer_sha256": digest,
                    "hardware_consumer_must_use_same_bytes": True,
                    "units": ["degree"] * 5 + ["percent"],
                },
                "action_sha256": digest,
                "action_bytes_sha256": hashlib.sha256(raw).hexdigest(),
                "simulation_preview": stage_preview,
                "inspect_wrist_camera_before_next_stage": stage_index < 3,
            }
        )
        previous = target.astype("<f8")
    packet = {
        "schema_version": WRIST_VIEW_PACKET_SCHEMA,
        "kind": "follower_only_staged_d405_tag_view_reposition",
        "single_use_per_stage": True,
        "hardware_identity": identity,
        "compile_anchor_source": "fresh_torque_off_follower_read",
        "compile_anchor_degrees": anchor.tolist(),
        "reviewed_live_anchor_degrees": EXPECTED_LIVE_ANCHOR_DEGREES.tolist(),
        "calibrated_minimum_degrees": lower.tolist(),
        "calibrated_maximum_degrees": upper.tolist(),
        "sample_hz": SAMPLE_HZ,
        "samples_per_stage": SAMPLES_PER_STAGE,
        "maximum_stage_excursion_degrees": MAX_STAGE_EXCURSION_DEGREES,
        "maximum_slew_degrees_s": MAX_SLEW_DEGREES_S,
        "stage_anchor_tolerance_degrees": STAGE_ANCHOR_TOLERANCE_DEGREES.tolist(),
        "final_tolerance_degrees": FINAL_TOLERANCE_DEGREES.tolist(),
        "stages": stages,
        "simulation_preview": {
            key: value for key, value in preview.items() if key != "stages"
        },
        "candidate_manifest": {
            "path": str(candidate_manifest_path.resolve()),
            "sha256": _sha256(candidate_manifest_path.resolve()),
            "candidate_digest": preview.get("candidate_digest"),
        },
        "action_assistance": {
            "inverse_kinematics": False,
            "clipping": False,
            "offsets": False,
            "suffix_or_corrective_action": False,
        },
        "execution_contract": {
            "one_stage_per_invocation": True,
            "fresh_preflight_each_stage": True,
            "prior_stage_receipt_required_after_stage_1": True,
            "torque_off_on_every_close": True,
            "camera_opened_by_this_path": False,
        },
        "physical_motion_commanded": False,
        "physical_follower_torque_enabled": False,
        "physical_authority": False,
    }
    packet["plan_sha256"] = _canonical(packet)
    _write_once(packet_path, packet)
    return packet


def review_wrist_view_reposition_packet(
    packet_path: Path,
    output_path: Path,
    *,
    reviewer: str,
    decision_id: str,
) -> dict[str, Any]:
    """Seal an independent review receipt without changing the packet."""

    packet_path = packet_path.resolve()
    packet = _validate_packet(packet_path)
    reviewer = reviewer.strip()
    decision_id = decision_id.strip()
    _require(reviewer and decision_id, "reviewer and decision identity are required")
    receipt = {
        "schema_version": WRIST_VIEW_REVIEW_SCHEMA,
        "status": "admitted_for_one_execution_per_stage",
        "packet_path": str(packet_path),
        "packet_sha256": _sha256(packet_path),
        "plan_sha256": packet["plan_sha256"],
        "reviewer": reviewer,
        "decision_id": decision_id,
        "frozen_float64_actions_reviewed": True,
        "stage_excursions_reviewed": True,
        "bounded_slew_reviewed": True,
        "simulation_contact_preview_reviewed": True,
        "fresh_anchor_and_identity_checks_reviewed": True,
        "torque_off_close_reviewed": True,
        "clear_workcell_acknowledged": True,
        "camera_inspection_between_stages_acknowledged": True,
        "physical_authority": False,
    }
    _write_once(output_path, receipt)
    return receipt


def _validate_review(
    review_path: Path, packet_path: Path, packet: Mapping[str, Any]
) -> dict[str, Any]:
    review = _read_json(review_path.resolve(), "wrist-view review")
    _require(
        review.get("schema_version") == WRIST_VIEW_REVIEW_SCHEMA
        and review.get("status") == "admitted_for_one_execution_per_stage"
        and review.get("packet_sha256") == _sha256(packet_path)
        and review.get("plan_sha256") == packet.get("plan_sha256"),
        "wrist-view review is not bound to this packet",
    )
    fields = (
        "reviewer",
        "decision_id",
        "frozen_float64_actions_reviewed",
        "stage_excursions_reviewed",
        "bounded_slew_reviewed",
        "simulation_contact_preview_reviewed",
        "fresh_anchor_and_identity_checks_reviewed",
        "torque_off_close_reviewed",
        "clear_workcell_acknowledged",
        "camera_inspection_between_stages_acknowledged",
    )
    _require(all(review.get(field) for field in fields), "review receipt is incomplete")
    return review


def execute_wrist_view_reposition_stage(
    packet_path: Path,
    review_path: Path,
    output_directory: Path,
    *,
    stage_index: int,
    prior_receipt_path: Path | None = None,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    gateway_factory: Callable[[Any], Any] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute exactly one reviewed stage, then close the follower torque-off."""

    packet_path = packet_path.resolve()
    packet = _validate_packet(packet_path)
    _validate_review(review_path, packet_path, packet)
    _require(operator_acknowledged, "fresh operator acknowledgement is required")
    _require(stage_index in (1, 2, 3), "stage index must be 1, 2, or 3")
    if stage_index == 1:
        _require(prior_receipt_path is None, "stage 1 does not accept a prior receipt")
    else:
        _require(prior_receipt_path is not None, "later stages require the prior receipt")
        prior = _read_json(prior_receipt_path.resolve(), "prior execution receipt")
        _require(
            prior.get("schema_version") == WRIST_VIEW_EXECUTION_SCHEMA
            and prior.get("status") == "completed_wrist_view_reposition_stage"
            and prior.get("packet_sha256") == _sha256(packet_path)
            and prior.get("stage_index") == stage_index - 1
            and prior.get("physical_follower_torque_enabled") is False,
            "prior execution receipt does not admit this stage",
        )

    manifest = packet["candidate_manifest"]
    manifest_path = Path(manifest["path"]).resolve()
    _require(
        _sha256(manifest_path) == manifest["sha256"],
        "candidate manifest drifted after packet compilation",
    )
    stage = packet["stages"][stage_index - 1]
    actions, timestamps, _ = _decode_stage(stage)
    fresh_preview = preview_wrist_view_actions(
        [np.asarray(item, dtype="<f8") for item in [actions]],
        manifest_path,
    )
    _require(
        fresh_preview.get("no_new_or_worsened_kinematic_contact") is True
        and not fresh_preview.get("external_contact_pairs"),
        "fresh simulation preview rejected the stage",
    )

    preflight = (preflight_fn or _default_preflight)()
    identity, current, lower, upper = _identity_and_limits(preflight)
    _require(identity == packet["hardware_identity"], "follower identity drifted")
    expected_anchor = np.asarray(stage["expected_anchor_degrees"], dtype=np.float64)
    anchor_tolerance = np.asarray(
        packet["stage_anchor_tolerance_degrees"], dtype=np.float64
    )
    _require(
        np.all(np.abs(_joint_delta(current, expected_anchor)) <= anchor_tolerance),
        "fresh follower pose does not match this stage anchor",
    )
    _require(
        np.all(actions >= lower[None, :]) and np.all(actions <= upper[None, :]),
        "frozen actions exceed fresh calibrated limits",
    )

    output_directory = output_directory.resolve()
    receipt_path = output_directory / "execution_receipt.json"
    samples_path = output_directory / "joint_samples.jsonl"
    _require(
        not receipt_path.exists() and not samples_path.exists(),
        "refusing to overwrite wrist-view execution output",
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    samples_path.open("x").close()
    gateway = (
        gateway_factory or _default_gateway
    )(_gateway_identity(identity) if gateway_factory is None else identity)
    completed = 0
    actual = current.copy()
    started = clock_fn()
    error: Exception | None = None
    try:
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        opened_start = np.asarray(opened["follower_start_degrees"], dtype=np.float64)
        _require(
            np.all(
                np.abs(_joint_delta(opened_start, expected_anchor))
                <= anchor_tolerance
            ),
            "follower anchor drifted before the stage hold",
        )
        with samples_path.open("a", encoding="utf-8") as handle:
            for sample_index, (timestamp, target) in enumerate(
                zip(timestamps, actions, strict=True)
            ):
                delay = started + float(timestamp) - clock_fn()
                if delay > 0.0:
                    sleep_fn(delay)
                sample = gateway.sample(
                    float(timestamp), exact_requested_degrees=target
                )
                requested = np.asarray(
                    sample.get("follower_requested_degrees"), dtype="<f8"
                )
                sent = np.asarray(
                    sample.get("follower_command_degrees"), dtype="<f8"
                )
                _require(
                    requested.tobytes() == target.tobytes()
                    and sent.tobytes() == target.tobytes()
                    and not sample.get("rate_limited")
                    and not sample.get("safety_clamped"),
                    "gateway modified, clipped, or rate-limited a frozen action",
                )
                actual = np.asarray(
                    sample["follower_actual_position_degrees"], dtype=np.float64
                )
                handle.write(
                    json.dumps(
                        {
                            "sample_index": sample_index,
                            "timestamp_seconds": float(timestamp),
                            "source_action_sha256": stage["action_sha256"],
                            "requested_physical_units": target.tolist(),
                            **sample,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                completed += 1
        target = np.asarray(stage["target_degrees"], dtype=np.float64)
        residual = _joint_delta(actual, target)
        _require(
            np.all(
                np.abs(residual)
                <= np.asarray(packet["final_tolerance_degrees"], dtype=np.float64)
            ),
            "follower did not reach the staged target",
        )
    except Exception as caught:
        error = caught
    finally:
        try:
            gateway.close()
        except Exception as caught:
            error = error or caught

    residual = _joint_delta(
        actual, np.asarray(stage["target_degrees"], dtype=np.float64)
    )
    receipt = {
        "schema_version": WRIST_VIEW_EXECUTION_SCHEMA,
        "status": (
            "completed_wrist_view_reposition_stage"
            if error is None
            else "stopped_safely"
        ),
        "packet_sha256": _sha256(packet_path),
        "review_sha256": _sha256(review_path.resolve()),
        "stage_index": stage_index,
        "action_sha256": stage["action_sha256"],
        "completed_samples": completed,
        "joint_samples_path": str(samples_path),
        "joint_samples_sha256": _sha256(samples_path),
        "fresh_preflight_anchor_degrees": current.tolist(),
        "expected_anchor_degrees": expected_anchor.tolist(),
        "target_degrees": stage["target_degrees"],
        "final_actual_degrees": actual.tolist(),
        "final_residual_degrees": residual.tolist(),
        "error": str(error) if error is not None else None,
        "physical_motion_commanded": completed > 0,
        "physical_follower_torque_enabled": False,
        "physical_authority": False,
        "camera_opened": False,
        "inspect_wrist_camera_before_next_stage": stage_index < 3,
        "stop_before_further_robot_command": True,
        "wall_duration_seconds": max(0.0, clock_fn() - started),
    }
    _write_once(receipt_path, receipt)
    if error is not None:
        raise WristViewRepositionError(
            f"wrist-view stage stopped safely with torque off: {error}"
        ) from error
    return receipt
