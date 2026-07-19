"""Bounded B-G physical source-fit for a separate simulator joint adapter.

The optimizer uses task-labeled square centers and gripper phase events from
physical teleoperation *source* recordings.  It is deliberately not a camera,
contact, dynamics, or sim-to-real calibration procedure.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import mujoco
import numpy as np
from scipy.optimize import least_squares

from .contact_prior import (
    load_simulator_variant,
    read_contact_prior_snapshot,
)
from .grasp import _pinch_offset, _pinch_point
from .paths import REPO_ROOT
from .pawn_bg_demo_sim import (
    BASELINE_JOINT_ADAPTER,
    JointAdapter,
    _catalog_episodes,
    _load_source,
    _run_episode,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_reward import load_reward_contract, sha256_file
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
)


CONTRACT_PATH = REPO_ROOT / "configs/optimization/pawn_bg_source_fit_v1.json"
EXPECTED_CONTRACT_SHA256 = (
    "9144e42316dc007f8fcd381c6b7c054cbfe12e8c7b639d2a06f1f91070172910"
)
SCHEMA_VERSION = "sim2claw.pawn_bg_source_fit_receipt.v1"

TOP_LEVEL_KEYS = {
    "schema_version", "optimization_id", "frozen_at", "proof_class", "purpose",
    "bindings", "evidence_policy", "event_extraction", "parameter_space",
    "search", "selection", "authority",
}
BINDING_KEYS = {
    "reward_contract", "physical_catalog", "source_split", "baseline_adapter",
    "owner_visual_review", "wrist_cross_view",
}
EVIDENCE_KEYS = {
    "episode_selector", "expected_episode_count", "expected_distinct_skill_count",
    "expected_qualitative_marker_count",
    "require_catalog_hashes_for_samples_receipt_and_overhead_video",
    "held_out_episode_assets_may_be_read", "footage_is_metric_camera_calibration",
    "task_labels_are_measured_object_trajectories",
}
EVENT_KEYS = {
    "joint_signal", "gripper_joint_index", "first_open_search_fraction",
    "destination_open_search_start_fraction",
    "near_close_fraction_of_source_open_to_valley_range",
    "joint_average_window_radius_samples", "source_event", "destination_event",
    "target_xy", "target_z", "estimated_pawn_neck_height_m",
    "event_targets_are_physical_measurements",
}
PARAMETER_KEYS = {
    "body_joint_names", "sign_values", "scale_radians_per_degree",
    "zero_offset_unit", "zero_offset_bounds", "gripper_transform",
    "optimized_fields", "simulator_geometry_optimized",
    "contact_parameters_optimized", "mass_or_inertia_optimized",
    "actuator_or_joint_limits_optimized", "reward_or_evaluator_optimized",
}
SEARCH_KEYS = {
    "discrete_sign_hypothesis_count", "offset_solver", "offset_initialization",
    "maximum_function_evaluations", "function_tolerance", "parameter_tolerance",
    "gradient_tolerance", "kinematic_shortlist_count", "frozen_seed",
}
SELECTION_KEYS = {
    "shortlist_full_physics_variant", "lexicographic_metrics",
    "acceptance_rule",
    "selected_adapter_final_contact_variants", "reward_thresholds_changed",
    "simulated_seed_changed",
}
AUTHORITY_KEYS = {
    "training_performed", "learned_b_g_act_checkpoint_evaluated",
    "source_demonstrations_are_act_policy_weights", "physical_calibration_claimed",
    "sim_to_real_error_measured", "held_out_validation_performed",
    "promotion_allowed", "claim_boundary",
}


class SourceFitError(ValueError):
    """Raised when source-fit evidence or its frozen contract drifts."""


def _exact_keys(value: Any, expected: set[str], context: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise SourceFitError(f"{context} must be an object")
    actual = set(value)
    if actual != expected:
        raise SourceFitError(
            f"{context} keys drifted; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )
    return value


def _exact(value: Any, expected: Any, context: str) -> None:
    if type(value) is not type(expected) or value != expected:
        raise SourceFitError(f"{context} drifted from the frozen value")


def _finite_number(value: Any, context: str, *, minimum: float = -math.inf) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise SourceFitError(f"{context} must be a finite number, not bool or string")
    number = float(value)
    if number < minimum:
        raise SourceFitError(f"{context} is below its minimum")
    return number


def _binding(
    bindings: dict[str, Any], name: str, expected_keys: set[str]
) -> dict[str, Any]:
    return _exact_keys(bindings[name], expected_keys, f"bindings.{name}")


def validate_source_fit_contract(contract: Any) -> dict[str, Any]:
    payload = _exact_keys(contract, TOP_LEVEL_KEYS, "source-fit contract")
    _exact(payload["schema_version"], "sim2claw.pawn_bg_source_fit_contract.v1", "schema")
    _exact(payload["optimization_id"], "pawn_bg_joint_adapter_source_fit_v1", "optimization id")
    _exact(payload["proof_class"], "physical_teleoperation_source_fit_diagnostic_not_calibration", "proof class")
    if type(payload["frozen_at"]) is not str or type(payload["purpose"]) is not str:
        raise SourceFitError("frozen_at and purpose must be strings")

    bindings = _exact_keys(payload["bindings"], BINDING_KEYS, "bindings")
    reward = _binding(bindings, "reward_contract", {"path", "sha256"})
    catalog = _binding(bindings, "physical_catalog", {"path", "sha256"})
    split = _binding(bindings, "source_split", {"path", "sha256", "allowed_partition"})
    baseline = _binding(
        bindings, "baseline_adapter", {"path", "sha256", "joint_transform_sha256"}
    )
    visual = _binding(
        bindings,
        "owner_visual_review",
        {
            "config_path", "config_sha256", "generated_manifest_path",
            "generated_manifest_sha256", "use", "metric_pose_admission",
        },
    )
    wrist = _binding(
        bindings,
        "wrist_cross_view",
        {
            "release_manifest_path", "release_manifest_sha256", "source_receipt_path",
            "source_receipt_sha256", "video_path", "video_sha256",
            "source_recording_id", "camera_role", "held_out_membership", "use",
            "quantitative_object_or_endpoint_weight",
        },
    )
    for name, binding in (
        ("reward", reward), ("catalog", catalog), ("split", split),
        ("baseline", baseline), ("visual", visual), ("wrist", wrist),
    ):
        for key, value in binding.items():
            if key in {"metric_pose_admission", "held_out_membership"}:
                continue
            if key == "quantitative_object_or_endpoint_weight":
                _finite_number(value, f"{name}.{key}", minimum=0.0)
            elif type(value) is not str or not value:
                raise SourceFitError(f"{name}.{key} must be a non-empty string")
    _exact(split["allowed_partition"], "train", "allowed source partition")
    _exact(visual["metric_pose_admission"], False, "metric pose admission")
    _exact(wrist["held_out_membership"], False, "wrist held-out membership")
    _exact(
        wrist["quantitative_object_or_endpoint_weight"],
        0.0,
        "wrist quantitative weight",
    )

    evidence = _exact_keys(payload["evidence_policy"], EVIDENCE_KEYS, "evidence policy")
    _exact(evidence["expected_episode_count"], 11, "training episode count")
    _exact(evidence["expected_distinct_skill_count"], 10, "training skill count")
    _exact(evidence["expected_qualitative_marker_count"], 22, "marker count")
    for key, expected in (
        ("require_catalog_hashes_for_samples_receipt_and_overhead_video", True),
        ("held_out_episode_assets_may_be_read", False),
        ("footage_is_metric_camera_calibration", False),
        ("task_labels_are_measured_object_trajectories", False),
    ):
        _exact(evidence[key], expected, f"evidence policy {key}")

    events = _exact_keys(payload["event_extraction"], EVENT_KEYS, "event extraction")
    _exact(events["joint_signal"], "follower_actual_position_degrees", "joint signal")
    _exact(events["gripper_joint_index"], 5, "gripper index")
    _exact(events["joint_average_window_radius_samples"], 2, "event average radius")
    _exact(events["event_targets_are_physical_measurements"], False, "event measurement claim")
    first_fraction = _finite_number(events["first_open_search_fraction"], "open fraction", minimum=0.0)
    destination_fraction = _finite_number(
        events["destination_open_search_start_fraction"],
        "destination search fraction",
        minimum=0.0,
    )
    close_fraction = _finite_number(
        events["near_close_fraction_of_source_open_to_valley_range"],
        "near-close fraction",
        minimum=0.0,
    )
    if not 0.0 < first_fraction < 1.0 or not 0.0 < destination_fraction < 1.0:
        raise SourceFitError("phase fractions must be strictly between zero and one")
    if not 0.0 < close_fraction < 1.0:
        raise SourceFitError("near-close fraction must be strictly between zero and one")
    if first_fraction > destination_fraction:
        raise SourceFitError("source search must end before destination search begins")
    _exact(events["estimated_pawn_neck_height_m"], 0.038, "pawn neck height")

    parameters = _exact_keys(payload["parameter_space"], PARAMETER_KEYS, "parameter space")
    _exact(parameters["body_joint_names"], list(ROBOT_JOINTS[:5]), "body joint names")
    _exact(parameters["sign_values"], [-1, 1], "sign values")
    _exact(parameters["scale_radians_per_degree"], math.pi / 180.0, "joint scale")
    for key in (
        "simulator_geometry_optimized", "contact_parameters_optimized",
        "mass_or_inertia_optimized", "actuator_or_joint_limits_optimized",
        "reward_or_evaluator_optimized",
    ):
        _exact(parameters[key], False, f"parameter authority {key}")

    search = _exact_keys(payload["search"], SEARCH_KEYS, "search")
    _exact(search["discrete_sign_hypothesis_count"], 32, "sign hypothesis count")
    _exact(search["offset_solver"], "scipy.optimize.least_squares", "offset solver")
    _exact(search["kinematic_shortlist_count"], 3, "shortlist count")
    _exact(search["frozen_seed"], 190719, "source-fit seed")
    if type(search["maximum_function_evaluations"]) is not int or search["maximum_function_evaluations"] <= 0:
        raise SourceFitError("maximum function evaluations must be a positive integer")
    for key in ("function_tolerance", "parameter_tolerance", "gradient_tolerance"):
        if _finite_number(search[key], key, minimum=0.0) <= 0.0:
            raise SourceFitError(f"{key} must be positive")

    selection = _exact_keys(payload["selection"], SELECTION_KEYS, "selection")
    _exact(selection["shortlist_full_physics_variant"], "nominal_uncalibrated", "shortlist variant")
    _exact(
        selection["selected_adapter_final_contact_variants"],
        [
            "nominal_uncalibrated", "rubber_tip_low",
            "rubber_tip_nominal_prior", "rubber_tip_high",
        ],
        "final contact variants",
    )
    _exact(selection["reward_thresholds_changed"], False, "reward threshold mutation")
    _exact(selection["simulated_seed_changed"], False, "simulated seed mutation")
    if type(selection["lexicographic_metrics"]) is not list or len(selection["lexicographic_metrics"]) != 5:
        raise SourceFitError("selection metrics must contain exactly five entries")
    _exact(
        selection["acceptance_rule"],
        "candidate_must_be_no_clipping_and_strictly_beat_the_provisional_baseline_on_the_frozen_lexicographic_consequence_metric_else_no_adapter_is_accepted",
        "candidate acceptance rule",
    )

    authority = _exact_keys(payload["authority"], AUTHORITY_KEYS, "authority")
    for key in AUTHORITY_KEYS - {"claim_boundary"}:
        _exact(authority[key], False, f"authority {key}")
    if type(authority["claim_boundary"]) is not str or not authority["claim_boundary"]:
        raise SourceFitError("claim boundary must be a non-empty string")
    return payload


def load_source_fit_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if path.resolve() == CONTRACT_PATH.resolve() and digest != EXPECTED_CONTRACT_SHA256:
        raise SourceFitError(
            f"source-fit contract digest rejected: expected {EXPECTED_CONTRACT_SHA256}, got {digest}"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SourceFitError("source-fit contract is not valid JSON") from error
    return validate_source_fit_contract(payload)


@dataclass(frozen=True)
class PhaseEvent:
    recording_id: str
    skill_id: str
    phase: str
    sample_index: int
    average_window_start: int
    average_window_end: int
    physical_body_joint_degrees: tuple[float, float, float, float, float]
    target_xyz_m: tuple[float, float, float]
    gripper_value_at_event: float


def extract_phase_indices(
    samples: list[dict[str, Any]], contract: dict[str, Any]
) -> tuple[int, int, int]:
    events = contract["event_extraction"]
    if len(samples) < 10:
        raise SourceFitError("phase extraction requires at least ten samples")
    try:
        gripper = np.asarray(
            [row[events["joint_signal"]][events["gripper_joint_index"]] for row in samples],
            dtype=np.float64,
        )
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise SourceFitError("phase extraction requires finite six-joint actual rows") from error
    if gripper.shape != (len(samples),) or not np.isfinite(gripper).all():
        raise SourceFitError("phase extraction requires a finite gripper signal")
    amplitude = float(np.max(gripper) - np.min(gripper))
    if amplitude <= 1.0:
        raise SourceFitError("gripper signal has no usable open-close amplitude")
    search_end = max(2, int(len(samples) * events["first_open_search_fraction"]))
    destination_start = max(
        search_end,
        int(len(samples) * events["destination_open_search_start_fraction"]),
    )
    if destination_start >= len(samples) - 1:
        raise SourceFitError("destination-release search window is empty")
    open_index = int(np.argmax(gripper[:search_end]))
    destination_index = destination_start + int(np.argmax(gripper[destination_start:]))
    if destination_index <= open_index + 1:
        raise SourceFitError("source and destination opening peaks are not ordered")
    valley_index = open_index + 1 + int(
        np.argmin(gripper[open_index + 1 : destination_index])
    )
    if valley_index >= destination_index:
        raise SourceFitError("gripper has no near-close valley between opening peaks")
    near_close_threshold = float(gripper[valley_index]) + events[
        "near_close_fraction_of_source_open_to_valley_range"
    ] * float(gripper[open_index] - gripper[valley_index])
    crossings = np.flatnonzero(
        gripper[open_index + 1 : valley_index + 1] <= near_close_threshold
    )
    if len(crossings) == 0:
        raise SourceFitError("gripper never reaches the predeclared near-close band")
    source_index = open_index + 1 + int(crossings[0])
    return open_index, source_index, destination_index


def _average_body_joints(
    samples: list[dict[str, Any]], index: int, contract: dict[str, Any]
) -> tuple[tuple[float, float, float, float, float], int, int]:
    radius = contract["event_extraction"]["joint_average_window_radius_samples"]
    start = max(0, index - radius)
    end = min(len(samples), index + radius + 1)
    signal = contract["event_extraction"]["joint_signal"]
    values = np.asarray([row[signal][:5] for row in samples[start:end]], dtype=np.float64)
    if values.shape != (end - start, 5) or not np.isfinite(values).all():
        raise SourceFitError("event window contains invalid body joint values")
    return tuple(float(value) for value in np.mean(values, axis=0)), start, end - 1


def _make_phase_events(
    episode: dict[str, Any], source: str, destination: str,
    samples: list[dict[str, Any]], contract: dict[str, Any],
    board_center: tuple[float, float],
) -> list[PhaseEvent]:
    _, source_index, destination_index = extract_phase_indices(samples, contract)
    gripper_index = contract["event_extraction"]["gripper_joint_index"]
    signal = contract["event_extraction"]["joint_signal"]
    events: list[PhaseEvent] = []
    for phase, index, square in (
        ("source_near_close", source_index, source),
        ("destination_reopen", destination_index, destination),
    ):
        joints, start, end = _average_body_joints(samples, index, contract)
        target = np.asarray(
            board_square_center(square, board_center_in_table_frame_xy_m=board_center),
            dtype=np.float64,
        )
        target[2] += contract["event_extraction"]["estimated_pawn_neck_height_m"]
        events.append(PhaseEvent(
            recording_id=episode["recording_id"],
            skill_id=f"pawn_{source}_to_{destination}",
            phase=phase,
            sample_index=index,
            average_window_start=start,
            average_window_end=end,
            physical_body_joint_degrees=joints,
            target_xyz_m=tuple(float(value) for value in target),
            gripper_value_at_event=float(samples[index][signal][gripper_index]),
        ))
    return events


def _require_hash(path: Path, expected: str, context: str) -> None:
    if not path.is_file():
        raise SourceFitError(f"{context} is missing: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise SourceFitError(f"{context} hash rejected: expected {expected}, got {actual}")


def _load_json_bound(path: Path, expected: str, context: str) -> dict[str, Any]:
    _require_hash(path, expected, context)
    try:
        value = json.loads(path.read_bytes())
    except json.JSONDecodeError as error:
        raise SourceFitError(f"{context} is invalid JSON") from error
    if type(value) is not dict:
        raise SourceFitError(f"{context} must contain an object")
    return value


def _verify_wrist_evidence(
    contract: dict[str, Any], source_repository_root: Path
) -> dict[str, Any]:
    binding = contract["bindings"]["wrist_cross_view"]
    release_path = source_repository_root / binding["release_manifest_path"]
    receipt_path = source_repository_root / binding["source_receipt_path"]
    video_path = source_repository_root / binding["video_path"]
    release = _load_json_bound(
        release_path, binding["release_manifest_sha256"], "wrist release manifest"
    )
    receipt = _load_json_bound(
        receipt_path, binding["source_receipt_sha256"], "wrist source receipt"
    )
    _require_hash(video_path, binding["video_sha256"], "wrist D405 video")
    if receipt.get("recording_id") != binding["source_recording_id"]:
        raise SourceFitError("wrist source recording identity drifted")
    if receipt.get("held_out_membership") is not False:
        raise SourceFitError("wrist evidence must be explicitly non-held-out")
    assets = {asset.get("name"): asset for asset in release.get("assets", [])}
    video_asset = assets.get(video_path.name)
    if (
        type(video_asset) is not dict
        or video_asset.get("sha256") != binding["video_sha256"]
        or video_asset.get("camera_role") != binding["camera_role"]
    ):
        raise SourceFitError("wrist asset identity drifted in release manifest")
    return {
        "release_manifest_path": str(release_path),
        "release_manifest_sha256": binding["release_manifest_sha256"],
        "source_receipt_sha256": binding["source_receipt_sha256"],
        "video_path": str(video_path),
        "video_sha256": binding["video_sha256"],
        "source_recording_id": binding["source_recording_id"],
        "camera_role": binding["camera_role"],
        "held_out_membership": False,
        "use": binding["use"],
        "quantitative_object_or_endpoint_weight": 0.0,
        "view_limitation": video_asset.get("view_limitation"),
    }


def _selected_training_episodes(
    contract: dict[str, Any], source_repository_root: Path
) -> tuple[list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]], dict[str, Any]]:
    bindings = contract["bindings"]
    catalog_path = REPO_ROOT / bindings["physical_catalog"]["path"]
    external_catalog_path = source_repository_root / bindings["physical_catalog"]["path"]
    _require_hash(catalog_path, bindings["physical_catalog"]["sha256"], "local physical catalog")
    _require_hash(external_catalog_path, bindings["physical_catalog"]["sha256"], "source physical catalog")
    catalog = json.loads(catalog_path.read_bytes())
    product_episodes = _catalog_episodes(catalog)

    split_binding = bindings["source_split"]
    split = _load_json_bound(
        REPO_ROOT / split_binding["path"], split_binding["sha256"], "source split"
    )
    assignments = {row["episode_id"]: row for row in split.get("episodes", [])}
    selected_meta = [
        row for row in product_episodes
        if assignments.get(row[0]["recording_id"], {}).get("split") == "train"
    ]
    expected_count = contract["evidence_policy"]["expected_episode_count"]
    if len(selected_meta) != expected_count:
        raise SourceFitError(
            f"training/product intersection drifted: expected {expected_count}, got {len(selected_meta)}"
        )
    skill_ids = {f"pawn_{source}_to_{destination}" for _, source, destination in selected_meta}
    if len(skill_ids) != contract["evidence_policy"]["expected_distinct_skill_count"]:
        raise SourceFitError("training/product skill coverage drifted")

    visual_binding = bindings["owner_visual_review"]
    _require_hash(
        REPO_ROOT / visual_binding["config_path"],
        visual_binding["config_sha256"],
        "owner visual review config",
    )
    visual_manifest = _load_json_bound(
        source_repository_root / visual_binding["generated_manifest_path"],
        visual_binding["generated_manifest_sha256"],
        "owner visual review manifest",
    )
    selected_ids = {episode["recording_id"] for episode, _, _ in selected_meta}
    markers = [
        marker for marker in visual_manifest.get("accepted_marker_manifest", [])
        if marker.get("source_recording_id") in selected_ids
    ]
    if len(markers) != contract["evidence_policy"]["expected_qualitative_marker_count"]:
        raise SourceFitError("owner-reviewed qualitative marker count drifted")
    marker_phases = {
        recording_id: {marker.get("phase") for marker in markers if marker.get("source_recording_id") == recording_id}
        for recording_id in selected_ids
    }
    if any(phases != {"initial", "final"} for phases in marker_phases.values()):
        raise SourceFitError("each selected episode requires owner-reviewed initial/final markers")

    selected: list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]] = []
    overhead_assets: list[dict[str, Any]] = []
    for episode, source, destination in selected_meta:
        samples = _load_source(episode, source_repository_root)
        overhead_path = source_repository_root / episode["assets"]["overhead_video"]
        _require_hash(overhead_path, episode["overhead_video_sha256"], "training overhead video")
        selected.append((episode, source, destination, samples))
        overhead_assets.append({
            "recording_id": episode["recording_id"],
            "folder_label": episode["folder_label"],
            "path": str(overhead_path),
            "sha256": episode["overhead_video_sha256"],
            "use": "owner_reviewed_qualitative_initial_final_and_phase_evidence",
            "quantitative_metric_weight": 0.0,
        })
    excluded = [
        {
            "recording_id": episode["recording_id"],
            "folder_label": episode["folder_label"],
            "split": assignments.get(episode["recording_id"], {}).get("split"),
            "assets_read": False,
        }
        for episode, _, _ in product_episodes if episode["recording_id"] not in selected_ids
    ]
    return selected, {
        "catalog_path": str(catalog_path),
        "catalog_sha256": bindings["physical_catalog"]["sha256"],
        "split_path": str(REPO_ROOT / split_binding["path"]),
        "split_sha256": split_binding["sha256"],
        "allowed_partition": "train",
        "selected_recording_ids": sorted(selected_ids),
        "selected_episode_count": len(selected),
        "selected_distinct_skill_count": len(skill_ids),
        "owner_visual_manifest_sha256": visual_binding["generated_manifest_sha256"],
        "owner_reviewed_marker_count": len(markers),
        "overhead_assets": overhead_assets,
        "excluded_product_episodes": excluded,
        "held_out_episode_assets_read": False,
    }


def _model_bindings(contract: dict[str, Any]) -> dict[str, Any]:
    reward = load_reward_contract()
    board_center = registered_board_center(reward["scene_binding"]["scene_id"])
    model = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=board_center,
    ).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}")
        for joint in ROBOT_JOINTS
    ]
    actuator_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}")
        for joint in ROBOT_JOINTS
    ]
    if min(joint_ids + actuator_ids) < 0:
        raise SourceFitError("current simulator is missing a required left-arm binding")
    qpos_addresses = [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids]
    bounds = np.asarray(model.actuator_ctrlrange[actuator_ids], dtype=np.float64)
    return {
        "reward": reward,
        "board_center": board_center,
        "model": model,
        "data": data,
        "qpos_addresses": qpos_addresses,
        "actuator_bounds": bounds,
        "pinch_offset_local": _pinch_offset(model, data, "left"),
    }


def _event_receipt(
    event: PhaseEvent, predicted: np.ndarray | None = None
) -> dict[str, Any]:
    result = {
        "recording_id": event.recording_id,
        "skill_id": event.skill_id,
        "phase": event.phase,
        "sample_index": event.sample_index,
        "average_window_start": event.average_window_start,
        "average_window_end": event.average_window_end,
        "physical_body_joint_degrees": list(event.physical_body_joint_degrees),
        "target_xyz_m": list(event.target_xyz_m),
        "gripper_value_at_event": event.gripper_value_at_event,
    }
    if predicted is not None:
        residual = predicted - np.asarray(event.target_xyz_m)
        result.update({
            "simulated_pinch_xyz_m": predicted.tolist(),
            "residual_xyz_m": residual.tolist(),
            "distance_m": float(np.linalg.norm(residual)),
        })
    return result


def _predict_events(
    adapter: JointAdapter, events: Iterable[PhaseEvent], model_binding: dict[str, Any]
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    model = model_binding["model"]
    data = model_binding["data"]
    qpos_addresses = model_binding["qpos_addresses"]
    predictions: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []
    for event in events:
        physical = np.asarray([*event.physical_body_joint_degrees, 0.0])
        converted = physical_values_to_sim_with_adapter(
            physical, model_binding["actuator_bounds"][-1], adapter
        )
        data.qpos[qpos_addresses[:5]] = converted[:5]
        mujoco.mj_forward(model, data)
        predicted = _pinch_point(
            model, data, "left", model_binding["pinch_offset_local"]
        ).copy()
        predictions.append(predicted)
        rows.append(_event_receipt(event, predicted))
    return np.asarray(predictions), rows


def _kinematic_metrics(
    adapter: JointAdapter, events: list[PhaseEvent], model_binding: dict[str, Any]
) -> dict[str, Any]:
    predictions, rows = _predict_events(adapter, events, model_binding)
    targets = np.asarray([event.target_xyz_m for event in events])
    vectors = predictions - targets
    distances = np.linalg.norm(vectors, axis=1)
    return {
        "event_count": len(events),
        "event_rms_distance_m": float(np.sqrt(np.mean(np.square(distances)))),
        "event_mean_distance_m": float(np.mean(distances)),
        "event_maximum_distance_m": float(np.max(distances)),
        "axis_rmse_m": np.sqrt(np.mean(np.square(vectors), axis=0)).tolist(),
        "events": rows,
    }


def _all_body_values(
    selected: list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]]
) -> np.ndarray:
    values: list[list[float]] = []
    for _, _, _, samples in selected:
        for sample in samples:
            values.append(sample["follower_command_degrees"][:5])
            values.append(sample["follower_actual_position_degrees"][:5])
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 5 or not np.isfinite(result).all():
        raise SourceFitError("training commands and actual positions must be finite five-joint rows")
    return result


def _offset_bounds(
    body_values_degrees: np.ndarray,
    signs: tuple[int, int, int, int, int],
    actuator_bounds: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    signed = np.deg2rad(body_values_degrees) * np.asarray(signs)
    lower = actuator_bounds[:5, 0] - np.min(signed, axis=0)
    upper = actuator_bounds[:5, 1] - np.max(signed, axis=0)
    if np.any(lower >= upper):
        raise SourceFitError("sign hypothesis has no exact no-clipping zero-offset interval")
    return lower, upper


def _adapter_limit_report(
    adapter: JointAdapter, body_values_degrees: np.ndarray, actuator_bounds: np.ndarray
) -> dict[str, Any]:
    converted = (
        np.deg2rad(body_values_degrees) * np.asarray(adapter.body_joint_signs)
        + np.asarray(adapter.body_joint_zero_offsets_rad)
    )
    below = np.maximum(actuator_bounds[:5, 0] - converted, 0.0)
    above = np.maximum(converted - actuator_bounds[:5, 1], 0.0)
    exceedance = np.maximum(below, above)
    return {
        "checked_joint_value_count": int(converted.size),
        "violating_joint_value_count": int(np.count_nonzero(exceedance > 1e-12)),
        "maximum_exceedance_rad": float(np.max(exceedance, initial=0.0)),
        "all_allowed_training_body_values_within_unchanged_limits": bool(
            np.count_nonzero(exceedance > 1e-12) == 0
        ),
        "minimum_converted_rad": np.min(converted, axis=0).tolist(),
        "maximum_converted_rad": np.max(converted, axis=0).tolist(),
        "actuator_lower_rad": actuator_bounds[:5, 0].tolist(),
        "actuator_upper_rad": actuator_bounds[:5, 1].tolist(),
    }


def _fit_candidates(
    selected: list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]],
    events: list[PhaseEvent], contract: dict[str, Any], model_binding: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body_values = _all_body_values(selected)
    targets = np.asarray([event.target_xyz_m for event in events])
    search = contract["search"]
    candidates: list[dict[str, Any]] = []
    for signs in itertools.product((-1, 1), repeat=5):
        lower, upper = _offset_bounds(
            body_values, signs, model_binding["actuator_bounds"]
        )

        def residual(offsets: np.ndarray) -> np.ndarray:
            adapter = JointAdapter(
                adapter_id="optimization_candidate",
                body_joint_signs=signs,
                body_joint_zero_offsets_rad=tuple(float(value) for value in offsets),
                evidence_class="bounded_source_fit_candidate_not_calibrated",
            )
            predicted, _ = _predict_events(adapter, events, model_binding)
            return (predicted - targets).reshape(-1)

        fit = least_squares(
            residual,
            (lower + upper) / 2.0,
            bounds=(lower, upper),
            max_nfev=search["maximum_function_evaluations"],
            ftol=search["function_tolerance"],
            xtol=search["parameter_tolerance"],
            gtol=search["gradient_tolerance"],
        )
        adapter = JointAdapter(
            adapter_id="pawn_bg_joint_adapter_source_fit_v1_candidate",
            body_joint_signs=signs,
            body_joint_zero_offsets_rad=tuple(float(value) for value in fit.x),
            evidence_class="bounded_physical_source_fit_not_calibrated",
        )
        kinematic = _kinematic_metrics(adapter, events, model_binding)
        limit_report = _adapter_limit_report(
            adapter, body_values, model_binding["actuator_bounds"]
        )
        if not limit_report["all_allowed_training_body_values_within_unchanged_limits"]:
            raise SourceFitError("optimizer produced a clipping adapter despite exact bounds")
        candidates.append({
            "adapter": adapter,
            "kinematic": kinematic,
            "limit_report": limit_report,
            "offset_lower_bounds_rad": lower.tolist(),
            "offset_upper_bounds_rad": upper.tolist(),
            "solver": {
                "success": bool(fit.success),
                "status": int(fit.status),
                "function_evaluations": int(fit.nfev),
                "cost": float(fit.cost),
                "message": str(fit.message),
            },
        })
    candidates.sort(key=lambda row: (row["kinematic"]["event_rms_distance_m"], row["adapter"].sha256))
    baseline = {
        "adapter": BASELINE_JOINT_ADAPTER,
        "kinematic": _kinematic_metrics(BASELINE_JOINT_ADAPTER, events, model_binding),
        "limit_report": _adapter_limit_report(
            BASELINE_JOINT_ADAPTER, body_values, model_binding["actuator_bounds"]
        ),
    }
    return candidates, baseline


def _aggregate_physics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise SourceFitError("physics aggregation requires at least one episode")
    return {
        "episode_count": len(rows),
        "task_consequence_success_count": sum(
            bool(row["score"]["task_consequence_success"]) for row in rows
        ),
        "selected_piece_contact_episode_count": sum(
            bool(row["score"]["gate_results"]["selected_piece_contact_observed"])
            for row in rows
        ),
        "piece_lift_episode_count": sum(
            bool(row["score"]["gate_results"]["piece_lifted"]) for row in rows
        ),
        "release_episode_count": sum(
            bool(row["score"]["gate_results"]["released"]) for row in rows
        ),
        "mean_diagnostic_reward": float(np.mean([row["score"]["diagnostic_reward"] for row in rows])),
        "mean_final_center_distance_m": float(
            np.mean([row["score"]["final_center_distance_m"] for row in rows])
        ),
        "maximum_piece_rise_m": float(max(row["score"]["maximum_piece_rise_m"] for row in rows)),
        "recordings_with_clipped_commands": sum(row["command_rows_clipped"] > 0 for row in rows),
        "recordings_with_actual_rows_outside_limits": sum(
            row["actual_rows_outside_sim_limits"] > 0 for row in rows
        ),
        "finite_episode_count": sum(
            bool(row["score"]["gate_results"]["finite_state"]) for row in rows
        ),
    }


def _run_adapter_variant(
    adapter: JointAdapter, variant: Any,
    selected: list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]],
    reward_contract: dict[str, Any],
) -> dict[str, Any]:
    rows = [
        _run_episode(
            contract=reward_contract,
            episode=episode,
            source=source,
            destination=destination,
            samples=samples,
            variant=variant,
            joint_adapter=adapter,
        )
        for episode, source, destination, samples in selected
    ]
    return {"aggregate": _aggregate_physics(rows), "episodes": rows}


def _selection_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    aggregate = candidate["nominal_physics"]["aggregate"]
    return (
        -aggregate["task_consequence_success_count"],
        -aggregate["selected_piece_contact_episode_count"],
        -aggregate["mean_diagnostic_reward"],
        aggregate["mean_final_center_distance_m"],
        candidate["kinematic"]["event_rms_distance_m"],
        candidate["adapter"].sha256,
    )


def _candidate_beats_baseline(
    candidate: dict[str, Any], baseline: dict[str, Any], limit_report: dict[str, Any]
) -> bool:
    return bool(
        limit_report["all_allowed_training_body_values_within_unchanged_limits"]
        and _selection_key(candidate)[:-1] < _selection_key(baseline)[:-1]
    )


def _candidate_receipt(candidate: dict[str, Any], *, include_events: bool) -> dict[str, Any]:
    kinematic = dict(candidate["kinematic"])
    if not include_events:
        kinematic.pop("events", None)
    result = {
        "adapter": candidate["adapter"].receipt(),
        "kinematic": kinematic,
        "limit_report": candidate["limit_report"],
    }
    for key in (
        "offset_lower_bounds_rad", "offset_upper_bounds_rad", "solver",
        "nominal_physics", "selection_rank",
    ):
        if key in candidate:
            result[key] = candidate[key]
    return result


def optimize_pawn_bg_source_fit(
    *, source_repository_root: Path, output_path: Path
) -> dict[str, Any]:
    contract = load_source_fit_contract()
    source_repository_root = source_repository_root.resolve()
    if not source_repository_root.is_dir():
        raise SourceFitError("physical source repository root is missing")

    bindings = contract["bindings"]
    for name in ("reward_contract", "source_split", "baseline_adapter"):
        binding = bindings[name]
        _require_hash(REPO_ROOT / binding["path"], binding["sha256"], name)
    baseline_config = json.loads((REPO_ROOT / bindings["baseline_adapter"]["path"]).read_bytes())
    if (
        baseline_config.get("physical_adapter", {}).get("joint_transform_sha256")
        != bindings["baseline_adapter"]["joint_transform_sha256"]
    ):
        raise SourceFitError("baseline joint transform identity drifted")

    selected, evidence = _selected_training_episodes(contract, source_repository_root)
    wrist_evidence = _verify_wrist_evidence(contract, source_repository_root)
    model_binding = _model_bindings(contract)
    board_center = model_binding["board_center"]
    events = [
        event
        for episode, source, destination, samples in selected
        for event in _make_phase_events(
            episode, source, destination, samples, contract, board_center
        )
    ]
    if len(events) != 2 * contract["evidence_policy"]["expected_episode_count"]:
        raise SourceFitError("phase event count drifted")

    candidates, baseline = _fit_candidates(selected, events, contract, model_binding)
    prior_snapshot = read_contact_prior_snapshot()
    nominal = load_simulator_variant(
        contract["selection"]["shortlist_full_physics_variant"],
        contract_snapshot=prior_snapshot,
    )
    baseline["nominal_physics"] = _run_adapter_variant(
        baseline["adapter"], nominal, selected, model_binding["reward"]
    )

    shortlist_count = contract["search"]["kinematic_shortlist_count"]
    shortlist = candidates[:shortlist_count]
    for candidate in shortlist:
        candidate["nominal_physics"] = _run_adapter_variant(
            candidate["adapter"], nominal, selected, model_binding["reward"]
        )
    shortlist.sort(key=_selection_key)
    for rank, candidate in enumerate(shortlist, start=1):
        candidate["selection_rank"] = rank
    selected_candidate = shortlist[0]
    selected_adapter = JointAdapter(
        adapter_id="pawn_bg_joint_adapter_source_fit_v1_selected",
        body_joint_signs=selected_candidate["adapter"].body_joint_signs,
        body_joint_zero_offsets_rad=selected_candidate["adapter"].body_joint_zero_offsets_rad,
        evidence_class="bounded_physical_source_fit_selected_not_calibrated",
    )
    selected_kinematic = _kinematic_metrics(selected_adapter, events, model_binding)
    selected_limit_report = _adapter_limit_report(
        selected_adapter, _all_body_values(selected), model_binding["actuator_bounds"]
    )

    final_variants: dict[str, Any] = {}
    for variant_id in contract["selection"]["selected_adapter_final_contact_variants"]:
        variant = load_simulator_variant(variant_id, contract_snapshot=prior_snapshot)
        if variant_id == nominal.variant_id:
            # The adapter ID is receipt metadata only; the numerical mapping is
            # identical to the selected candidate already run above.
            variant_result = _run_adapter_variant(
                selected_adapter, variant, selected, model_binding["reward"]
            )
        else:
            variant_result = _run_adapter_variant(
                selected_adapter, variant, selected, model_binding["reward"]
            )
        final_variants[variant_id] = variant_result

    baseline_rms = baseline["kinematic"]["event_rms_distance_m"]
    selected_rms = selected_kinematic["event_rms_distance_m"]
    baseline_metric_key = _selection_key(baseline)[:-1]
    candidate_metric_key = _selection_key(selected_candidate)[:-1]
    candidate_accepted = _candidate_beats_baseline(
        selected_candidate, baseline, selected_limit_report
    )
    optimization_status = (
        "accepted_bounded_source_fit_adapter_not_physical_calibration"
        if candidate_accepted
        else "terminal_negative_no_source_fit_adapter_accepted"
    )
    core = {
        "contract_sha256": EXPECTED_CONTRACT_SHA256,
        "evidence": evidence,
        "wrist_evidence": wrist_evidence,
        "events": [_event_receipt(event) for event in events],
        "baseline": _candidate_receipt(baseline, include_events=True),
        "kinematic_hypothesis_count": len(candidates),
        "kinematic_shortlist": [
            _candidate_receipt(candidate, include_events=False) for candidate in shortlist
        ],
        "best_candidate_adapter": selected_adapter.receipt(),
        "best_candidate_kinematic": selected_kinematic,
        "best_candidate_limit_report": selected_limit_report,
        "candidate_accepted": candidate_accepted,
        "accepted_adapter": selected_adapter.receipt() if candidate_accepted else None,
        "optimization_status": optimization_status,
        "acceptance_comparison": {
            "rule": contract["selection"]["acceptance_rule"],
            "baseline_lexicographic_key": list(baseline_metric_key),
            "candidate_lexicographic_key": list(candidate_metric_key),
            "candidate_strictly_beats_baseline": candidate_metric_key < baseline_metric_key,
        },
        "kinematic_event_rms_improvement_m": baseline_rms - selected_rms,
        "kinematic_event_rms_relative_improvement": (
            (baseline_rms - selected_rms) / baseline_rms if baseline_rms > 0.0 else 0.0
        ),
        "final_contact_variants": final_variants,
        "final_contact_variants_use_best_candidate_even_if_rejected": True,
    }
    deterministic_bytes = json.dumps(
        core, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    report = {
        "schema_version": SCHEMA_VERSION,
        "optimization_id": contract["optimization_id"],
        "created_at": datetime.now(UTC).isoformat(),
        "source_fit_contract_path": str(CONTRACT_PATH.relative_to(REPO_ROOT)),
        "source_fit_contract_sha256": EXPECTED_CONTRACT_SHA256,
        "reward_contract_sha256": bindings["reward_contract"]["sha256"],
        "contact_prior_sha256": prior_snapshot.sha256,
        "deterministic_core_sha256": hashlib.sha256(deterministic_bytes).hexdigest(),
        **core,
        "training_performed": False,
        "learned_b_g_act_checkpoint_evaluated": False,
        "source_demonstrations_are_human_owned": True,
        "physical_calibration_claimed": False,
        "sim_to_real_error_measured": False,
        "held_out_validation_performed": False,
        "promotion_allowed": False,
        "claim_boundary": contract["authority"]["claim_boundary"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)
    return report


__all__ = [
    "CONTRACT_PATH",
    "EXPECTED_CONTRACT_SHA256",
    "PhaseEvent",
    "SourceFitError",
    "extract_phase_indices",
    "load_source_fit_contract",
    "optimize_pawn_bg_source_fit",
    "validate_source_fit_contract",
]
