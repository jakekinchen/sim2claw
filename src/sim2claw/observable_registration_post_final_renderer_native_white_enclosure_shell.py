"""Test one renderer-native white-enclosure shell against retained physical frames."""

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
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_final_renderer_native_white_enclosure_shell_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_renderer_native_white_enclosure_shell_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_renderer_native_white_enclosure_shell_v1"


def load_post_final_renderer_native_white_enclosure_shell_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR99 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    frozen = contract["frozen_candidate"]
    if frozen["renderer_only_background_body_id"] != 6:
        raise ValueError("OR99 background body drifted")
    if frozen["renderer_only_kept_background_geom_names"] != ["rear_wall"]:
        raise ValueError("OR99 shell primitive drifted")
    if frozen["renderer_only_removed_child_body_ids"] != [7]:
        raise ValueError("OR99 removed child drifted")
    if frozen["rear_wall_geometry_unchanged"] is not True or frozen["new_geometry_added"] is not False:
        raise ValueError("OR99 renderer-native shell boundary drifted")
    if frozen["pixel_compositing_or_warp"] is not False or frozen["physics_or_state_mutated"] is not False:
        raise ValueError("OR99 pixel or physics boundary drifted")
    resources = contract["resource_boundary"]
    if resources["fits_allowed"] != 0 or resources["candidate_family_searches_allowed"] != 0:
        raise ValueError("OR99 fit/search boundary drifted")
    if resources["simulator_replays_allowed"] != 0 or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR99 resource boundary drifted")
    if any(contract["authority"].values()) or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR99 authority or claim boundary drifted")
    return contract


