"""Fit independent left/right robot-base SE(2) transforms with exact mesh silhouettes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import differential_evolution

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_scene_composition_residual_attribution import (
    _masked_tolerant_edge_f1,
)
from .observable_registration_board_anchored_workcell_se2_static_development_fit import (
    _prepare_full_mesh_stream,
    _region_masks,
)
from .observable_registration_development_initial_shared_3d_camera_fit import _metrics
from .observable_registration_expanded_development_global_monotone_response_fit import (
    apply_monotone_response,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    sha256_file,
)
from .observable_registration_native_rasterizer_byte_equivalence import (
    _compile_native,
    _native_rasterize,
)
from .observable_registration_post_final_shared_robot_base_se2_diagnostic import (
    _robot_registered_trace,
    _write_png,
)
from .observable_registration_static_development_full_mesh_comparison import (
    _load_unique_asset_cache,
)


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic_v1"


def load_post_final_independent_left_right_robot_base_se2_diagnostic_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR94 contract")
    for name, source in contract["sources"].items():
        if name != "mesh_asset_root" and sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    if len(contract["samples"]) != 6:
        raise ValueError("OR94 six-sample boundary drifted")
    family = contract["robot_registration_family"]
    if (
        len(family["parameter_names"]) != 6
        or len(family["bounds"]) != 6
        or family["per_episode_parameters"] != 0
        or family["shared_across_all_six_frames"] is not True
    ):
        raise ValueError("OR94 independent six-parameter family drifted")
    frozen = contract["frozen_candidate"]
    left_ids = set(frozen["baseline_left_robot_transform"]["transformed_body_ids"])
    right_ids = set(frozen["baseline_right_robot_transform"]["transformed_body_ids"])
    static_ids = set(frozen["static_workcell_transform"]["transformed_body_ids"])
    if left_ids != set(range(29, 37)) or right_ids != set(range(37, 45)) or left_ids & right_ids or (left_ids | right_ids) & static_ids:
        raise ValueError("OR94 left/right/static body partition drifted")
    resources = contract["resource_boundary"]
    if (
        resources["new_physical_video_decodes_allowed"] != 0
        or resources["independent_parameter_count_allowed"] != 6
        or resources["analytic_or_bounds_proxy_renders_allowed"] != 0
        or resources["exact_robot_only_mesh_search_candidate_evaluations_allowed"] != 198
        or resources["exact_robot_only_mesh_search_renders_allowed"] != 1200
        or resources["simulator_replays_allowed"] != 0
        or resources["paid_compute_allowed"] is not False
        or any(contract["authority"].values())
    ):
        raise ValueError("OR94 resource or authority boundary drifted")
    if contract["claim_limits"]["same_video_semantic_match"] is not False or contract["claim_limits"]["untouched_cohort_remaining"] is not False:
        raise ValueError("OR94 claim boundary drifted")
    return contract


def _independently_registered_trace(
    trace: dict[str, Any],
    *,
    anchor_body_id: int,
    left_body_ids: list[int],
    right_body_ids: list[int],
    vector: np.ndarray,
) -> dict[str, Any]:
    vector = np.asarray(vector, dtype=np.float64)
    if vector.shape != (6,):
        raise ValueError("OR94 transform requires six parameters")
    left = _robot_registered_trace(
        trace,
        anchor_body_id=anchor_body_id,
        robot_body_ids=left_body_ids,
        vector=vector[:3],
    )
    return _robot_registered_trace(
        left,
        anchor_body_id=anchor_body_id,
        robot_body_ids=right_body_ids,
        vector=vector[3:],
    )


def _mean_region(rows: list[dict[str, float]], key: str) -> float:
    return float(np.mean([float(row[key]) for row in rows]))


def fit_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR94 one-run receipt already exists")
    contract = load_post_final_independent_left_right_robot_base_se2_diagnostic_contract(contract_path)
    or93_closeout = json.loads((REPO_ROOT / contract["sources"]["or93_closeout"]["path"]).read_text())
    if or93_closeout["reviewer_decision"] != "REJECT_SHARED_ROBOT_BASE_AND_FREEZE_INDEPENDENT_LEFT_RIGHT_DIAGNOSTIC":
        raise ValueError("OR93 did not authorize independent robot registration")
    or92_contract = json.loads((REPO_ROOT / contract["sources"]["or92_contract"]["path"]).read_text())
    or91_contract = json.loads((REPO_ROOT / contract["sources"]["or91_contract"]["path"]).read_text())
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or91_frame_rows"]["path"]).read_text())["rows"]
    frame_map = {(row["recording_id"], int(row["evaluation_index"])): row for row in frame_rows}
    pair_map = {(row["recording_id"], row["sample"]): row for row in or92_contract["frame_pairs"]}
    episode_map = {row["recording_id"]: row for row in or91_contract["final_evaluator_heldout_episodes"]}

    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    body_names = [body["name"] for body in scene["bodies"]]
    prepared: list[dict[str, Any]] = []
    trace_cache: dict[str, dict[str, Any]] = {}
    for sample in contract["samples"]:
        recording_id = sample["recording_id"]
        pair = pair_map[(recording_id, sample["sample"])]
        physical_path = REPO_ROOT / pair["physical"]["path"]
        if sha256_file(physical_path) != pair["physical"]["sha256"]:
            raise ValueError("OR94 physical frame hash mismatch")
        indexed = frame_map[(recording_id, int(sample["evaluation_index"]))]
        if int(indexed["state_trace_frame_index"]) != int(sample["state_trace_frame_index"]):
            raise ValueError("OR94 trace-frame binding drifted")
        if recording_id not in trace_cache:
            trace_binding = episode_map[recording_id]["state_trace"]
            trace_path = REPO_ROOT / trace_binding["path"]
            if sha256_file(trace_path) != trace_binding["sha256"]:
                raise ValueError("OR94 trace hash mismatch")
            trace_cache[recording_id] = json.loads(trace_path.read_text())
        trace = trace_cache[recording_id]
        if trace["body_names"] != body_names:
            raise ValueError("scene and trace body ordering drifted")
        physical = cv2.imread(str(physical_path), cv2.IMREAD_COLOR)
        if physical is None or physical.shape[:2] != (240, 320):
            raise ValueError("OR94 physical audit frame unreadable or wrong size")
        prepared.append(
            {
                "sample": sample,
                "physical": physical,
                "trace": {"body_names": trace["body_names"], "frames": [trace["frames"][int(sample["state_trace_frame_index"])]]},
            }
        )

    frozen = contract["frozen_candidate"]
    anchor_body_id = int(frozen["static_workcell_transform"]["anchor_body_id"])
    static_vector = np.asarray(frozen["static_workcell_transform"]["vector"], dtype=np.float64)
    static_family = {
        "anchor_body_id": anchor_body_id,
        "transformed_workcell_body_ids": [int(value) for value in frozen["static_workcell_transform"]["transformed_body_ids"]],
    }
    left_ids = [int(value) for value in frozen["baseline_left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["baseline_right_robot_transform"]["transformed_body_ids"]]
    baseline_vector = np.asarray(
        frozen["baseline_left_robot_transform"]["vector"] + frozen["baseline_right_robot_transform"]["vector"],
        dtype=np.float64,
    )
    camera = frozen["camera"]
    response = frozen["global_monotone_response"]
    renderer = contract["renderer"]
    edge = contract["metric"]["edge"]
    search = contract["search"]
    search_width, search_height = int(search["width_px"]), int(search["height_px"])
    search_renderer = dict(renderer)
    search_renderer["width_px"] = search_width
    search_renderer["height_px"] = search_height
    search_physical = [cv2.resize(row["physical"], (search_width, search_height), interpolation=cv2.INTER_AREA) for row in prepared]
    points = np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64)
    search_masks = _region_masks(
        points * np.asarray([search_width / 320.0, search_height / 240.0]),
        width=search_width,
        height=search_height,
        dilation_kernel_px=max(1, round(int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]) * search_width / 320.0)),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"])
    library_path, compile_command, compiler_stderr = _compile_native(
        {"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}},
        output_directory,
    )
    robot_ids = set(left_ids) | set(right_ids)
    robot_scene = dict(scene)
    robot_scene["geoms"] = [geom for geom in scene["geoms"] if int(geom["body_id"]) in robot_ids]
    empty_family = {"anchor_body_id": anchor_body_id, "transformed_workcell_body_ids": []}
    robot_only_render_count = 0
    robot_only_triangle_counts: list[int] = []

    def robot_only_rows(vector: np.ndarray) -> list[dict[str, float]]:
        nonlocal robot_only_render_count
        rows: list[dict[str, float]] = []
        for physical, prepared_row in zip(search_physical, prepared, strict=True):
            transformed = _independently_registered_trace(
                prepared_row["trace"],
                anchor_body_id=anchor_body_id,
                left_body_ids=left_ids,
                right_body_ids=right_ids,
                vector=vector,
            )
            pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(
                robot_scene,
                transformed,
                meshes,
                camera,
                search_renderer,
                empty_family,
                np.zeros(3, dtype=np.float64),
            )
            candidate, _, _, _ = _native_rasterize(library_path, pixels, depths, colors, search_renderer)
            candidate = apply_monotone_response(
                candidate,
                bias=float(response["bias"]),
                low_slope=float(response["low_intensity_slope"]),
                high_slope=float(response["high_intensity_slope"]),
                knot=int(response["fixed_input_knot"]),
            )
            physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
            candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
            board = _masked_tolerant_edge_f1(physical_gray, candidate_gray, search_masks[0], edge)
            outside = _masked_tolerant_edge_f1(physical_gray, candidate_gray, search_masks[1], edge)
            rows.append({"board_plus_margin_edge_f1": float(board["f1"]), "outside_board_edge_f1": float(outside["f1"])})
            robot_only_render_count += 1
            robot_only_triangle_counts.append(int(triangle_count))
        return rows

    proxy_baseline_rows = robot_only_rows(baseline_vector)
    evaluation_count = 0
    best_score = -np.inf
    best_history: list[dict[str, Any]] = []

    def objective(vector: np.ndarray) -> float:
        nonlocal evaluation_count, best_score
        rows = robot_only_rows(vector)
        score = _mean_region(rows, "outside_board_edge_f1") + 0.30 * _mean_region(rows, "board_plus_margin_edge_f1")
        evaluation_count += 1
        if score > best_score:
            best_score = score
            best_history.append({"evaluation": evaluation_count, "score": score, "vector": np.asarray(vector).tolist()})
        return -score

    started = time.perf_counter()
    result = differential_evolution(
        objective,
        bounds=[tuple(float(value) for value in bounds) for bounds in contract["robot_registration_family"]["bounds"]],
        rng=np.random.default_rng(int(search["seed"])),
        popsize=int(search["population_size_multiplier"]),
        maxiter=int(search["maximum_iterations"]),
        tol=float(search["tolerance"]),
        atol=float(search["absolute_tolerance"]),
        polish=bool(search["polish"]),
        workers=int(search["workers"]),
        updating="immediate",
    )
    if evaluation_count > int(search["maximum_candidate_evaluations"]):
        raise RuntimeError("OR94 search exceeded frozen candidate budget")
    selected_vector = np.asarray(result.x, dtype=np.float64)
    proxy_selected_rows = robot_only_rows(selected_vector)
    if robot_only_render_count > int(search["maximum_robot_only_mesh_renders"]):
        raise RuntimeError("OR94 robot-only render budget exceeded")

    board_mask, outside_mask = _region_masks(
        points,
        width=320,
        height=240,
        dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    final_rows: list[dict[str, Any]] = []
    montage_rows: list[np.ndarray] = []
    full_triangle_counts: list[int] = []
    for prepared_row in prepared:
        variants: dict[str, dict[str, Any]] = {}
        images: dict[str, np.ndarray] = {}
        for label, vector in (("baseline", baseline_vector), ("selected", selected_vector)):
            transformed = _independently_registered_trace(
                prepared_row["trace"],
                anchor_body_id=anchor_body_id,
                left_body_ids=left_ids,
                right_body_ids=right_ids,
                vector=vector,
            )
            pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(
                scene, transformed, meshes, camera, renderer, static_family, static_vector
            )
            candidate, updates, occluded, raster_seconds = _native_rasterize(library_path, pixels, depths, colors, renderer)
            candidate = apply_monotone_response(
                candidate,
                bias=float(response["bias"]),
                low_slope=float(response["low_intensity_slope"]),
                high_slope=float(response["high_intensity_slope"]),
                knot=int(response["fixed_input_knot"]),
            )
            images[label] = candidate
            physical_gray = cv2.cvtColor(prepared_row["physical"], cv2.COLOR_BGR2GRAY)
            candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
            whole = _metrics(prepared_row["physical"], candidate, edge)
            board = _masked_tolerant_edge_f1(physical_gray, candidate_gray, board_mask, edge)
            outside = _masked_tolerant_edge_f1(physical_gray, candidate_gray, outside_mask, edge)
            filename = f"{prepared_row['sample']['recording_id']}-{prepared_row['sample']['sample']}-{label}.png"
            variants[label] = {
                "whole_frame": whole,
                "board_plus_margin": board,
                "outside_board": outside,
                "render": {"total_raster_triangle_count": int(triangle_count), "depth_buffer_update_count": int(updates), "occluded_fragment_count": int(occluded), "native_raster_seconds": float(raster_seconds)},
                "candidate_image": _write_png(output_directory / filename, candidate),
            }
            full_triangle_counts.append(int(triangle_count))
        final_rows.append(
            {
                "recording_id": prepared_row["sample"]["recording_id"],
                "sample": prepared_row["sample"]["sample"],
                "state_trace_frame_index": int(prepared_row["sample"]["state_trace_frame_index"]),
                "baseline": variants["baseline"],
                "selected": variants["selected"],
                "outside_board_edge_f1_delta": float(variants["selected"]["outside_board"]["f1"] - variants["baseline"]["outside_board"]["f1"]),
                "board_plus_margin_edge_f1_delta": float(variants["selected"]["board_plus_margin"]["f1"] - variants["baseline"]["board_plus_margin"]["f1"]),
            }
        )
        montage_rows.append(np.concatenate([prepared_row["physical"], images["baseline"], images["selected"]], axis=1))
    montage_binding = _write_png(output_directory / "physical_baseline_selected.png", np.concatenate(montage_rows, axis=0))
    baseline_outside = float(np.mean([row["baseline"]["outside_board"]["f1"] for row in final_rows]))
    selected_outside = float(np.mean([row["selected"]["outside_board"]["f1"] for row in final_rows]))
    baseline_board = float(np.mean([row["baseline"]["board_plus_margin"]["f1"] for row in final_rows]))
    selected_board = float(np.mean([row["selected"]["board_plus_margin"]["f1"] for row in final_rows]))
    improved_samples = sum(row["outside_board_edge_f1_delta"] >= 0.02 for row in final_rows)
    acceptance = contract["acceptance"]
    gates = {
        "exact_six_bound_samples": len(final_rows) == 6,
        "one_shared_six_parameter_independent_robot_vector": len(selected_vector) == 6,
        "exact_mesh_robot_only_search_within_candidate_budget": evaluation_count <= int(search["maximum_candidate_evaluations"]),
        "exact_mesh_robot_only_search_within_render_budget": robot_only_render_count <= int(search["maximum_robot_only_mesh_renders"]),
        "constant_nonzero_robot_only_triangle_count": len(set(robot_only_triangle_counts)) == 1 and robot_only_triangle_counts[0] > 0,
        "exact_six_baseline_and_six_selected_full_mesh_renders": len(full_triangle_counts) == 12,
        "expected_full_scene_triangle_count_every_render": all(value == 824944 for value in full_triangle_counts),
        "manifest_unique_assets_read_once": len(asset_receipts) == int(contract["resource_boundary"]["mesh_asset_reads_allowed"]),
        "minimum_selected_mean_outside_board_edge_f1": selected_outside >= float(acceptance["minimum_selected_mean_outside_board_edge_f1"]),
        "minimum_selected_minus_baseline_mean_outside_board_edge_f1": selected_outside - baseline_outside >= float(acceptance["minimum_selected_minus_baseline_mean_outside_board_edge_f1"]),
        "minimum_samples_with_material_outside_board_improvement": improved_samples >= int(acceptance["minimum_samples_with_outside_board_edge_f1_delta_at_least_0p02"]),
        "minimum_selected_mean_board_plus_margin_edge_f1": selected_board >= float(acceptance["minimum_selected_mean_board_plus_margin_edge_f1"]),
        "minimum_selected_minus_baseline_mean_board_plus_margin_edge_f1": selected_board - baseline_board >= float(acceptance["minimum_selected_minus_baseline_mean_board_plus_margin_edge_f1"]),
        "static_workcell_camera_response_actions_states_and_timing_fixed": True,
        "no_analytic_proxy_new_physical_decode_replay_hardware_or_paid_compute": True,
        "post_final_diagnostic_not_promotion": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_INDEPENDENT_LEFT_RIGHT_ROBOT_BASE_SE2_HEADROOM_SELECTED" if passed else "TERMINAL_INDEPENDENT_LEFT_RIGHT_ROBOT_BASE_SE2_INSUFFICIENT",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "selected": {"parameter_names": contract["robot_registration_family"]["parameter_names"], "vector": selected_vector.tolist(), "optimizer_converged": bool(result.success), "optimizer_message": str(result.message), "robot_only_exact_mesh_rows": proxy_selected_rows},
        "baseline": {"vector": baseline_vector.tolist(), "robot_only_exact_mesh_rows": proxy_baseline_rows},
        "best_history": best_history,
        "final_rows": final_rows,
        "summary": {
            "baseline_mean_outside_board_edge_f1": baseline_outside,
            "selected_mean_outside_board_edge_f1": selected_outside,
            "selected_minus_baseline_mean_outside_board_edge_f1": selected_outside - baseline_outside,
            "samples_with_outside_board_edge_f1_delta_at_least_0p02": improved_samples,
            "baseline_mean_board_plus_margin_edge_f1": baseline_board,
            "selected_mean_board_plus_margin_edge_f1": selected_board,
            "selected_minus_baseline_mean_board_plus_margin_edge_f1": selected_board - baseline_board,
        },
        "montage": {**montage_binding, "layout": "physical_left_baseline_middle_selected_right"},
        "compiled_library": {"path": str(library_path.relative_to(REPO_ROOT)), "sha256": sha256_file(library_path), "compile_command": compile_command, "compiler_stderr": compiler_stderr},
        "gates": gates,
        "execution": {
            "already_extracted_physical_frame_reads": 6,
            "state_trace_frame_reads": 6,
            "new_physical_video_decodes": 0,
            "independent_parameter_count": 6,
            "mesh_asset_reads": len(asset_receipts),
            "analytic_or_bounds_proxy_renders": 0,
            "exact_robot_only_mesh_search_candidate_evaluations": evaluation_count,
            "exact_robot_only_mesh_search_renders": robot_only_render_count,
            "exact_full_mesh_baseline_renders": 6,
            "exact_full_mesh_selected_renders": 6,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "elapsed_seconds": time.perf_counter() - started,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_POST_FINAL_INDEPENDENT_ROBOT_BASE_FULL_CORPUS_DIAGNOSTIC" if passed else "REJECT_RIGID_BASE_REGISTRATION_AND_REATTRIBUTE_KINEMATIC_OR_SCENE_CONTENT_RESIDUAL",
        "next_transition": "freeze_or95_post_final_independent_robot_base_full_corpus_diagnostic" if passed else "freeze_or95_post_final_robot_kinematic_scene_content_residual_attribution",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(fit_once(), sort_keys=True))
