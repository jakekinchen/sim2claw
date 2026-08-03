"""Fit one bounded renderer-native white side-wall plane with no-refit validation."""

from __future__ import annotations

import json
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
from .observable_registration_post_final_renderer_native_white_enclosure_shell import _white_shell_scene
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_final_bounded_renderer_native_enclosure_plane_fit_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_bounded_renderer_native_enclosure_plane_fit_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_bounded_renderer_native_enclosure_plane_fit_v1"


def load_post_final_bounded_renderer_native_enclosure_plane_fit_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR100 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)):
        raise ValueError("OR100 split drifted")
    family = contract["candidate_family"]
    geom = family["new_geom"]
    if geom["body_id"] != 6 or geom["type"] != "box":
        raise ValueError("OR100 side-wall identity drifted")
    if geom["local_x_candidates_m"] != [-0.5, -0.475, -0.45, -0.425, -0.4, -0.375, -0.35, -0.325, -0.3]:
        raise ValueError("OR100 x family drifted")
    if geom["half_size_m"] != [0.035, 0.575, 0.95] or family["one_global_value_selected"] is not True:
        raise ValueError("OR100 plane geometry drifted")
    if family["per_episode_geometry"] is not False or family["flexible_mesh"] is not False:
        raise ValueError("OR100 geometry boundary drifted")
    if family["pixel_compositing_or_warp"] is not False or family["physics_or_state_mutated"] is not False:
        raise ValueError("OR100 pixel or physics boundary drifted")
    resources = contract["resource_boundary"]
    if resources["fits_allowed"] != 1 or resources["candidate_family_searches_allowed"] != 1:
        raise ValueError("OR100 fit boundary drifted")
    if resources["simulator_replays_allowed"] != 0 or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR100 resource boundary drifted")
    if any(contract["authority"].values()) or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR100 authority or claim boundary drifted")
    return contract


def _scene_with_side_wall(scene: dict[str, Any], contract: dict[str, Any], local_x: float) -> dict[str, Any]:
    shell_contract = {
        "frozen_candidate": {
            "renderer_only_background_body_id": 6,
            "renderer_only_kept_background_geom_names": ["rear_wall"],
            "renderer_only_removed_child_body_ids": [7],
        }
    }
    candidate = _white_shell_scene(scene, shell_contract)
    spec = contract["candidate_family"]["new_geom"]
    geom = {
        "id": max(int(value["id"]) for value in scene["geoms"]) + 1,
        "body_id": int(spec["body_id"]),
        "name": spec["name"],
        "type": spec["type"],
        "group": 1,
        "mesh_id": None,
        "position": [float(local_x), float(spec["local_y_m"]), float(spec["local_z_m"])],
        "quaternion_wxyz": [float(value) for value in spec["quaternion_wxyz"]],
        "size": [float(value) for value in spec["half_size_m"]],
        "rgba": [float(value) for value in spec["rgba"]],
    }
    candidate["geoms"] = [*candidate["geoms"], geom]
    return candidate