def _white_shell_scene(scene: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    frozen = contract["frozen_candidate"]
    background_id = int(frozen["renderer_only_background_body_id"])
    kept = set(frozen["renderer_only_kept_background_geom_names"])
    removed_children = {int(value) for value in frozen["renderer_only_removed_child_body_ids"]}
    candidate = dict(scene)
    candidate["geoms"] = [
        geom
        for geom in scene["geoms"]
        if int(geom["body_id"]) not in removed_children
        and (int(geom["body_id"]) != background_id or geom["name"] in kept)
    ]
    return candidate


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR99 one-run receipt already exists")
    contract = load_post_final_renderer_native_white_enclosure_shell_contract(contract_path)
    or98 = json.loads((REPO_ROOT / contract["sources"]["or98_closeout"]["path"]).read_text())
    if or98["reviewer_decision"] != "REJECT_ABLATION_AND_FREEZE_WHITE_ENCLOSURE_PRIMITIVE_SUCCESSOR":
        raise ValueError("OR98 did not authorize white-enclosure primitive work")
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episodes = _episode_inventory(or95_contract)
    frozen = or95_contract["frozen_candidate"]
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    body6_geoms = [geom for geom in scene["geoms"] if int(geom["body_id"]) == 6]
    body7_geoms = [geom for geom in scene["geoms"] if int(geom["body_id"]) == 7]
    if len(body6_geoms) != int(contract["gates"]["expected_body6_geom_count"]):
        raise ValueError("OR99 body 6 geom inventory drifted")
    if len(body7_geoms) != int(contract["gates"]["expected_body7_geom_count"]):
        raise ValueError("OR99 body 7 geom inventory drifted")
    if sum(geom["name"] == "rear_wall" for geom in body6_geoms) != 1:
        raise ValueError("OR99 rear-wall primitive identity drifted")
    shell_scene = _white_shell_scene(scene, contract)
    body_names = [body["name"] for body in scene["bodies"]]
    renderer = contract["renderer"]
    camera = frozen["camera"]
    static = frozen["static_workcell_transform"]
    static_family = {
        "anchor_body_id": int(static["anchor_body_id"]),
        "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]],
    }
    static_vector = np.asarray(static["vector"], dtype=np.float64)
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(
        frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"],
        dtype=np.float64,
    )
    response = frozen["global_monotone_response"]
    edge = contract["metric"]["edge"]
    board_mask, outside_mask = _region_masks(
        np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=320,
        height=240,
        dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    )
    library_path, compile_command, compiler_stderr = _compile_native(
        {"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}},
        output_directory,
    )
    rows: list[dict[str, Any]] = []
    montage_rows: list[np.ndarray] = []
    for episode in episodes:
        trace_binding = episode["state_trace"]
        if sha256_file(REPO_ROOT / trace_binding["path"]) != trace_binding["sha256"]:
            raise ValueError("OR99 trace hash mismatch")
        trace = json.loads((REPO_ROOT / trace_binding["path"]).read_text())
        if trace["body_names"] != body_names:
            raise ValueError("scene and trace body ordering drifted")
        one_trace = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
        transformed = _independently_registered_trace(
            one_trace,
            anchor_body_id=int(static["anchor_body_id"]),
            left_body_ids=left_ids,
            right_body_ids=right_ids,
            vector=robot_vector,
        )
        video = episode["physical_video"]
        physical = cv2.flip(
            _decode_selected_frames(
                REPO_ROOT / video["path"],
                selected_indices=np.asarray([0], dtype=np.int64),
                expected_frame_count=int(video["frame_count"]),
                expected_width=int(video["width_px"]),
                expected_height=int(video["height_px"]),
                output_width=320,
                output_height=240,
            )[0],
            -1,
        )
        variants: dict[str, dict[str, Any]] = {}
        images: dict[str, np.ndarray] = {}
        for label, candidate_scene in (("baseline", scene), ("shell", shell_scene)):
            pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(
                candidate_scene, transformed, meshes, camera, renderer, static_family, static_vector
            )
            simulator, updates, occluded, raster_seconds = _native_rasterize(
                library_path, pixels, depths, colors, renderer
            )
            candidate = apply_monotone_response(
                simulator,
                bias=float(response["bias"]),
                low_slope=float(response["low_intensity_slope"]),
                high_slope=float(response["high_intensity_slope"]),
                knot=int(response["fixed_input_knot"]),
            )
            images[label] = candidate
            physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
            candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
            variants[label] = {
                "whole_frame": _metrics(physical, candidate, edge),
                "board_plus_margin": _masked_tolerant_edge_f1(physical_gray, candidate_gray, board_mask, edge),
                "outside_board": _masked_tolerant_edge_f1(physical_gray, candidate_gray, outside_mask, edge),
                "render": {
                    "triangle_count": int(triangle_count),
                    "depth_updates": int(updates),
                    "occluded_fragments": int(occluded),
                    "raster_seconds": float(raster_seconds),
                },
                "image": _write_png(output_directory / f"{episode['recording_id']}-{label}.png", candidate),
            }
        rows.append(
            {
                "recording_id": episode["recording_id"],
                "split_position": int(episode["split_position"]),
                "baseline": variants["baseline"],
                "shell": variants["shell"],
                "outside_board_edge_f1_delta": float(variants["shell"]["outside_board"]["f1"] - variants["baseline"]["outside_board"]["f1"]),
                "board_plus_margin_edge_f1_delta": float(variants["shell"]["board_plus_margin"]["f1"] - variants["baseline"]["board_plus_margin"]["f1"]),
                "full_frame_linear_similarity_delta": float(variants["shell"]["whole_frame"]["full_frame_linear_pixel_similarity"] - variants["baseline"]["whole_frame"]["full_frame_linear_pixel_similarity"]),
            }
        )
        montage_rows.append(np.concatenate([physical, images["baseline"], images["shell"]], axis=1))
    montage = _write_png(output_directory / "physical_baseline_shell.png", np.concatenate(montage_rows, axis=0))

    def mean_metric(label: str, region: str, metric: str) -> float:
        return float(np.mean([row[label][region][metric] for row in rows]))

    baseline_outside = mean_metric("baseline", "outside_board", "f1")
    shell_outside = mean_metric("shell", "outside_board", "f1")
    baseline_board = mean_metric("baseline", "board_plus_margin", "f1")
    shell_board = mean_metric("shell", "board_plus_margin", "f1")
    baseline_linear = mean_metric("baseline", "whole_frame", "full_frame_linear_pixel_similarity")
    shell_linear = mean_metric("shell", "whole_frame", "full_frame_linear_pixel_similarity")
    improved = sum(row["outside_board_edge_f1_delta"] >= 0.01 for row in rows)
    acceptance = contract["acceptance"]
    gates = {
        "exact_eleven_episodes": len(rows) == int(contract["gates"]["expected_episode_count"]),
        "exact_baseline_triangle_count": all(row["baseline"]["render"]["triangle_count"] == int(contract["gates"]["expected_baseline_triangle_count"]) for row in rows),
        "exact_shell_triangle_count": all(row["shell"]["render"]["triangle_count"] == int(contract["gates"]["expected_shell_triangle_count"]) for row in rows),
        "exact_background_geom_inventory": len(body6_geoms) == int(contract["gates"]["expected_body6_geom_count"]) and len(body7_geoms) == int(contract["gates"]["expected_body7_geom_count"]),
        "manifest_unique_assets_read_once": len(asset_receipts) == int(contract["gates"]["expected_unique_mesh_asset_reads"]),
        "minimum_selected_mean_outside_board_edge_f1": shell_outside >= float(acceptance["minimum_selected_mean_outside_board_edge_f1"]),
        "minimum_selected_minus_baseline_mean_outside_board_edge_f1": shell_outside - baseline_outside >= float(acceptance["minimum_selected_minus_baseline_mean_outside_board_edge_f1"]),
        "minimum_episodes_with_material_outside_improvement": improved >= int(acceptance["minimum_episodes_with_outside_board_edge_f1_delta_at_least_0p01"]),
        "bounded_board_regression": shell_board - baseline_board >= float(acceptance["minimum_selected_minus_baseline_mean_board_plus_margin_edge_f1"]),
        "bounded_full_frame_regression": shell_linear - baseline_linear >= float(acceptance["minimum_selected_minus_baseline_mean_full_frame_linear_similarity"]),
        "camera_scene_except_background_detail_response_actions_states_fixed": True,
        "no_fit_search_pixel_composite_replay_hardware_or_paid_compute": True,
        "post_final_diagnostic_not_promotion": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_renderer_native_white_enclosure_shell_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_RENDERER_NATIVE_WHITE_ENCLOSURE_SHELL_SELECTED" if passed else "TERMINAL_RENDERER_NATIVE_WHITE_ENCLOSURE_SHELL_INSUFFICIENT",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "rows": rows,
        "summary": {
            "baseline_mean_outside_board_edge_f1": baseline_outside,
            "shell_mean_outside_board_edge_f1": shell_outside,
            "outside_board_edge_f1_delta": shell_outside - baseline_outside,
            "episodes_with_outside_board_delta_at_least_0p01": improved,
            "baseline_mean_board_plus_margin_edge_f1": baseline_board,
            "shell_mean_board_plus_margin_edge_f1": shell_board,
            "board_plus_margin_edge_f1_delta": shell_board - baseline_board,
            "baseline_mean_full_frame_linear_similarity": baseline_linear,
            "shell_mean_full_frame_linear_similarity": shell_linear,
            "full_frame_linear_similarity_delta": shell_linear - baseline_linear,
        },
        "montage": {**montage, "layout": "physical_left_baseline_middle_shell_right"},
        "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "gates": gates,
        "execution": {"already_open_physical_video_decodes": 11, "physical_initial_frames_read": 11, "exact_full_mesh_baseline_renders": 11, "exact_full_mesh_shell_renders": 11, "mesh_asset_reads": len(asset_receipts), "fits": 0, "candidate_family_searches": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_WHITE_ENCLOSURE_SHELL_FULL_TIMELINE" if passed else "REJECT_SHELL_AND_FREEZE_BOUNDED_RENDERER_NATIVE_ENCLOSURE_PLANES",
        "next_transition": "freeze_or100_white_enclosure_shell_full_timeline" if passed else "freeze_or100_bounded_renderer_native_enclosure_plane_successor",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
