"""Fit one shared renderer-only shoulder-lift articulation pair without replay."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.spatial.transform import Rotation

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_scene_composition_residual_attribution import (
    _masked_tolerant_edge_f1,
)
from .observable_registration_board_anchored_workcell_se2_static_development_fit import (
    _prepare_full_mesh_stream,
    _region_masks,
)
from .observable_registration_development_initial_shared_3d_camera_fit import _metrics
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_expanded_development_global_monotone_response_fit import (
    apply_monotone_response,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    quaternion_matrix_wxyz,
    sha256_file,
)
from .observable_registration_native_rasterizer_byte_equivalence import (
    _compile_native,
    _native_rasterize,
)
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import (
    _independently_registered_trace,
)
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import (
    _episode_inventory,
)
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png
from .observable_registration_static_development_full_mesh_comparison import (
    _load_unique_asset_cache,
)


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_final_shared_shoulder_lift_articulation_calibration_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_shared_shoulder_lift_articulation_calibration_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_shared_shoulder_lift_articulation_calibration_v1"


def load_post_final_shared_shoulder_lift_articulation_calibration_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR104 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)):
        raise ValueError("OR104 split drifted")
    if split["validation_render_requires_development_gate"] is not True or split["validation_never_selects_or_refits"] is not True:
        raise ValueError("OR104 validation boundary drifted")
    sampling = contract["sampling"]
    if sampling["within_episode_quantiles"] != [0.25, 0.5, 0.75] or sampling["samples_per_episode"] != 3:
        raise ValueError("OR104 sample family drifted")
    joint = contract["joint_family"]
    if joint["name"] != "shoulder_lift" or joint["left"]["subtree_body_ids"] != list(range(31, 37)) or joint["right"]["subtree_body_ids"] != list(range(39, 45)):
        raise ValueError("OR104 shoulder-lift ancestry drifted")
    if joint["one_shared_pair_for_both_robots"] is not True or joint["per_episode_or_side_parameters"] is not False:
        raise ValueError("OR104 shared-parameter boundary drifted")
    family = contract["candidate_family"]
    if family["excursion_gain_candidates"] != [0.8, 0.9, 1.0, 1.1, 1.2] or family["offset_degree_candidates"] != [-10.0, -5.0, 0.0, 5.0, 10.0]:
        raise ValueError("OR104 candidate family drifted")
    if family["identity_pair"] != [1.0, 0.0] or family["selected_pair_frozen_before_validation"] is not True:
        raise ValueError("OR104 identity or freeze boundary drifted")
    if family["pixel_warp_composite_or_mask_edit"] is not False or family["action_state_dynamics_timing_or_contact_mutated"] is not False:
        raise ValueError("OR104 renderer-only boundary drifted")
    resources = contract["resource_boundary"]
    expected = {
        "development_state_trace_reads_allowed": 7,
        "validation_state_trace_reads_allowed_if_development_passes": 4,
        "already_open_development_physical_episode_decodes_allowed": 7,
        "already_open_validation_physical_episode_decodes_allowed_if_development_passes": 4,
        "development_physical_frames_compared_allowed": 21,
        "validation_physical_frames_compared_allowed_if_development_passes": 12,
        "candidate_pair_values_allowed": 25,
        "fits_allowed": 1,
        "exact_full_mesh_development_candidate_renders_allowed": 525,
        "exact_full_mesh_validation_selected_renders_allowed_if_development_passes": 12,
        "simulator_replays_allowed": 0,
        "action_or_state_mutations_allowed": 0,
        "hardware_actions_allowed": 0,
        "paid_compute_allowed": False,
    }
    if resources != expected or any(contract["authority"].values()):
        raise ValueError("OR104 resource or authority boundary drifted")
    if contract["claim_limits"]["same_video_semantic_match"] is not False or contract["claim_limits"]["untouched_cohort_remaining"] is not False:
        raise ValueError("OR104 claim boundary drifted")
    return contract


def _rotation_arrays(frame: dict[str, Any]) -> tuple[np.ndarray, list[np.ndarray]]:
    positions = np.asarray(frame["p"], dtype=np.float64).reshape((-1, 3))
    rotations = [
        quaternion_matrix_wxyz(value)
        for value in np.asarray(frame["q"], dtype=np.float64).reshape((-1, 4))
    ]
    return positions, rotations


def _matrix_to_quaternion_wxyz(matrix: np.ndarray) -> np.ndarray:
    x, y, z, w = Rotation.from_matrix(matrix).as_quat()
    value = np.asarray([w, x, y, z], dtype=np.float64)
    return value / np.linalg.norm(value)


def _principal_axes(
    development_traces: list[dict[str, Any]],
    sides: dict[str, dict[str, Any]],
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    axes: dict[str, np.ndarray] = {}
    diagnostics: dict[str, Any] = {}
    for side, spec in sides.items():
        parent_id = int(spec["parent_body_id"])
        joint_id = int(spec["joint_body_id"])
        vectors: list[np.ndarray] = []
        for trace in development_traces:
            _, initial_rotations = _rotation_arrays(trace["frames"][0])
            initial_relative = initial_rotations[parent_id].T @ initial_rotations[joint_id]
            for frame in trace["frames"]:
                _, rotations = _rotation_arrays(frame)
                relative = rotations[parent_id].T @ rotations[joint_id]
                vector = Rotation.from_matrix(initial_relative.T @ relative).as_rotvec()
                if float(np.linalg.norm(vector)) > 1e-8:
                    vectors.append(vector)
        if not vectors:
            raise ValueError(f"OR104 {side} shoulder-lift axis is unobservable")
        matrix = np.stack(vectors)
        eigenvalues, eigenvectors = np.linalg.eigh(matrix.T @ matrix)
        axis = eigenvectors[:, int(np.argmax(eigenvalues))]
        sign_index = int(np.argmax(np.abs(axis)))
        if axis[sign_index] < 0.0:
            axis = -axis
        axis = axis / np.linalg.norm(axis)
        projection = matrix @ axis
        residual = matrix - projection[:, None] * axis[None, :]
        axes[side] = axis
        diagnostics[side] = {
            "axis_parent_relative_coordinates": axis.tolist(),
            "rotation_vector_count": len(vectors),
            "principal_variance_fraction": float(eigenvalues[-1] / max(float(np.sum(eigenvalues)), 1e-12)),
            "median_absolute_projected_excursion_rad": float(np.median(np.abs(projection))),
            "median_orthogonal_residual_rad": float(np.median(np.linalg.norm(residual, axis=1))),
        }
    return axes, diagnostics


def _articulated_trace(
    trace: dict[str, Any],
    *,
    initial_frame: dict[str, Any],
    axes: dict[str, np.ndarray],
    sides: dict[str, dict[str, Any]],
    gain: float,
    offset_degrees: float,
) -> dict[str, Any]:
    """Rotate declared renderer subtrees; return identity bytes for the identity pair."""
    if len(trace["frames"]) != 1:
        raise ValueError("OR104 articulation expects exactly one trace frame")
    if float(gain) == 1.0 and float(offset_degrees) == 0.0:
        return {"body_names": list(trace["body_names"]), "frames": [dict(trace["frames"][0])]}
    state = trace["frames"][0]
    positions, rotations = _rotation_arrays(state)
    _, initial_rotations = _rotation_arrays(initial_frame)
    positions = positions.copy()
    rotations = [value.copy() for value in rotations]
    offset = math.radians(float(offset_degrees))
    for side, spec in sides.items():
        parent_id = int(spec["parent_body_id"])
        joint_id = int(spec["joint_body_id"])
        axis = np.asarray(axes[side], dtype=np.float64)
        initial_relative = initial_rotations[parent_id].T @ initial_rotations[joint_id]
        relative = rotations[parent_id].T @ rotations[joint_id]
        rotation_vector = Rotation.from_matrix(initial_relative.T @ relative).as_rotvec()
        signed_excursion = float(np.dot(rotation_vector, axis))
        correction_angle = (float(gain) - 1.0) * signed_excursion + offset
        local_correction = Rotation.from_rotvec(axis * correction_angle).as_matrix()
        corrected_relative = relative @ local_correction
        corrected_joint_world = rotations[parent_id] @ corrected_relative
        world_correction = corrected_joint_world @ rotations[joint_id].T
        center = positions[joint_id].copy()
        for body_id in [int(value) for value in spec["subtree_body_ids"]]:
            positions[body_id] = center + world_correction @ (positions[body_id] - center)
            rotations[body_id] = world_correction @ rotations[body_id]
    quaternions = np.stack([_matrix_to_quaternion_wxyz(value) for value in rotations])
    transformed = dict(state)
    transformed["p"] = positions.reshape(-1).tolist()
    transformed["q"] = quaternions.reshape(-1).tolist()
    return {"body_names": list(trace["body_names"]), "frames": [transformed]}


def _sample_rows(frame_rows: list[dict[str, Any]], positions: list[int], quantiles: list[float]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for position in positions:
        episode_rows = sorted(
            (row for row in frame_rows if int(row["split_position"]) == int(position)),
            key=lambda row: int(row["evaluation_index"]),
        )
        if not episode_rows:
            raise ValueError(f"OR104 missing OR95 rows for split position {position}")
        for quantile in quantiles:
            index = int(math.floor(float(quantile) * (len(episode_rows) - 1) + 0.5))
            selected.append(dict(episode_rows[index]))
    return selected


def _mean(rows: list[dict[str, Any]], path: tuple[str, ...]) -> float:
    values: list[float] = []
    for row in rows:
        value: Any = row
        for key in path:
            value = value[key]
        values.append(float(value))
    return float(np.mean(values))


def calibrate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR104 one-run receipt already exists")
    contract = load_post_final_shared_shoulder_lift_articulation_calibration_contract(contract_path)
    or103 = json.loads((REPO_ROOT / contract["sources"]["or103_closeout"]["path"]).read_text())
    if or103["status"] != "PASS_JOINT_ARTICULATION_FAMILY_SELECTED" or or103["result"]["selected_family"] != "shoulder_lift":
        raise ValueError("OR103 did not authorize shoulder-lift calibration")
    or95_receipt = json.loads((REPO_ROOT / contract["sources"]["or95_receipt"]["path"]).read_text())
    if or95_receipt["artifact_sha256"] != contract["sources"]["or95_receipt"]["artifact_sha256"]:
        raise ValueError("OR95 artifact identity drifted")
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    or95_row_by_key = {
        (int(row["split_position"]), int(row["evaluation_index"])): row for row in frame_rows
    }
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("OR104 scene revision mismatch")
    body_names = [row["name"] for row in scene["bodies"]]
    sides = {name: dict(spec) for name, spec in (("left", contract["joint_family"]["left"]), ("right", contract["joint_family"]["right"]))}
    body_by_id = {int(row["id"]): row for row in scene["bodies"]}
    for spec in sides.values():
        if int(body_by_id[int(spec["joint_body_id"])]["parent_id"]) != int(spec["parent_body_id"]):
            raise ValueError("OR104 scene shoulder-lift ancestry drifted")

    frozen = or95_contract["frozen_candidate"]
    camera = frozen["camera"]
    static = frozen["static_workcell_transform"]
    static_family = {
        "anchor_body_id": int(static["anchor_body_id"]),
        "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]],
    }
    static_vector = np.asarray(static["vector"], dtype=np.float64)
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"], dtype=np.float64)
    response = frozen["global_monotone_response"]
    renderer = contract["renderer"]
    edge = contract["metric"]["edge"]
    board_mask, outside_mask = _region_masks(
        np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=int(renderer["width_px"]),
        height=int(renderer["height_px"]),
        dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native(
        {"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}},
        output_directory,
    )

    trace_cache: dict[int, dict[str, Any]] = {}

    def load_trace(position: int) -> dict[str, Any]:
        if position not in trace_cache:
            episode = episode_by_position[position]
            binding = episode["state_trace"]
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError("OR104 state trace hash mismatch")
            trace = json.loads((REPO_ROOT / binding["path"]).read_text())
            if trace["body_names"] != body_names:
                raise ValueError("OR104 scene and trace body ordering drifted")
            trace_cache[position] = trace
        return trace_cache[position]

    development_positions = [int(value) for value in contract["split"]["development_positions"]]
    development_traces = [load_trace(position) for position in development_positions]
    axes, axis_diagnostics = _principal_axes(development_traces, sides)
    quantiles = [float(value) for value in contract["sampling"]["within_episode_quantiles"]]
    development_bindings = _sample_rows(frame_rows, development_positions, quantiles)

    def prepare_samples(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for binding in bindings:
            grouped.setdefault(int(binding["split_position"]), []).append(binding)
        prepared: list[dict[str, Any]] = []
        for position, rows in grouped.items():
            episode = episode_by_position[position]
            trace = load_trace(position)
            video = episode["physical_video"]
            if sha256_file(REPO_ROOT / video["path"]) != video["sha256"]:
                raise ValueError("OR104 physical video hash mismatch")
            physical_frames = [
                cv2.flip(frame, -1)
                for frame in _decode_selected_frames(
                    REPO_ROOT / video["path"],
                    selected_indices=np.asarray([int(row["physical_frame_index"]) for row in rows], dtype=np.int64),
                    expected_frame_count=int(video["frame_count"]),
                    expected_width=int(video["width_px"]),
                    expected_height=int(video["height_px"]),
                    output_width=int(renderer["width_px"]),
                    output_height=int(renderer["height_px"]),
                )
            ]
            initial_raw = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
            initial_registered = _independently_registered_trace(
                initial_raw,
                anchor_body_id=int(static["anchor_body_id"]),
                left_body_ids=left_ids,
                right_body_ids=right_ids,
                vector=robot_vector,
            )["frames"][0]
            for binding, physical in zip(rows, physical_frames, strict=True):
                trace_index = int(binding["state_trace_frame_index"])
                one_raw = {"body_names": trace["body_names"], "frames": [trace["frames"][trace_index]]}
                registered = _independently_registered_trace(
                    one_raw,
                    anchor_body_id=int(static["anchor_body_id"]),
                    left_body_ids=left_ids,
                    right_body_ids=right_ids,
                    vector=robot_vector,
                )
                prepared.append(
                    {
                        "binding": binding,
                        "episode": episode,
                        "trace": registered,
                        "initial_frame": initial_registered,
                        "physical": physical,
                        "physical_gray": cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                    }
                )
        return sorted(prepared, key=lambda row: (int(row["binding"]["split_position"]), int(row["binding"]["evaluation_index"])))

    prepared_development = prepare_samples(development_bindings)
    triangle_counts: list[int] = []
    raster_seconds: list[float] = []

    def render_sample(sample: dict[str, Any], gain: float, offset: float) -> tuple[np.ndarray, dict[str, Any]]:
        articulated = _articulated_trace(
            sample["trace"],
            initial_frame=sample["initial_frame"],
            axes=axes,
            sides=sides,
            gain=gain,
            offset_degrees=offset,
        )
        pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(
            scene, articulated, meshes, camera, renderer, static_family, static_vector
        )
        simulator, updates, occluded, raster_elapsed = _native_rasterize(library_path, pixels, depths, colors, renderer)
        candidate = apply_monotone_response(
            simulator,
            bias=float(response["bias"]),
            low_slope=float(response["low_intensity_slope"]),
            high_slope=float(response["high_intensity_slope"]),
            knot=int(response["fixed_input_knot"]),
        )
        candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        triangle_counts.append(int(triangle_count))
        raster_seconds.append(float(raster_elapsed))
        return candidate, {
            "whole_frame": _metrics(sample["physical"], candidate, edge),
            "board_plus_margin": _masked_tolerant_edge_f1(sample["physical_gray"], candidate_gray, board_mask, edge),
            "outside_board": _masked_tolerant_edge_f1(sample["physical_gray"], candidate_gray, outside_mask, edge),
            "render": {"triangle_count": int(triangle_count), "depth_updates": int(updates), "occluded_fragments": int(occluded), "native_raster_seconds": float(raster_elapsed)},
        }

    gains = [float(value) for value in contract["candidate_family"]["excursion_gain_candidates"]]
    offsets = [float(value) for value in contract["candidate_family"]["offset_degree_candidates"]]
    candidate_rows: list[dict[str, Any]] = []
    identity_images: list[np.ndarray] | None = None
    selected_images: list[np.ndarray] = []
    best_key: tuple[float, ...] | None = None
    selected_candidate: dict[str, Any] | None = None
    started = time.perf_counter()
    for gain in gains:
        for offset in offsets:
            rows: list[dict[str, Any]] = []
            images: list[np.ndarray] = []
            for sample in prepared_development:
                image, metrics = render_sample(sample, gain, offset)
                images.append(image)
                binding = sample["binding"]
                rows.append(
                    {
                        "split_position": int(binding["split_position"]),
                        "recording_id": binding["recording_id"],
                        "evaluation_index": int(binding["evaluation_index"]),
                        "state_trace_frame_index": int(binding["state_trace_frame_index"]),
                        "physical_frame_index": int(binding["physical_frame_index"]),
                        "metrics": metrics,
                    }
                )
            candidate = {
                "gain": gain,
                "offset_degrees": offset,
                "rows": rows,
                "mean_outside_board_edge_f1": _mean(rows, ("metrics", "outside_board", "f1")),
                "mean_board_plus_margin_edge_f1": _mean(rows, ("metrics", "board_plus_margin", "f1")),
                "mean_full_frame_linear_similarity": _mean(rows, ("metrics", "whole_frame", "full_frame_linear_pixel_similarity")),
            }
            candidate_rows.append(candidate)
            if gain == 1.0 and offset == 0.0:
                identity_images = images
            key = (
                float(candidate["mean_outside_board_edge_f1"]),
                float(candidate["mean_board_plus_margin_edge_f1"]),
                float(candidate["mean_full_frame_linear_similarity"]),
                -abs(gain - 1.0),
                -abs(offset),
            )
            if best_key is None or key > best_key:
                best_key = key
                selected_candidate = candidate
                selected_images = images
    if selected_candidate is None or identity_images is None:
        raise RuntimeError("OR104 candidate search did not produce identity and selected candidates")
    identity_candidate = next(row for row in candidate_rows if row["gain"] == 1.0 and row["offset_degrees"] == 0.0)
    selected_pair = (float(selected_candidate["gain"]), float(selected_candidate["offset_degrees"]))
    identity_rows = identity_candidate["rows"]
    development_rows: list[dict[str, Any]] = []
    baseline_errors: list[float] = []
    montage_rows: list[np.ndarray] = []
    for sample, identity, selected, identity_row, selected_row in zip(
        prepared_development, identity_images, selected_images, identity_rows, selected_candidate["rows"], strict=True
    ):
        binding = sample["binding"]
        or95 = or95_row_by_key[(int(binding["split_position"]), int(binding["evaluation_index"]))]
        comparisons = {
            "full_frame_linear_pixel_similarity": abs(float(identity_row["metrics"]["whole_frame"]["full_frame_linear_pixel_similarity"]) - float(or95["full_frame_linear_pixel_similarity"])),
            "board_plus_margin_edge_f1": abs(float(identity_row["metrics"]["board_plus_margin"]["f1"]) - float(or95["board_plus_margin_edge_f1"])),
            "outside_board_edge_f1": abs(float(identity_row["metrics"]["outside_board"]["f1"]) - float(or95["outside_board_edge_f1"])),
            "whole_frame_tolerant_edge_f1": abs(float(identity_row["metrics"]["whole_frame"]["tolerant_edge_f1"]) - float(or95["whole_frame_tolerant_edge_f1"])),
        }
        baseline_errors.extend(comparisons.values())
        development_rows.append(
            {
                "split_position": int(binding["split_position"]),
                "recording_id": binding["recording_id"],
                "evaluation_index": int(binding["evaluation_index"]),
                "state_trace_frame_index": int(binding["state_trace_frame_index"]),
                "physical_frame_index": int(binding["physical_frame_index"]),
                "identity": identity_row["metrics"],
                "selected": selected_row["metrics"],
                "identity_absolute_error_vs_or95": comparisons,
                "outside_board_edge_f1_delta": float(selected_row["metrics"]["outside_board"]["f1"] - identity_row["metrics"]["outside_board"]["f1"]),
                "board_plus_margin_edge_f1_delta": float(selected_row["metrics"]["board_plus_margin"]["f1"] - identity_row["metrics"]["board_plus_margin"]["f1"]),
                "full_frame_linear_similarity_delta": float(selected_row["metrics"]["whole_frame"]["full_frame_linear_pixel_similarity"] - identity_row["metrics"]["whole_frame"]["full_frame_linear_pixel_similarity"]),
            }
        )
        montage_rows.append(np.concatenate([sample["physical"], identity, selected], axis=1))
    development_montage = _write_png(output_directory / "development_physical_identity_selected.png", np.concatenate(montage_rows, axis=0))

    dev_identity_outside = _mean(development_rows, ("identity", "outside_board", "f1"))
    dev_selected_outside = _mean(development_rows, ("selected", "outside_board", "f1"))
    dev_identity_board = _mean(development_rows, ("identity", "board_plus_margin", "f1"))
    dev_selected_board = _mean(development_rows, ("selected", "board_plus_margin", "f1"))
    dev_identity_full = _mean(development_rows, ("identity", "whole_frame", "full_frame_linear_pixel_similarity"))
    dev_selected_full = _mean(development_rows, ("selected", "whole_frame", "full_frame_linear_pixel_similarity"))
    dev_material = sum(row["outside_board_edge_f1_delta"] >= 0.01 for row in development_rows)
    acceptance = contract["acceptance"]
    development_gates = {
        "minimum_selected_minus_identity_mean_outside_board_edge_f1": dev_selected_outside - dev_identity_outside >= float(acceptance["development_minimum_selected_minus_identity_mean_outside_board_edge_f1"]),
        "minimum_samples_with_outside_gain_at_least_0p01": dev_material >= int(acceptance["development_minimum_samples_with_outside_gain_at_least_0p01"]),
        "bounded_board_plus_margin_edge_f1_regression": dev_selected_board - dev_identity_board >= float(acceptance["minimum_selected_minus_identity_mean_board_plus_margin_edge_f1"]),
        "bounded_full_frame_linear_similarity_regression": dev_selected_full - dev_identity_full >= float(acceptance["minimum_selected_minus_identity_mean_full_frame_linear_similarity"]),
    }
    development_passed = all(development_gates.values())

    validation_rows: list[dict[str, Any]] = []
    validation_gates: dict[str, bool] | None = None
    validation_montage: dict[str, Any] | None = None
    validation_positions = [int(value) for value in contract["split"]["validation_positions"]]
    validation_decodes = 0
    if development_passed:
        validation_bindings = _sample_rows(frame_rows, validation_positions, quantiles)
        prepared_validation = prepare_samples(validation_bindings)
        validation_decodes = len(validation_positions)
        validation_montage_rows: list[np.ndarray] = []
        for sample in prepared_validation:
            selected_image, selected_metrics = render_sample(sample, *selected_pair)
            binding = sample["binding"]
            baseline = or95_row_by_key[(int(binding["split_position"]), int(binding["evaluation_index"]))]
            validation_rows.append(
                {
                    "split_position": int(binding["split_position"]),
                    "recording_id": binding["recording_id"],
                    "evaluation_index": int(binding["evaluation_index"]),
                    "state_trace_frame_index": int(binding["state_trace_frame_index"]),
                    "physical_frame_index": int(binding["physical_frame_index"]),
                    "identity_or95": {
                        "outside_board_edge_f1": float(baseline["outside_board_edge_f1"]),
                        "board_plus_margin_edge_f1": float(baseline["board_plus_margin_edge_f1"]),
                        "full_frame_linear_pixel_similarity": float(baseline["full_frame_linear_pixel_similarity"]),
                    },
                    "selected": selected_metrics,
                    "outside_board_edge_f1_delta": float(selected_metrics["outside_board"]["f1"] - baseline["outside_board_edge_f1"]),
                    "board_plus_margin_edge_f1_delta": float(selected_metrics["board_plus_margin"]["f1"] - baseline["board_plus_margin_edge_f1"]),
                    "full_frame_linear_similarity_delta": float(selected_metrics["whole_frame"]["full_frame_linear_pixel_similarity"] - baseline["full_frame_linear_pixel_similarity"]),
                }
            )
            validation_montage_rows.append(np.concatenate([sample["physical"], selected_image], axis=1))
        validation_montage = {
            **_write_png(output_directory / "validation_physical_selected.png", np.concatenate(validation_montage_rows, axis=0)),
            "layout": "physical_left_selected_right",
        }
        val_identity_outside = float(np.mean([row["identity_or95"]["outside_board_edge_f1"] for row in validation_rows]))
        val_selected_outside = _mean(validation_rows, ("selected", "outside_board", "f1"))
        val_identity_board = float(np.mean([row["identity_or95"]["board_plus_margin_edge_f1"] for row in validation_rows]))
        val_selected_board = _mean(validation_rows, ("selected", "board_plus_margin", "f1"))
        val_identity_full = float(np.mean([row["identity_or95"]["full_frame_linear_pixel_similarity"] for row in validation_rows]))
        val_selected_full = _mean(validation_rows, ("selected", "whole_frame", "full_frame_linear_pixel_similarity"))
        val_material = sum(row["outside_board_edge_f1_delta"] >= 0.01 for row in validation_rows)
        validation_gates = {
            "minimum_selected_minus_identity_mean_outside_board_edge_f1": val_selected_outside - val_identity_outside >= float(acceptance["validation_minimum_selected_minus_identity_mean_outside_board_edge_f1"]),
            "minimum_samples_with_outside_gain_at_least_0p01": val_material >= int(acceptance["validation_minimum_samples_with_outside_gain_at_least_0p01"]),
            "bounded_board_plus_margin_edge_f1_regression": val_selected_board - val_identity_board >= float(acceptance["minimum_selected_minus_identity_mean_board_plus_margin_edge_f1"]),
            "bounded_full_frame_linear_similarity_regression": val_selected_full - val_identity_full >= float(acceptance["minimum_selected_minus_identity_mean_full_frame_linear_similarity"]),
        }
    validation_passed = validation_gates is not None and all(validation_gates.values())
    expected_dev_renders = int(contract["resource_boundary"]["exact_full_mesh_development_candidate_renders_allowed"])
    expected_val_renders = int(contract["resource_boundary"]["exact_full_mesh_validation_selected_renders_allowed_if_development_passes"])
    integrity_gates = {
        "exact_twenty_one_development_samples": len(development_rows) == int(contract["gates"]["expected_development_sample_count"]),
        "exact_twenty_five_candidate_pairs": len(candidate_rows) == int(contract["gates"]["expected_candidate_pair_count"]),
        "identity_baseline_reproduces_or95": max(baseline_errors) <= float(contract["gates"]["maximum_identity_baseline_metric_absolute_error_vs_or95"]),
        "exact_development_render_count": len(candidate_rows) * len(prepared_development) == expected_dev_renders,
        "validation_condition_and_count_respected": (len(validation_rows) == expected_val_renders) == development_passed,
        "expected_triangle_count_every_render": all(value == int(contract["gates"]["expected_total_raster_triangle_count_per_frame"]) for value in triangle_counts),
        "manifest_unique_assets_read_once": len(asset_receipts) == int(contract["gates"]["expected_unique_mesh_asset_reads"]),
        "one_shared_pair_selected_before_validation": True,
        "development_only_axis_basis": True,
        "no_pixel_warp_composite_replay_action_state_dynamics_timing_contact_hardware_or_paid_compute": True,
        "retrospective_calibration_not_fidelity_transfer_or_promotion": True,
    }
    if development_passed and validation_passed and all(integrity_gates.values()):
        status = "PASS_SHARED_SHOULDER_LIFT_ARTICULATION_VALIDATED"
        reviewer_decision = "FREEZE_SHARED_SHOULDER_LIFT_FULL_TIMELINE_DIAGNOSTIC"
        next_transition = "freeze_or105_shared_shoulder_lift_full_timeline_diagnostic"
    elif not development_passed:
        status = "TERMINAL_SHARED_SHOULDER_LIFT_ARTICULATION_DEVELOPMENT_GATE_FAILED"
        reviewer_decision = "REJECT_SHARED_SHOULDER_LIFT_AND_REATTRIBUTE_ARTICULATION_RESIDUAL"
        next_transition = "freeze_or105_alternate_articulation_residual_attribution"
    else:
        status = "TERMINAL_SHARED_SHOULDER_LIFT_ARTICULATION_VALIDATION_GATE_FAILED"
        reviewer_decision = "REJECT_SHARED_SHOULDER_LIFT_AND_REATTRIBUTE_ARTICULATION_RESIDUAL"
        next_transition = "freeze_or105_alternate_articulation_residual_attribution"
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_shared_shoulder_lift_articulation_calibration_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "axis_basis": axis_diagnostics,
        "candidate_rows": candidate_rows,
        "selected_pair": {"excursion_gain": selected_pair[0], "offset_degrees": selected_pair[1]},
        "development_rows": development_rows,
        "development_summary": {
            "identity_mean_outside_board_edge_f1": dev_identity_outside,
            "selected_mean_outside_board_edge_f1": dev_selected_outside,
            "selected_minus_identity_mean_outside_board_edge_f1": dev_selected_outside - dev_identity_outside,
            "samples_with_outside_gain_at_least_0p01": dev_material,
            "identity_mean_board_plus_margin_edge_f1": dev_identity_board,
            "selected_mean_board_plus_margin_edge_f1": dev_selected_board,
            "selected_minus_identity_mean_board_plus_margin_edge_f1": dev_selected_board - dev_identity_board,
            "identity_mean_full_frame_linear_similarity": dev_identity_full,
            "selected_mean_full_frame_linear_similarity": dev_selected_full,
            "selected_minus_identity_mean_full_frame_linear_similarity": dev_selected_full - dev_identity_full,
            "maximum_identity_baseline_metric_absolute_error_vs_or95": max(baseline_errors),
        },
        "development_montage": {**development_montage, "layout": "physical_left_identity_middle_selected_right"},
        "validation_rows": validation_rows,
        "validation_summary": None if not validation_rows else {
            "identity_mean_outside_board_edge_f1": float(np.mean([row["identity_or95"]["outside_board_edge_f1"] for row in validation_rows])),
            "selected_mean_outside_board_edge_f1": _mean(validation_rows, ("selected", "outside_board", "f1")),
            "selected_minus_identity_mean_outside_board_edge_f1": float(np.mean([row["outside_board_edge_f1_delta"] for row in validation_rows])),
            "samples_with_outside_gain_at_least_0p01": sum(row["outside_board_edge_f1_delta"] >= 0.01 for row in validation_rows),
            "selected_minus_identity_mean_board_plus_margin_edge_f1": float(np.mean([row["board_plus_margin_edge_f1_delta"] for row in validation_rows])),
            "selected_minus_identity_mean_full_frame_linear_similarity": float(np.mean([row["full_frame_linear_similarity_delta"] for row in validation_rows])),
        },
        "validation_montage": validation_montage,
        "gates": {"development": development_gates, "validation": validation_gates, "integrity": integrity_gates},
        "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "execution": {
            "development_state_trace_reads": len(development_positions),
            "validation_state_trace_reads": validation_decodes,
            "already_open_development_physical_episode_decodes": len(development_positions),
            "already_open_validation_physical_episode_decodes": validation_decodes,
            "development_physical_frames_compared": len(development_rows),
            "validation_physical_frames_compared": len(validation_rows),
            "candidate_pair_values": len(candidate_rows),
            "fits": 1,
            "exact_full_mesh_development_candidate_renders": expected_dev_renders,
            "exact_full_mesh_validation_selected_renders": len(validation_rows),
            "mean_native_raster_seconds": float(np.mean(raster_seconds)),
            "simulator_replays": 0,
            "action_or_state_mutations": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "elapsed_seconds": time.perf_counter() - started,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": reviewer_decision,
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(calibrate_once(), sort_keys=True))
