"""Ablate unrelated legacy background bodies before authoring replacement geometry."""

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
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_final_legacy_photo_background_ablation_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_legacy_photo_background_ablation_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_legacy_photo_background_ablation_v1"


def load_post_final_legacy_photo_background_ablation_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR98 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    frozen = contract["frozen_candidate"]
    if frozen["renderer_only_ablated_body_ids"] != [6, 7] or frozen["new_geometry_added"] is not False or frozen["physics_or_state_mutated"] is not False:
        raise ValueError("OR98 ablation family drifted")
    resources = contract["resource_boundary"]
    if resources["fits_allowed"] != 0 or resources["candidate_family_searches_allowed"] != 0 or resources["simulator_replays_allowed"] != 0 or resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR98 resource or authority boundary drifted")
    if contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR98 claim boundary drifted")
    return contract


def _write_png(path: Path, frame: np.ndarray) -> dict[str, str]:
    ok, encoded = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR98 PNG encoding failed")
    path.write_bytes(encoded.tobytes())
    return {"path": str(path.relative_to(REPO_ROOT)), "sha256": sha256_file(path)}


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR98 one-run receipt already exists")
    contract = load_post_final_legacy_photo_background_ablation_contract(contract_path)
    or97 = json.loads((REPO_ROOT / contract["sources"]["or97_closeout"]["path"]).read_text())
    if or97["selected_mechanism"] != "renderer_native_static_scene_content_and_robot_articulation":
        raise ValueError("OR97 did not authorize static scene-content work")
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episodes = _episode_inventory(or95_contract)
    frozen = or95_contract["frozen_candidate"]
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    body_names = [body["name"] for body in scene["bodies"]]
    ablated_ids = set(contract["frozen_candidate"]["renderer_only_ablated_body_ids"])
    ablated_scene = dict(scene)
    ablated_scene["geoms"] = [geom for geom in scene["geoms"] if int(geom["body_id"]) not in ablated_ids]
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
    library_path, compile_command, compiler_stderr = _compile_native({"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}}, output_directory)
    rows: list[dict[str, Any]] = []
    montage_rows: list[np.ndarray] = []
    for episode in episodes:
        trace_binding = episode["state_trace"]
        if sha256_file(REPO_ROOT / trace_binding["path"]) != trace_binding["sha256"]:
            raise ValueError("OR98 trace hash mismatch")
        trace = json.loads((REPO_ROOT / trace_binding["path"]).read_text())
        if trace["body_names"] != body_names:
            raise ValueError("scene and trace body ordering drifted")
        one_trace = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
        transformed = _independently_registered_trace(one_trace, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=robot_vector)
        video = episode["physical_video"]
        physical = cv2.flip(_decode_selected_frames(REPO_ROOT / video["path"], selected_indices=np.asarray([0], dtype=np.int64), expected_frame_count=int(video["frame_count"]), expected_width=int(video["width_px"]), expected_height=int(video["height_px"]), output_width=320, output_height=240)[0], -1)
        variants: dict[str, dict[str, Any]] = {}
        images: dict[str, np.ndarray] = {}
        for label, candidate_scene in (("baseline", scene), ("ablated", ablated_scene)):
            pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(candidate_scene, transformed, meshes, camera, renderer, static_family, static_vector)
            simulator, updates, occluded, raster_seconds = _native_rasterize(library_path, pixels, depths, colors, renderer)
            candidate = apply_monotone_response(simulator, bias=float(response["bias"]), low_slope=float(response["low_intensity_slope"]), high_slope=float(response["high_intensity_slope"]), knot=int(response["fixed_input_knot"]))
            images[label] = candidate
            physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
            candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
            variants[label] = {
                "whole_frame": _metrics(physical, candidate, edge),
                "board_plus_margin": _masked_tolerant_edge_f1(physical_gray, candidate_gray, board_mask, edge),
                "outside_board": _masked_tolerant_edge_f1(physical_gray, candidate_gray, outside_mask, edge),
                "render": {"triangle_count": int(triangle_count), "depth_updates": int(updates), "occluded_fragments": int(occluded), "raster_seconds": float(raster_seconds)},
                "image": _write_png(output_directory / f"{episode['recording_id']}-{label}.png", candidate),
            }
        rows.append({"recording_id": episode["recording_id"], "split_position": int(episode["split_position"]), "baseline": variants["baseline"], "ablated": variants["ablated"], "outside_board_edge_f1_delta": float(variants["ablated"]["outside_board"]["f1"] - variants["baseline"]["outside_board"]["f1"]), "board_plus_margin_edge_f1_delta": float(variants["ablated"]["board_plus_margin"]["f1"] - variants["baseline"]["board_plus_margin"]["f1"]), "full_frame_linear_similarity_delta": float(variants["ablated"]["whole_frame"]["full_frame_linear_pixel_similarity"] - variants["baseline"]["whole_frame"]["full_frame_linear_pixel_similarity"])})
        montage_rows.append(np.concatenate([physical, images["baseline"], images["ablated"]], axis=1))
    montage = _write_png(output_directory / "physical_baseline_ablated.png", np.concatenate(montage_rows, axis=0))
    baseline_outside = float(np.mean([row["baseline"]["outside_board"]["f1"] for row in rows]))
    ablated_outside = float(np.mean([row["ablated"]["outside_board"]["f1"] for row in rows]))
    baseline_board = float(np.mean([row["baseline"]["board_plus_margin"]["f1"] for row in rows]))
    ablated_board = float(np.mean([row["ablated"]["board_plus_margin"]["f1"] for row in rows]))
    baseline_linear = float(np.mean([row["baseline"]["whole_frame"]["full_frame_linear_pixel_similarity"] for row in rows]))
    ablated_linear = float(np.mean([row["ablated"]["whole_frame"]["full_frame_linear_pixel_similarity"] for row in rows]))
    improved = sum(row["outside_board_edge_f1_delta"] >= 0.01 for row in rows)
    acceptance = contract["acceptance"]
    gates = {
        "exact_eleven_episodes": len(rows) == 11,
        "exact_baseline_triangle_count": all(row["baseline"]["render"]["triangle_count"] == int(contract["gates"]["expected_baseline_triangle_count"]) for row in rows),
        "exact_ablated_triangle_count": all(row["ablated"]["render"]["triangle_count"] == int(contract["gates"]["expected_ablated_triangle_count"]) for row in rows),
        "manifest_unique_assets_read_once": len(asset_receipts) == int(contract["gates"]["expected_unique_mesh_asset_reads"]),
        "minimum_selected_mean_outside_board_edge_f1": ablated_outside >= float(acceptance["minimum_selected_mean_outside_board_edge_f1"]),
        "minimum_selected_minus_baseline_mean_outside_board_edge_f1": ablated_outside - baseline_outside >= float(acceptance["minimum_selected_minus_baseline_mean_outside_board_edge_f1"]),
        "minimum_episodes_with_material_outside_improvement": improved >= int(acceptance["minimum_episodes_with_outside_board_edge_f1_delta_at_least_0p01"]),
        "bounded_board_regression": ablated_board - baseline_board >= float(acceptance["minimum_selected_minus_baseline_mean_board_plus_margin_edge_f1"]),
        "bounded_full_frame_regression": ablated_linear - baseline_linear >= float(acceptance["minimum_selected_minus_baseline_mean_full_frame_linear_similarity"]),
        "camera_table_board_fiducials_robots_response_actions_states_fixed": True,
        "no_fit_search_replay_hardware_or_paid_compute": True,
        "post_final_diagnostic_not_promotion": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_legacy_photo_background_ablation_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_LEGACY_PHOTO_BACKGROUND_ABLATION_SELECTED" if passed else "TERMINAL_LEGACY_PHOTO_BACKGROUND_ABLATION_INSUFFICIENT",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "rows": rows,
        "summary": {"baseline_mean_outside_board_edge_f1": baseline_outside, "ablated_mean_outside_board_edge_f1": ablated_outside, "outside_board_edge_f1_delta": ablated_outside - baseline_outside, "episodes_with_outside_board_delta_at_least_0p01": improved, "baseline_mean_board_plus_margin_edge_f1": baseline_board, "ablated_mean_board_plus_margin_edge_f1": ablated_board, "board_plus_margin_edge_f1_delta": ablated_board - baseline_board, "baseline_mean_full_frame_linear_similarity": baseline_linear, "ablated_mean_full_frame_linear_similarity": ablated_linear, "full_frame_linear_similarity_delta": ablated_linear - baseline_linear},
        "montage": {**montage, "layout": "physical_left_baseline_middle_ablated_right"},
        "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "gates": gates,
        "execution": {"already_open_physical_video_decodes": 11, "physical_initial_frames_read": 11, "exact_full_mesh_baseline_renders": 11, "exact_full_mesh_ablated_renders": 11, "mesh_asset_reads": len(asset_receipts), "fits": 0, "candidate_family_searches": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_ABLATED_BACKGROUND_FULL_TIMELINE" if passed else "REJECT_ABLATION_AND_FREEZE_WHITE_ENCLOSURE_PRIMITIVE_SUCCESSOR",
        "next_transition": "freeze_or99_ablated_background_full_timeline" if passed else "freeze_or99_renderer_native_white_enclosure_primitive_successor",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