def _mean(rows: list[dict[str, Any]], path: tuple[str, ...]) -> float:
    values: list[float] = []
    for row in rows:
        value: Any = row
        for key in path:
            value = value[key]
        values.append(float(value))
    return float(np.mean(values))


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR100 one-run receipt already exists")
    contract = load_post_final_bounded_renderer_native_enclosure_plane_fit_contract(contract_path)
    or99_closeout = json.loads((REPO_ROOT / contract["sources"]["or99_closeout"]["path"]).read_text())
    if or99_closeout["reviewer_decision"] != "REJECT_SHELL_AND_FREEZE_BOUNDED_RENDERER_NATIVE_ENCLOSURE_PLANES":
        raise ValueError("OR99 did not authorize bounded enclosure planes")
    or99_receipt = json.loads((REPO_ROOT / contract["sources"]["or99_receipt"]["path"]).read_text())
    if or99_receipt["artifact_sha256"] != contract["sources"]["or99_receipt"]["artifact_sha256"]:
        raise ValueError("OR99 artifact identity drifted")
    shell_by_position = {int(row["split_position"]): row["shell"] for row in or99_receipt["rows"]}
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(episode["split_position"]): episode for episode in episodes}
    frozen = or95_contract["frozen_candidate"]
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    body_names = [body["name"] for body in scene["bodies"]]
    renderer = contract["renderer"]
    camera = frozen["camera"]
    static = frozen["static_workcell_transform"]
    static_family = {"anchor_body_id": int(static["anchor_body_id"]), "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]]}
    static_vector = np.asarray(static["vector"], dtype=np.float64)
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"], dtype=np.float64)
    response = frozen["global_monotone_response"]
    edge = contract["metric"]["edge"]
    board_mask, outside_mask = _region_masks(
        np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=320,
        height=240,
        dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native(
        {"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}},
        output_directory,
    )

    def prepare_episode(position: int) -> dict[str, Any]:
        episode = episode_by_position[position]
        trace_binding = episode["state_trace"]
        if sha256_file(REPO_ROOT / trace_binding["path"]) != trace_binding["sha256"]:
            raise ValueError("OR100 trace hash mismatch")
        trace = json.loads((REPO_ROOT / trace_binding["path"]).read_text())
        if trace["body_names"] != body_names:
            raise ValueError("scene and trace body ordering drifted")
        one_trace = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
        transformed = _independently_registered_trace(one_trace, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=robot_vector)
        video = episode["physical_video"]
        physical = cv2.flip(_decode_selected_frames(REPO_ROOT / video["path"], selected_indices=np.asarray([0], dtype=np.int64), expected_frame_count=int(video["frame_count"]), expected_width=int(video["width_px"]), expected_height=int(video["height_px"]), output_width=320, output_height=240)[0], -1)
        return {"episode": episode, "trace": transformed, "physical": physical}

    def render(prepared: dict[str, Any], local_x: float) -> tuple[np.ndarray, dict[str, Any]]:
        candidate_scene = _scene_with_side_wall(scene, contract, local_x)
        pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(candidate_scene, prepared["trace"], meshes, camera, renderer, static_family, static_vector)
        simulator, updates, occluded, raster_seconds = _native_rasterize(library_path, pixels, depths, colors, renderer)
        candidate = apply_monotone_response(simulator, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
        physical = prepared["physical"]
        physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
        candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        metrics = {
            "whole_frame": _metrics(physical, candidate, edge),
            "board_plus_margin": _masked_tolerant_edge_f1(physical_gray, candidate_gray, board_mask, edge),
            "outside_board": _masked_tolerant_edge_f1(physical_gray, candidate_gray, outside_mask, edge),
            "render": {"triangle_count": int(triangle_count), "depth_updates": int(updates), "occluded_fragments": int(occluded), "raster_seconds": float(raster_seconds)},
        }
        return candidate, metrics

    development_positions = [int(value) for value in contract["split"]["development_positions"]]
    prepared_development = {position: prepare_episode(position) for position in development_positions}
    candidate_frames: dict[tuple[float, int], np.ndarray] = {}
    candidate_rows: list[dict[str, Any]] = []
    for local_x in [float(value) for value in contract["candidate_family"]["new_geom"]["local_x_candidates_m"]]:
        rows: list[dict[str, Any]] = []
        for position in development_positions:
            frame, metrics = render(prepared_development[position], local_x)
            candidate_frames[(local_x, position)] = frame
            shell = shell_by_position[position]
            rows.append({"split_position": position, "recording_id": prepared_development[position]["episode"]["recording_id"], "selected": metrics, "shell": shell, "outside_board_edge_f1_delta": float(metrics["outside_board"]["f1"] - shell["outside_board"]["f1"]), "board_plus_margin_edge_f1_delta": float(metrics["board_plus_margin"]["f1"] - shell["board_plus_margin"]["f1"]), "full_frame_linear_similarity_delta": float(metrics["whole_frame"]["full_frame_linear_pixel_similarity"] - shell["whole_frame"]["full_frame_linear_pixel_similarity"])})
        candidate_rows.append({"local_x_m": local_x, "rows": rows, "mean_outside_board_edge_f1": _mean(rows, ("selected", "outside_board", "f1")), "mean_full_frame_linear_similarity": _mean(rows, ("selected", "whole_frame", "full_frame_linear_pixel_similarity"))})
    selected = max(candidate_rows, key=lambda row: (row["mean_outside_board_edge_f1"], row["mean_full_frame_linear_similarity"], -row["local_x_m"]))
    selected_x = float(selected["local_x_m"])
    development_rows = selected["rows"]
    dev_shell_outside = _mean(development_rows, ("shell", "outside_board", "f1"))
    dev_selected_outside = _mean(development_rows, ("selected", "outside_board", "f1"))
    dev_shell_board = _mean(development_rows, ("shell", "board_plus_margin", "f1"))
    dev_selected_board = _mean(development_rows, ("selected", "board_plus_margin", "f1"))
    dev_shell_linear = _mean(development_rows, ("shell", "whole_frame", "full_frame_linear_pixel_similarity"))
    dev_selected_linear = _mean(development_rows, ("selected", "whole_frame", "full_frame_linear_pixel_similarity"))
    dev_material = sum(row["outside_board_edge_f1_delta"] >= 0.01 for row in development_rows)
    acceptance = contract["acceptance"]
    development_gates = {
        "minimum_selected_mean_outside_board_edge_f1": dev_selected_outside >= float(acceptance["development_minimum_selected_mean_outside_board_edge_f1"]),
        "minimum_selected_minus_shell_mean_outside_board_edge_f1": dev_selected_outside - dev_shell_outside >= float(acceptance["development_minimum_selected_minus_shell_mean_outside_board_edge_f1"]),
        "minimum_positions_with_material_outside_improvement": dev_material >= int(acceptance["development_minimum_positions_with_outside_gain_at_least_0p01"]),
        "bounded_board_regression": dev_selected_board - dev_shell_board >= float(acceptance["minimum_selected_minus_shell_mean_board_plus_margin_edge_f1"]),
        "bounded_full_frame_regression": dev_selected_linear - dev_shell_linear >= float(acceptance["minimum_selected_minus_shell_mean_full_frame_linear_similarity"]),
    }
    development_passed = all(development_gates.values())
    development_montage_rows: list[np.ndarray] = []
    for position in development_positions:
        prepared = prepared_development[position]
        shell_image = cv2.imread(str(REPO_ROOT / shell_by_position[position]["image"]["path"]), cv2.IMREAD_COLOR)
        selected_image = candidate_frames[(selected_x, position)]
        _write_png(output_directory / f"{prepared['episode']['recording_id']}-selected.png", selected_image)
        development_montage_rows.append(np.concatenate([prepared["physical"], shell_image, selected_image], axis=1))
    development_montage = _write_png(output_directory / "development_physical_shell_selected.png", np.concatenate(development_montage_rows, axis=0))

    validation_rows: list[dict[str, Any]] = []
    validation_gates: dict[str, bool] | None = None
    validation_montage: dict[str, str] | None = None
    if development_passed:
        validation_montage_rows: list[np.ndarray] = []
        for position in [int(value) for value in contract["split"]["validation_positions"]]:
            prepared = prepare_episode(position)
            frame, metrics = render(prepared, selected_x)
            shell = shell_by_position[position]
            validation_rows.append({"split_position": position, "recording_id": prepared["episode"]["recording_id"], "selected": metrics, "shell": shell, "outside_board_edge_f1_delta": float(metrics["outside_board"]["f1"] - shell["outside_board"]["f1"]), "board_plus_margin_edge_f1_delta": float(metrics["board_plus_margin"]["f1"] - shell["board_plus_margin"]["f1"]), "full_frame_linear_similarity_delta": float(metrics["whole_frame"]["full_frame_linear_pixel_similarity"] - shell["whole_frame"]["full_frame_linear_pixel_similarity"])})
            shell_image = cv2.imread(str(REPO_ROOT / shell["image"]["path"]), cv2.IMREAD_COLOR)
            _write_png(output_directory / f"{prepared['episode']['recording_id']}-validation-selected.png", frame)
            validation_montage_rows.append(np.concatenate([prepared["physical"], shell_image, frame], axis=1))
        validation_montage = _write_png(output_directory / "validation_physical_shell_selected.png", np.concatenate(validation_montage_rows, axis=0))
        val_shell_outside = _mean(validation_rows, ("shell", "outside_board", "f1"))
        val_selected_outside = _mean(validation_rows, ("selected", "outside_board", "f1"))
        val_shell_board = _mean(validation_rows, ("shell", "board_plus_margin", "f1"))
        val_selected_board = _mean(validation_rows, ("selected", "board_plus_margin", "f1"))
        val_shell_linear = _mean(validation_rows, ("shell", "whole_frame", "full_frame_linear_pixel_similarity"))
        val_selected_linear = _mean(validation_rows, ("selected", "whole_frame", "full_frame_linear_pixel_similarity"))
        val_material = sum(row["outside_board_edge_f1_delta"] >= 0.01 for row in validation_rows)
        validation_gates = {
            "minimum_selected_mean_outside_board_edge_f1": val_selected_outside >= float(acceptance["validation_minimum_selected_mean_outside_board_edge_f1"]),
            "minimum_selected_minus_shell_mean_outside_board_edge_f1": val_selected_outside - val_shell_outside >= float(acceptance["validation_minimum_selected_minus_shell_mean_outside_board_edge_f1"]),
            "minimum_positions_with_material_outside_improvement": val_material >= int(acceptance["validation_minimum_positions_with_outside_gain_at_least_0p01"]),
            "bounded_board_regression": val_selected_board - val_shell_board >= float(acceptance["minimum_selected_minus_shell_mean_board_plus_margin_edge_f1"]),
            "bounded_full_frame_regression": val_selected_linear - val_shell_linear >= float(acceptance["minimum_selected_minus_shell_mean_full_frame_linear_similarity"]),
        }
    validation_passed = validation_gates is not None and all(validation_gates.values())
    integrity_gates = {
        "exact_development_position_count": len(development_positions) == int(contract["gates"]["expected_development_position_count"]),
        "exact_candidate_count": len(candidate_rows) == int(contract["gates"]["expected_candidate_count"]),
        "exact_development_render_count": len(development_positions) * len(candidate_rows) == int(contract["resource_boundary"]["exact_full_mesh_development_candidate_renders_allowed"]),
        "exact_candidate_triangle_count": all(row["selected"]["render"]["triangle_count"] == int(contract["gates"]["expected_candidate_triangle_count"]) for candidate in candidate_rows for row in candidate["rows"]),
        "manifest_unique_assets_read_once": len(asset_receipts) == int(contract["gates"]["expected_unique_mesh_asset_reads"]),
        "one_global_value_selected": True,
        "validation_not_used_for_selection": True,
        "validation_render_condition_respected": bool(validation_rows) == development_passed,
        "no_pixel_composite_flexible_mesh_replay_physics_hardware_or_paid_compute": True,
        "post_final_calibration_not_promotion": True,
    }
    if validation_passed and all(integrity_gates.values()):
        status = "PASS_BOUNDED_RENDERER_NATIVE_ENCLOSURE_PLANE_VALIDATED"
        reviewer_decision = "FREEZE_ENCLOSURE_PLANE_FULL_TIMELINE"
        next_transition = "freeze_or101_enclosure_plane_full_timeline"
    elif not development_passed:
        status = "TERMINAL_BOUNDED_RENDERER_NATIVE_ENCLOSURE_PLANE_DEVELOPMENT_GATE_FAILED"
        reviewer_decision = "REJECT_ENCLOSURE_PLANE_AND_PIVOT_TO_ROBOT_ARTICULATION_SCALE"
        next_transition = "freeze_or101_robot_articulation_scale_residual_successor"
    else:
        status = "TERMINAL_BOUNDED_RENDERER_NATIVE_ENCLOSURE_PLANE_VALIDATION_GATE_FAILED"
        reviewer_decision = "REJECT_ENCLOSURE_PLANE_AND_PIVOT_TO_ROBOT_ARTICULATION_SCALE"
        next_transition = "freeze_or101_robot_articulation_scale_residual_successor"
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_bounded_renderer_native_enclosure_plane_fit_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "candidate_summaries": [{key: value for key, value in candidate.items() if key != "rows"} for candidate in candidate_rows],
        "selected_local_x_m": selected_x,
        "development_rows": development_rows,
        "development_summary": {"shell_mean_outside_board_edge_f1": dev_shell_outside, "selected_mean_outside_board_edge_f1": dev_selected_outside, "outside_board_edge_f1_delta": dev_selected_outside - dev_shell_outside, "positions_with_outside_delta_at_least_0p01": dev_material, "board_plus_margin_edge_f1_delta": dev_selected_board - dev_shell_board, "full_frame_linear_similarity_delta": dev_selected_linear - dev_shell_linear},
        "development_montage": {**development_montage, "layout": "physical_left_shell_middle_selected_right"},
        "validation_rows": validation_rows,
        "validation_summary": None if not validation_rows else {"shell_mean_outside_board_edge_f1": _mean(validation_rows, ("shell", "outside_board", "f1")), "selected_mean_outside_board_edge_f1": _mean(validation_rows, ("selected", "outside_board", "f1")), "outside_board_edge_f1_delta": _mean(validation_rows, ("outside_board_edge_f1_delta",)), "positions_with_outside_delta_at_least_0p01": sum(row["outside_board_edge_f1_delta"] >= 0.01 for row in validation_rows), "board_plus_margin_edge_f1_delta": _mean(validation_rows, ("board_plus_margin_edge_f1_delta",)), "full_frame_linear_similarity_delta": _mean(validation_rows, ("full_frame_linear_similarity_delta",))},
        "validation_montage": None if validation_montage is None else {**validation_montage, "layout": "physical_left_shell_middle_selected_right"},
        "gates": {"integrity": integrity_gates, "development": development_gates, "validation": validation_gates},
        "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "execution": {"already_open_physical_video_decodes": len(development_positions) + len(validation_rows), "physical_initial_frames_read": len(development_positions) + len(validation_rows), "exact_full_mesh_development_candidate_renders": len(development_positions) * len(candidate_rows), "exact_full_mesh_validation_selected_renders": len(validation_rows), "mesh_asset_reads": len(asset_receipts), "fits": 1, "candidate_family_searches": 1, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": reviewer_decision,
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
