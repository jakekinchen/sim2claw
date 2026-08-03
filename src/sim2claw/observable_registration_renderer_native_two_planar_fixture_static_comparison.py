"""Compare the frozen complete and clipped planar fixtures in one native z-buffer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_scene_composition_residual_attribution import _masked_tolerant_edge_f1
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _prepare_full_mesh_stream, _region_masks
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_native_rasterizer_byte_equivalence import _compile_native, _native_rasterize
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import (
    _episode_inventory,
    load_post_final_independent_robot_base_full_corpus_diagnostic_contract,
)
from .observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import (
    _primitive_triangle_stream,
    load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract,
)
from .observable_registration_post_final_two_material_finite_object_full_timeline_propagation import (
    load_post_final_two_material_finite_object_full_timeline_propagation_contract,
)
from .observable_registration_renderer_native_planar_fixture_static_comparison import _fixture_stream
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache
from .observable_registration_temporal_pixel_similarity import _linear_similarity


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_renderer_native_two_planar_fixture_static_comparison_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_two_planar_fixture_static_comparison_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_two_planar_fixture_static_comparison_v1"


def load_two_planar_fixture_static_comparison_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR130 contract")
    for group in ("sources", "frozen_identities"):
        for name, binding in contract[group].items():
            if name == "mesh_asset_root":
                continue
            source_path = binding.get("path")
            expected = binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR130 identity mismatch: {source_path}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["corroboration_positions"] != list(range(8, 12)):
        raise ValueError("OR130 split drifted")
    if split["corroboration_requires_development_pass"] is not True or split["corroboration_refit_allowed"] is not False:
        raise ValueError("OR130 corroboration boundary drifted")
    fixture = contract["fixture"]
    if fixture["fixture_count"] != 2 or fixture["triangle_count_per_fixture"] != 128 or fixture["total_fixture_triangle_count"] != 256:
        raise ValueError("OR130 fixture count drifted")
    if fixture["shared_zbuffer"] is not True or fixture["physical_pixel_texture_projection"] is not False or fixture["screen_space_overlay"] is not False:
        raise ValueError("OR130 renderer-native boundary drifted")
    resources = contract["resource_boundary"]
    zero = (
        "physical_pixel_texture_projections_allowed",
        "screen_space_overlays_allowed",
        "fits_or_candidate_selections_allowed",
        "threshold_changes_allowed",
        "retries_allowed",
        "simulator_replays_allowed",
        "hardware_actions_allowed",
    )
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR130 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR130 authority must remain closed")
    return contract


def _mask_for_corners(corners: list[list[float]], dilation_kernel_px: int) -> np.ndarray:
    mask = np.zeros((240, 320), dtype=np.uint8)
    cv2.fillConvexPoly(mask, np.rint(np.asarray(corners, dtype=np.float64)).astype(np.int32), 1)
    return cv2.dilate(mask, np.ones((dilation_kernel_px, dilation_kernel_px), dtype=np.uint8)) > 0


def _edge(frame: np.ndarray, candidate: np.ndarray, mask: np.ndarray, edge: dict[str, Any]) -> float:
    return float(
        _masked_tolerant_edge_f1(
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
            cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY),
            mask,
            edge,
        )["f1"]
    )


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    return float(np.mean([float(row[key]) for row in rows]))


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR130 one-run receipt already exists")
    contract = load_two_planar_fixture_static_comparison_contract(contract_path)
    or127 = json.loads((REPO_ROOT / contract["sources"]["or127_receipt"]["path"]).read_text())
    or129 = json.loads((REPO_ROOT / contract["sources"]["or129_receipt"]["path"]).read_text())
    complete_parameters = json.loads((REPO_ROOT / contract["sources"]["or126_parameters"]["path"]).read_text())
    clipped_parameters = json.loads((REPO_ROOT / contract["sources"]["or129_parameters"]["path"]).read_text())
    if or127["artifact_sha256"] != contract["sources"]["or127_receipt"]["artifact_sha256"]:
        raise ValueError("OR130 OR127 prerequisite drifted")
    if or129["artifact_sha256"] != contract["sources"]["or129_receipt"]["artifact_sha256"]:
        raise ValueError("OR130 OR129 prerequisite drifted")
    if complete_parameters["artifact_sha256"] != contract["sources"]["or126_parameters"]["artifact_sha256"]:
        raise ValueError("OR130 complete-fixture parameters drifted")
    if clipped_parameters["artifact_sha256"] != contract["sources"]["or129_parameters"]["artifact_sha256"]:
        raise ValueError("OR130 clipped-fixture parameters drifted")

    or119_contract = load_post_final_two_material_finite_object_full_timeline_propagation_contract(
        REPO_ROOT / contract["sources"]["or119_contract"]["path"]
    )
    or116_contract = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(
        REPO_ROOT / or119_contract["sources"]["or116_contract"]["path"]
    )
    or95 = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(
        REPO_ROOT / or119_contract["sources"]["or95_contract"]["path"]
    )
    or118 = json.loads((REPO_ROOT / or119_contract["sources"]["or118_receipt"]["path"]).read_text())
    prior_rows = json.loads((REPO_ROOT / contract["sources"]["or119_frame_rows"]["path"]).read_text())["rows"]
    prior_initial = {int(row["split_position"]): row for row in prior_rows if int(row["evaluation_index"]) == 0}
    or127_rows = {int(row["split_position"]): row for row in or127["rows"]}
    scene = json.loads((REPO_ROOT / or119_contract["sources"]["shared_scene_manifest"]["path"]).read_text())
    frozen = or95["frozen_candidate"]
    camera = frozen["camera"]
    response = frozen["global_monotone_response"]
    renderer = or119_contract["renderer"]
    static = frozen["static_workcell_transform"]
    static_family = {
        "anchor_body_id": int(static["anchor_body_id"]),
        "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]],
    }
    static_vector = np.asarray(static["vector"], dtype=np.float64)
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(
        frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"], dtype=np.float64
    )
    shape = or118["frozen_shape"]
    shaft = np.asarray(or119_contract["frozen_object"]["shaft_pre_response_bgr"], dtype=np.uint8)
    terminal = np.asarray(or119_contract["frozen_object"]["terminal_pre_response_bgr"], dtype=np.uint8)
    object_colors = np.concatenate([np.tile(shaft, (248, 1)), np.tile(terminal, (100, 1))], axis=0)
    episodes = _episode_inventory(or95)
    by_position = {int(row["split_position"]): row for row in episodes}
    _, outside_mask = _region_masks(
        np.asarray(or119_contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=320,
        height=240,
        dilation_kernel_px=int(or119_contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    mask_kernel = int(contract["regions"]["fixture_mask_dilation_kernel_px"])
    complete_mask = _mask_for_corners(complete_parameters["development_median_corners_px"], mask_kernel)
    clipped_mask = _mask_for_corners(clipped_parameters["development_fitted_corners_px"], mask_kernel)
    edge = or119_contract["metric"]["edge"]

    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / or119_contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native(
        {"sources": {"native_source": or119_contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}},
        output_directory,
    )
    complete_pixels, complete_depths, complete_colors = _fixture_stream(complete_parameters, camera, contract, response)
    clipped_pixels, clipped_depths, clipped_colors = _fixture_stream(clipped_parameters, camera, contract, response)
    rows: list[dict[str, Any]] = []
    panels: list[np.ndarray] = []
    triangle_counts: list[dict[str, int]] = []

    def evaluate_positions(positions: list[int], split_name: str) -> None:
        for position in positions:
            episode = by_position[position]
            video = episode["physical_video"]
            video_path = REPO_ROOT / video["path"]
            if sha256_file(video_path) != video["sha256"]:
                raise ValueError("OR130 physical video identity drifted")
            physical = cv2.flip(
                _decode_selected_frames(
                    video_path,
                    selected_indices=np.asarray([0], dtype=np.int64),
                    expected_frame_count=int(video["frame_count"]),
                    expected_width=int(video["width_px"]),
                    expected_height=int(video["height_px"]),
                    output_width=320,
                    output_height=240,
                )[0],
                -1,
            )
            trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
            one = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
            registered = _independently_registered_trace(
                one,
                anchor_body_id=int(static["anchor_body_id"]),
                left_body_ids=left_ids,
                right_body_ids=right_ids,
                vector=robot_vector,
            )
            pixels, depths, colors, _ = _prepare_full_mesh_stream(
                scene, registered, meshes, camera, renderer, static_family, static_vector
            )
            object_pixels, object_depths, _, _ = _primitive_triangle_stream(
                shape,
                registered,
                scene,
                camera,
                renderer,
                static_family,
                static_vector,
                or116_contract["support_plane"],
                np.asarray([0, 0, 0], dtype=np.uint8),
            )
            baseline_pixels = np.ascontiguousarray(np.concatenate([pixels, object_pixels]))
            baseline_depths = np.ascontiguousarray(np.concatenate([depths, object_depths]))
            baseline_colors = np.ascontiguousarray(np.concatenate([colors, object_colors]))
            complete_stream_pixels = np.ascontiguousarray(np.concatenate([baseline_pixels, complete_pixels]))
            complete_stream_depths = np.ascontiguousarray(np.concatenate([baseline_depths, complete_depths]))
            complete_stream_colors = np.ascontiguousarray(np.concatenate([baseline_colors, complete_colors]))
            two_stream_pixels = np.ascontiguousarray(np.concatenate([complete_stream_pixels, clipped_pixels]))
            two_stream_depths = np.ascontiguousarray(np.concatenate([complete_stream_depths, clipped_depths]))
            two_stream_colors = np.ascontiguousarray(np.concatenate([complete_stream_colors, clipped_colors]))
            raw_frames = [
                _native_rasterize(library_path, baseline_pixels, baseline_depths, baseline_colors, renderer)[0],
                _native_rasterize(library_path, complete_stream_pixels, complete_stream_depths, complete_stream_colors, renderer)[0],
                _native_rasterize(library_path, two_stream_pixels, two_stream_depths, two_stream_colors, renderer)[0],
            ]
            baseline, complete, candidate = [
                apply_monotone_response(
                    raw,
                    bias=float(response["bias"]),
                    low_slope=float(response["low_intensity_slope"]),
                    high_slope=float(response["high_intensity_slope"]),
                    knot=int(response["fixed_input_knot"]),
                )
                for raw in raw_frames
            ]
            metrics = {
                "baseline_full_similarity": _linear_similarity(physical, baseline),
                "complete_full_similarity": _linear_similarity(physical, complete),
                "candidate_full_similarity": _linear_similarity(physical, candidate),
                "baseline_clipped_similarity": _linear_similarity(physical, baseline, clipped_mask),
                "complete_clipped_similarity": _linear_similarity(physical, complete, clipped_mask),
                "candidate_clipped_similarity": _linear_similarity(physical, candidate, clipped_mask),
                "baseline_clipped_edge_f1": _edge(physical, baseline, clipped_mask, edge),
                "complete_clipped_edge_f1": _edge(physical, complete, clipped_mask, edge),
                "candidate_clipped_edge_f1": _edge(physical, candidate, clipped_mask, edge),
                "complete_fixture_edge_f1": _edge(physical, complete, complete_mask, edge),
                "candidate_complete_fixture_edge_f1": _edge(physical, candidate, complete_mask, edge),
                "complete_outside_edge_f1": _edge(physical, complete, outside_mask, edge),
                "candidate_outside_edge_f1": _edge(physical, candidate, outside_mask, edge),
            }
            prior = prior_initial[position]
            prior_complete = or127_rows[position]
            row: dict[str, Any] = {
                "split": split_name,
                "split_position": position,
                "recording_id": episode["recording_id"],
                **metrics,
                "full_similarity_delta_vs_complete": metrics["candidate_full_similarity"] - metrics["complete_full_similarity"],
                "clipped_similarity_delta_vs_complete": metrics["candidate_clipped_similarity"] - metrics["complete_clipped_similarity"],
                "clipped_edge_f1_delta_vs_complete": metrics["candidate_clipped_edge_f1"] - metrics["complete_clipped_edge_f1"],
                "outside_edge_f1_delta_vs_complete": metrics["candidate_outside_edge_f1"] - metrics["complete_outside_edge_f1"],
                "complete_fixture_edge_f1_delta": metrics["candidate_complete_fixture_edge_f1"] - metrics["complete_fixture_edge_f1"],
                "baseline_full_error_vs_or119": metrics["baseline_full_similarity"] - float(prior["full_frame_linear_pixel_similarity"]),
                "baseline_outside_edge_error_vs_or119": _edge(physical, baseline, outside_mask, edge) - float(prior["outside_board_edge_f1"]),
                "complete_full_error_vs_or127": metrics["complete_full_similarity"] - float(prior_complete["candidate_full_similarity"]),
                "complete_outside_edge_error_vs_or127": metrics["complete_outside_edge_f1"] - float(prior_complete["candidate_outside_edge_f1"]),
            }
            rows.append(row)
            triangle_counts.append({"baseline": len(baseline_pixels), "complete": len(complete_stream_pixels), "candidate": len(two_stream_pixels)})
            panels.append(np.concatenate([physical, baseline, complete, candidate], axis=1))

    evaluate_positions(contract["split"]["development_positions"], "development")
    development = [row for row in rows if row["split"] == "development"]
    gates = contract["gates"]
    development_passed = (
        _mean(development, "clipped_edge_f1_delta_vs_complete") >= float(gates["minimum_development_mean_clipped_edge_f1_delta"])
        and _mean(development, "clipped_similarity_delta_vs_complete") >= float(gates["minimum_development_mean_clipped_similarity_delta"])
        and _mean(development, "full_similarity_delta_vs_complete") >= float(gates["minimum_development_mean_full_similarity_delta"])
        and _mean(development, "outside_edge_f1_delta_vs_complete") >= float(gates["minimum_development_mean_outside_edge_f1_delta"])
        and min(float(row["clipped_edge_f1_delta_vs_complete"]) for row in development) >= float(gates["minimum_each_development_clipped_edge_f1_delta"])
        and min(float(row["complete_fixture_edge_f1_delta"]) for row in development) >= -float(gates["maximum_each_complete_fixture_edge_f1_regression"])
    )
    if development_passed:
        evaluate_positions(contract["split"]["corroboration_positions"], "corroboration")
    corroboration = [row for row in rows if row["split"] == "corroboration"]
    corroboration_passed = bool(corroboration) and (
        _mean(corroboration, "clipped_edge_f1_delta_vs_complete") >= float(gates["minimum_corroboration_mean_clipped_edge_f1_delta"])
        and _mean(corroboration, "full_similarity_delta_vs_complete") >= float(gates["minimum_corroboration_mean_full_similarity_delta"])
        and _mean(corroboration, "outside_edge_f1_delta_vs_complete") >= float(gates["minimum_corroboration_mean_outside_edge_f1_delta"])
    )
    maximum_reference_error = max(
        max(
            abs(float(row["baseline_full_error_vs_or119"])),
            abs(float(row["baseline_outside_edge_error_vs_or119"])),
            abs(float(row["complete_full_error_vs_or127"])),
            abs(float(row["complete_outside_edge_error_vs_or127"])),
        )
        for row in rows
    )
    integrity = {
        "baseline_and_complete_reproduce_predecessors": maximum_reference_error <= float(gates["maximum_reference_metric_error"]),
        "expected_unique_mesh_asset_reads": len(asset_receipts) == 18,
        "triangle_counts_exact": all(
            row == {"baseline": 825292, "complete": 825420, "candidate": 825548} for row in triangle_counts
        ),
        "corroboration_condition_respected": (len(corroboration) == 4) == development_passed,
        "two_procedural_fixtures_share_native_zbuffer": True,
        "zero_texture_overlay_fit_selection_threshold_change_retry_replay_hardware_or_paid_compute": True,
    }
    passed = development_passed and corroboration_passed and all(integrity.values())
    montage = np.concatenate([cv2.resize(panel, (640, 120), interpolation=cv2.INTER_AREA) for panel in panels], axis=0)
    montage_path = output_directory / "two-planar-fixture-static-comparison.png"
    ok, encoded = cv2.imencode(".png", montage, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR130 montage encoding failed")
    montage_path.write_bytes(encoded.tobytes())
    summary_keys = (
        "baseline_full_similarity",
        "complete_full_similarity",
        "candidate_full_similarity",
        "full_similarity_delta_vs_complete",
        "clipped_similarity_delta_vs_complete",
        "clipped_edge_f1_delta_vs_complete",
        "outside_edge_f1_delta_vs_complete",
        "complete_fixture_edge_f1_delta",
    )
    summary = {key: _mean(rows, key) for key in summary_keys}
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_renderer_native_two_planar_fixture_static_comparison_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_RENDERER_NATIVE_TWO_PLANAR_FIXTURE_STATIC_COMPARISON" if passed else "TERMINAL_RENDERER_NATIVE_TWO_PLANAR_FIXTURE_STATIC_GATES_FAILED",
        "proof_class": contract["proof_class"],
        "identities": {"contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "implementation": contract["frozen_identities"]["implementation"], "test": contract["frozen_identities"]["test"]},
        "rows": rows,
        "summary": summary,
        "development_passed": development_passed,
        "corroboration_passed": corroboration_passed,
        "integrity_gates": integrity,
        "audit": {"path": str(montage_path.relative_to(REPO_ROOT)), "sha256": sha256_file(montage_path), "layout": "rows_are_physical_baseline_complete_fixture_two_fixtures"},
        "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "execution": {"physical_video_decodes": len(rows), "physical_frame_reads": len(rows), "baseline_renders": len(rows), "complete_fixture_renders": len(rows), "two_fixture_renders": len(rows), "complete_fixture_triangles": 128, "clipped_fixture_triangles": 128, "physical_pixel_texture_projections": 0, "screen_space_overlays": 0, "fits_or_candidate_selections": 0, "threshold_changes": 0, "retries": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_TWO_PLANAR_FIXTURE_FULL_TIMELINE_PROPAGATION" if passed else "STOP_TWO_PLANAR_FIXTURE_STATIC_GATES_FAILED",
        "next_transition": "freeze_or131_two_planar_fixture_full_timeline_propagation" if passed else "stop_or130_two_planar_fixture_static_gates_failed",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
