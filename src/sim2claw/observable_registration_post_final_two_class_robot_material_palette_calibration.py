"""Calibrate one shared structural/servo renderer palette with no-refit validation."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_scene_composition_residual_attribution import _masked_tolerant_edge_f1
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _prepare_full_mesh_stream, _region_masks
from .observable_registration_development_initial_shared_3d_camera_fit import _metrics
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png
from .observable_registration_post_final_shared_shoulder_lift_articulation_calibration import _mean, _sample_rows
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_final_two_class_robot_material_palette_calibration_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_two_class_robot_material_palette_calibration_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_two_class_robot_material_palette_calibration_v1"


def load_post_final_two_class_robot_material_palette_calibration_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR106 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)):
        raise ValueError("OR106 split drifted")
    if split["validation_render_requires_development_gate"] is not True or split["validation_never_selects_or_refits"] is not True:
        raise ValueError("OR106 validation boundary drifted")
    if contract["sampling"]["within_episode_quantiles"] != [0.25, 0.5, 0.75] or contract["sampling"]["samples_per_episode"] != 3:
        raise ValueError("OR106 sample family drifted")
    family = contract["candidate_family"]
    if family["structural_grayscale_albedo_candidates"] != [0.5, 0.7, 0.85, 1.0] or family["servo_grayscale_albedo_candidates"] != [0.05, 0.15, 0.3, 0.5]:
        raise ValueError("OR106 palette family drifted")
    if family["identity_pair"] != [0.5, 0.5] or family["one_shared_pair_for_both_robots_all_frames_and_episodes"] is not True:
        raise ValueError("OR106 shared identity boundary drifted")
    if family["per_frame_side_episode_or_mesh_values"] is not False or family["pixel_warp_composite_texture_projection_or_mask_edit"] is not False:
        raise ValueError("OR106 material-only boundary drifted")
    expected = {
        "development_state_trace_reads_allowed": 7,
        "validation_state_trace_reads_allowed_if_development_passes": 4,
        "already_open_development_physical_episode_decodes_allowed": 7,
        "already_open_validation_physical_episode_decodes_allowed_if_development_passes": 4,
        "development_physical_frames_compared_allowed": 21,
        "validation_physical_frames_compared_allowed_if_development_passes": 12,
        "candidate_pair_values_allowed": 16,
        "fits_allowed": 1,
        "exact_full_mesh_development_candidate_renders_allowed": 336,
        "exact_full_mesh_validation_selected_renders_allowed_if_development_passes": 12,
        "simulator_replays_allowed": 0,
        "action_or_state_mutations_allowed": 0,
        "hardware_actions_allowed": 0,
        "paid_compute_allowed": False,
    }
    if contract["resource_boundary"] != expected or any(contract["authority"].values()):
        raise ValueError("OR106 resource or authority boundary drifted")
    if contract["claim_limits"]["same_video_semantic_match"] is not False or contract["claim_limits"]["untouched_cohort_remaining"] is not False:
        raise ValueError("OR106 claim boundary drifted")
    return contract


def _base_name(name: str) -> str:
    for prefix in ("left_", "right_"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def _material_scene(
    scene: dict[str, Any],
    classes: dict[str, set[str]],
    structural_albedo: float,
    servo_albedo: float,
) -> dict[str, Any]:
    mesh_name_by_id = {int(row["id"]): row["name"] for row in scene["meshes"]}
    candidate = dict(scene)
    candidate_geoms: list[dict[str, Any]] = []
    for geom in scene["geoms"]:
        body_id = int(geom["body_id"])
        if not (29 <= body_id <= 44 and geom["type"] == "mesh"):
            candidate_geoms.append(dict(geom))
            continue
        base = _base_name(mesh_name_by_id[int(geom["mesh_id"])])
        if base in classes["servo"]:
            value = float(servo_albedo)
        elif base in classes["structural"]:
            value = float(structural_albedo)
        else:
            raise ValueError(f"OR106 unclassified robot visual mesh: {base}")
        updated = dict(geom)
        updated["rgba"] = [value, value, value, 1.0]
        candidate_geoms.append(updated)
    candidate["geoms"] = candidate_geoms
    return candidate


def calibrate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR106 one-run receipt already exists")
    contract = load_post_final_two_class_robot_material_palette_calibration_contract(contract_path)
    or105 = json.loads((REPO_ROOT / contract["sources"]["or105_closeout"]["path"]).read_text())
    if or105["reviewer_decision"] != "FREEZE_TWO_CLASS_ROBOT_MATERIAL_PALETTE_CALIBRATION":
        raise ValueError("OR105 did not authorize material palette calibration")
    or105_receipt = json.loads((REPO_ROOT / contract["sources"]["or105_receipt"]["path"]).read_text())
    if or105_receipt["artifact_sha256"] != contract["sources"]["or105_receipt"]["artifact_sha256"]:
        raise ValueError("OR105 artifact identity drifted")
    classes = {
        "servo": set(or105_receipt["summary"]["upstream_dark_servo_meshes"]),
        "structural": set(or105_receipt["summary"]["upstream_nonservo_structural_meshes"]),
    }
    if classes["servo"] & classes["structural"] or not classes["servo"] or not classes["structural"]:
        raise ValueError("OR106 material class partition drifted")
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    or95_receipt = json.loads((REPO_ROOT / contract["sources"]["or95_receipt"]["path"]).read_text())
    if or95_receipt["artifact_sha256"] != contract["sources"]["or95_receipt"]["artifact_sha256"]:
        raise ValueError("OR95 artifact identity drifted")
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())["rows"]
    baseline_by_key = {(int(row["split_position"]), int(row["evaluation_index"])): row for row in frame_rows}
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("OR106 scene revision mismatch")
    body_names = [row["name"] for row in scene["bodies"]]
    frozen = or95_contract["frozen_candidate"]
    camera = frozen["camera"]
    static = frozen["static_workcell_transform"]
    static_family = {"anchor_body_id": int(static["anchor_body_id"]), "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]]}
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
        {"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}}, output_directory
    )
    trace_cache: dict[int, dict[str, Any]] = {}

    def load_trace(position: int) -> dict[str, Any]:
        if position not in trace_cache:
            binding = episode_by_position[position]["state_trace"]
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError("OR106 trace hash mismatch")
            trace = json.loads((REPO_ROOT / binding["path"]).read_text())
            if trace["body_names"] != body_names:
                raise ValueError("OR106 scene and trace body ordering drifted")
            trace_cache[position] = trace
        return trace_cache[position]

    def prepare(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for binding in bindings:
            grouped.setdefault(int(binding["split_position"]), []).append(binding)
        prepared: list[dict[str, Any]] = []
        for position, rows in grouped.items():
            episode = episode_by_position[position]
            trace = load_trace(position)
            video = episode["physical_video"]
            if sha256_file(REPO_ROOT / video["path"]) != video["sha256"]:
                raise ValueError("OR106 physical video hash mismatch")
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
            for binding, physical in zip(rows, physical_frames, strict=True):
                one = {"body_names": trace["body_names"], "frames": [trace["frames"][int(binding["state_trace_frame_index"])]]}
                registered = _independently_registered_trace(
                    one,
                    anchor_body_id=int(static["anchor_body_id"]),
                    left_body_ids=left_ids,
                    right_body_ids=right_ids,
                    vector=robot_vector,
                )
                prepared.append({"binding": binding, "trace": registered, "physical": physical, "physical_gray": cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)})
        return sorted(prepared, key=lambda row: (int(row["binding"]["split_position"]), int(row["binding"]["evaluation_index"])))

    quantiles = [float(value) for value in contract["sampling"]["within_episode_quantiles"]]
    development_positions = [int(value) for value in contract["split"]["development_positions"]]
    development = prepare(_sample_rows(frame_rows, development_positions, quantiles))
    triangle_counts: list[int] = []
    raster_seconds: list[float] = []

    def render(sample: dict[str, Any], candidate_scene: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
        pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(candidate_scene, sample["trace"], meshes, camera, renderer, static_family, static_vector)
        simulator, updates, occluded, elapsed = _native_rasterize(library_path, pixels, depths, colors, renderer)
        candidate = apply_monotone_response(simulator, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
        gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        triangle_counts.append(int(triangle_count))
        raster_seconds.append(float(elapsed))
        return candidate, {
            "whole_frame": _metrics(sample["physical"], candidate, edge),
            "board_plus_margin": _masked_tolerant_edge_f1(sample["physical_gray"], gray, board_mask, edge),
            "outside_board": _masked_tolerant_edge_f1(sample["physical_gray"], gray, outside_mask, edge),
            "render": {"triangle_count": int(triangle_count), "depth_updates": int(updates), "occluded_fragments": int(occluded), "native_raster_seconds": float(elapsed)},
        }

    structural_values = [float(value) for value in contract["candidate_family"]["structural_grayscale_albedo_candidates"]]
    servo_values = [float(value) for value in contract["candidate_family"]["servo_grayscale_albedo_candidates"]]
    candidate_rows: list[dict[str, Any]] = []
    identity_images: list[np.ndarray] | None = None
    selected_images: list[np.ndarray] = []
    selected_candidate: dict[str, Any] | None = None
    best_key: tuple[float, ...] | None = None
    started = time.perf_counter()
    for structural in structural_values:
        for servo in servo_values:
            candidate_scene = _material_scene(scene, classes, structural, servo)
            rows: list[dict[str, Any]] = []
            images: list[np.ndarray] = []
            for sample in development:
                image, metrics = render(sample, candidate_scene)
                images.append(image)
                binding = sample["binding"]
                rows.append({"split_position": int(binding["split_position"]), "recording_id": binding["recording_id"], "evaluation_index": int(binding["evaluation_index"]), "state_trace_frame_index": int(binding["state_trace_frame_index"]), "physical_frame_index": int(binding["physical_frame_index"]), "metrics": metrics})
            candidate = {
                "structural_albedo": structural,
                "servo_albedo": servo,
                "rows": rows,
                "mean_full_frame_linear_similarity": _mean(rows, ("metrics", "whole_frame", "full_frame_linear_pixel_similarity")),
                "mean_outside_board_edge_f1": _mean(rows, ("metrics", "outside_board", "f1")),
                "mean_board_plus_margin_edge_f1": _mean(rows, ("metrics", "board_plus_margin", "f1")),
            }
            candidate_rows.append(candidate)
            if structural == 0.5 and servo == 0.5:
                identity_images = images
            key = (float(candidate["mean_full_frame_linear_similarity"]), float(candidate["mean_outside_board_edge_f1"]), float(candidate["mean_board_plus_margin_edge_f1"]), -abs(structural - 0.5), -abs(servo - 0.5))
            if best_key is None or key > best_key:
                best_key = key
                selected_candidate = candidate
                selected_images = images
    if selected_candidate is None or identity_images is None:
        raise RuntimeError("OR106 did not produce identity and selected palettes")
    identity_candidate = next(row for row in candidate_rows if row["structural_albedo"] == 0.5 and row["servo_albedo"] == 0.5)
    selected_pair = (float(selected_candidate["structural_albedo"]), float(selected_candidate["servo_albedo"]))
    development_rows: list[dict[str, Any]] = []
    baseline_errors: list[float] = []
    montage_rows: list[np.ndarray] = []
    for sample, identity_image, selected_image, identity_row, selected_row in zip(development, identity_images, selected_images, identity_candidate["rows"], selected_candidate["rows"], strict=True):
        binding = sample["binding"]
        baseline = baseline_by_key[(int(binding["split_position"]), int(binding["evaluation_index"]))]
        errors = {
            "full_frame_linear_pixel_similarity": abs(float(identity_row["metrics"]["whole_frame"]["full_frame_linear_pixel_similarity"]) - float(baseline["full_frame_linear_pixel_similarity"])),
            "board_plus_margin_edge_f1": abs(float(identity_row["metrics"]["board_plus_margin"]["f1"]) - float(baseline["board_plus_margin_edge_f1"])),
            "outside_board_edge_f1": abs(float(identity_row["metrics"]["outside_board"]["f1"]) - float(baseline["outside_board_edge_f1"])),
        }
        baseline_errors.extend(errors.values())
        development_rows.append({
            "split_position": int(binding["split_position"]), "recording_id": binding["recording_id"], "evaluation_index": int(binding["evaluation_index"]),
            "identity": identity_row["metrics"], "selected": selected_row["metrics"], "identity_absolute_error_vs_or95": errors,
            "full_frame_linear_similarity_delta": float(selected_row["metrics"]["whole_frame"]["full_frame_linear_pixel_similarity"] - identity_row["metrics"]["whole_frame"]["full_frame_linear_pixel_similarity"]),
            "outside_board_edge_f1_delta": float(selected_row["metrics"]["outside_board"]["f1"] - identity_row["metrics"]["outside_board"]["f1"]),
            "board_plus_margin_edge_f1_delta": float(selected_row["metrics"]["board_plus_margin"]["f1"] - identity_row["metrics"]["board_plus_margin"]["f1"]),
        })
        montage_rows.append(np.concatenate([sample["physical"], identity_image, selected_image], axis=1))
    development_montage = _write_png(output_directory / "development_physical_identity_selected.png", np.concatenate(montage_rows, axis=0))
    dev_identity_full = _mean(development_rows, ("identity", "whole_frame", "full_frame_linear_pixel_similarity"))
    dev_selected_full = _mean(development_rows, ("selected", "whole_frame", "full_frame_linear_pixel_similarity"))
    dev_identity_outside = _mean(development_rows, ("identity", "outside_board", "f1"))
    dev_selected_outside = _mean(development_rows, ("selected", "outside_board", "f1"))
    dev_identity_board = _mean(development_rows, ("identity", "board_plus_margin", "f1"))
    dev_selected_board = _mean(development_rows, ("selected", "board_plus_margin", "f1"))
    dev_material = sum(row["full_frame_linear_similarity_delta"] >= 0.002 for row in development_rows)
    acceptance = contract["acceptance"]
    development_gates = {
        "minimum_selected_minus_identity_mean_full_frame_linear_similarity": dev_selected_full - dev_identity_full >= float(acceptance["development_minimum_selected_minus_identity_mean_full_frame_linear_similarity"]),
        "minimum_samples_with_full_frame_gain_at_least_0p002": dev_material >= int(acceptance["development_minimum_samples_with_full_frame_gain_at_least_0p002"]),
        "bounded_outside_board_edge_f1_regression": dev_selected_outside - dev_identity_outside >= float(acceptance["minimum_selected_minus_identity_mean_outside_board_edge_f1"]),
        "bounded_board_plus_margin_edge_f1_regression": dev_selected_board - dev_identity_board >= float(acceptance["minimum_selected_minus_identity_mean_board_plus_margin_edge_f1"]),
    }
    development_passed = all(development_gates.values())
    validation_rows: list[dict[str, Any]] = []
    validation_gates: dict[str, bool] | None = None
    validation_montage: dict[str, Any] | None = None
    validation_decodes = 0
    if development_passed:
        validation_positions = [int(value) for value in contract["split"]["validation_positions"]]
        validation = prepare(_sample_rows(frame_rows, validation_positions, quantiles))
        validation_decodes = len(validation_positions)
        selected_scene = _material_scene(scene, classes, *selected_pair)
        montage: list[np.ndarray] = []
        for sample in validation:
            image, metrics = render(sample, selected_scene)
            binding = sample["binding"]
            baseline = baseline_by_key[(int(binding["split_position"]), int(binding["evaluation_index"]))]
            validation_rows.append({
                "split_position": int(binding["split_position"]), "recording_id": binding["recording_id"], "evaluation_index": int(binding["evaluation_index"]),
                "identity_or95": {"full_frame_linear_pixel_similarity": float(baseline["full_frame_linear_pixel_similarity"]), "outside_board_edge_f1": float(baseline["outside_board_edge_f1"]), "board_plus_margin_edge_f1": float(baseline["board_plus_margin_edge_f1"])},
                "selected": metrics,
                "full_frame_linear_similarity_delta": float(metrics["whole_frame"]["full_frame_linear_pixel_similarity"] - baseline["full_frame_linear_pixel_similarity"]),
                "outside_board_edge_f1_delta": float(metrics["outside_board"]["f1"] - baseline["outside_board_edge_f1"]),
                "board_plus_margin_edge_f1_delta": float(metrics["board_plus_margin"]["f1"] - baseline["board_plus_margin_edge_f1"]),
            })
            montage.append(np.concatenate([sample["physical"], image], axis=1))
        validation_montage = {**_write_png(output_directory / "validation_physical_selected.png", np.concatenate(montage, axis=0)), "layout": "physical_left_selected_right"}
        val_full_delta = float(np.mean([row["full_frame_linear_similarity_delta"] for row in validation_rows]))
        val_outside_delta = float(np.mean([row["outside_board_edge_f1_delta"] for row in validation_rows]))
        val_board_delta = float(np.mean([row["board_plus_margin_edge_f1_delta"] for row in validation_rows]))
        val_material = sum(row["full_frame_linear_similarity_delta"] >= 0.002 for row in validation_rows)
        validation_gates = {
            "minimum_selected_minus_identity_mean_full_frame_linear_similarity": val_full_delta >= float(acceptance["validation_minimum_selected_minus_identity_mean_full_frame_linear_similarity"]),
            "minimum_samples_with_full_frame_gain_at_least_0p002": val_material >= int(acceptance["validation_minimum_samples_with_full_frame_gain_at_least_0p002"]),
            "bounded_outside_board_edge_f1_regression": val_outside_delta >= float(acceptance["minimum_selected_minus_identity_mean_outside_board_edge_f1"]),
            "bounded_board_plus_margin_edge_f1_regression": val_board_delta >= float(acceptance["minimum_selected_minus_identity_mean_board_plus_margin_edge_f1"]),
        }
    validation_passed = validation_gates is not None and all(validation_gates.values())
    expected_validation = int(contract["gates"]["expected_validation_sample_count"])
    integrity_gates = {
        "exact_twenty_one_development_samples": len(development_rows) == int(contract["gates"]["expected_development_sample_count"]),
        "exact_sixteen_candidate_pairs": len(candidate_rows) == int(contract["gates"]["expected_candidate_pair_count"]),
        "identity_baseline_reproduces_or95": max(baseline_errors) <= float(contract["gates"]["maximum_identity_baseline_metric_absolute_error_vs_or95"]),
        "exact_development_render_count": len(candidate_rows) * len(development) == int(contract["resource_boundary"]["exact_full_mesh_development_candidate_renders_allowed"]),
        "validation_condition_and_count_respected": (len(validation_rows) == expected_validation) == development_passed,
        "expected_triangle_count_every_render": all(value == int(contract["gates"]["expected_total_raster_triangle_count_per_frame"]) for value in triangle_counts),
        "manifest_unique_assets_read_once": len(asset_receipts) == int(contract["gates"]["expected_unique_mesh_asset_reads"]),
        "one_shared_pair_selected_before_validation": True,
        "complete_two_class_partition": True,
        "no_pixel_warp_composite_texture_projection_replay_action_state_dynamics_timing_contact_hardware_or_paid_compute": True,
        "retrospective_material_calibration_not_fidelity_transfer_or_promotion": True,
    }
    if development_passed and validation_passed and all(integrity_gates.values()):
        status = "PASS_TWO_CLASS_ROBOT_MATERIAL_PALETTE_VALIDATED"
        reviewer_decision = "FREEZE_TWO_CLASS_ROBOT_MATERIAL_FULL_TIMELINE_DIAGNOSTIC"
        next_transition = "freeze_or107_two_class_robot_material_full_timeline_diagnostic"
    elif not development_passed:
        status = "TERMINAL_TWO_CLASS_ROBOT_MATERIAL_PALETTE_DEVELOPMENT_GATE_FAILED"
        reviewer_decision = "REJECT_TWO_CLASS_ROBOT_MATERIAL_PALETTE_AND_ATTRIBUTE_EXOGENOUS_OPERATIONAL_CONTENT"
        next_transition = "freeze_or107_exogenous_operational_content_attribution"
    else:
        status = "TERMINAL_TWO_CLASS_ROBOT_MATERIAL_PALETTE_VALIDATION_GATE_FAILED"
        reviewer_decision = "REJECT_TWO_CLASS_ROBOT_MATERIAL_PALETTE_AND_ATTRIBUTE_EXOGENOUS_OPERATIONAL_CONTENT"
        next_transition = "freeze_or107_exogenous_operational_content_attribution"
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_two_class_robot_material_palette_calibration_receipt.v1",
        "experiment_id": contract["experiment_id"], "status": status, "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "material_classes": {key: sorted(value) for key, value in classes.items()},
        "candidate_rows": candidate_rows,
        "selected_pair": {"structural_grayscale_albedo": selected_pair[0], "servo_grayscale_albedo": selected_pair[1]},
        "development_rows": development_rows,
        "development_summary": {
            "identity_mean_full_frame_linear_similarity": dev_identity_full, "selected_mean_full_frame_linear_similarity": dev_selected_full, "selected_minus_identity_mean_full_frame_linear_similarity": dev_selected_full - dev_identity_full,
            "samples_with_full_frame_gain_at_least_0p002": dev_material,
            "identity_mean_outside_board_edge_f1": dev_identity_outside, "selected_mean_outside_board_edge_f1": dev_selected_outside, "selected_minus_identity_mean_outside_board_edge_f1": dev_selected_outside - dev_identity_outside,
            "identity_mean_board_plus_margin_edge_f1": dev_identity_board, "selected_mean_board_plus_margin_edge_f1": dev_selected_board, "selected_minus_identity_mean_board_plus_margin_edge_f1": dev_selected_board - dev_identity_board,
            "maximum_identity_baseline_metric_absolute_error_vs_or95": max(baseline_errors),
        },
        "development_montage": {**development_montage, "layout": "physical_left_identity_middle_selected_right"},
        "validation_rows": validation_rows,
        "validation_summary": None if not validation_rows else {
            "selected_minus_identity_mean_full_frame_linear_similarity": float(np.mean([row["full_frame_linear_similarity_delta"] for row in validation_rows])),
            "samples_with_full_frame_gain_at_least_0p002": sum(row["full_frame_linear_similarity_delta"] >= 0.002 for row in validation_rows),
            "selected_minus_identity_mean_outside_board_edge_f1": float(np.mean([row["outside_board_edge_f1_delta"] for row in validation_rows])),
            "selected_minus_identity_mean_board_plus_margin_edge_f1": float(np.mean([row["board_plus_margin_edge_f1_delta"] for row in validation_rows])),
        },
        "validation_montage": validation_montage,
        "gates": {"development": development_gates, "validation": validation_gates, "integrity": integrity_gates},
        "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "execution": {
            "development_state_trace_reads": len(development_positions), "validation_state_trace_reads": validation_decodes,
            "already_open_development_physical_episode_decodes": len(development_positions), "already_open_validation_physical_episode_decodes": validation_decodes,
            "development_physical_frames_compared": len(development_rows), "validation_physical_frames_compared": len(validation_rows),
            "candidate_pair_values": len(candidate_rows), "fits": 1,
            "exact_full_mesh_development_candidate_renders": len(candidate_rows) * len(development), "exact_full_mesh_validation_selected_renders": len(validation_rows),
            "mean_native_raster_seconds": float(np.mean(raster_seconds)), "simulator_replays": 0, "action_or_state_mutations": 0, "hardware_actions": 0, "paid_compute": False,
            "elapsed_seconds": time.perf_counter() - started,
        },
        "claim_limits": contract["claim_limits"], "reviewer_decision": reviewer_decision, "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(calibrate_once(), sort_keys=True))
