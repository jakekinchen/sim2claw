"""Reattribute edge residuals after the frozen OR63 line counterfactual."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_json, _bound_path
from .observable_registration_retained_edge_residual_mechanism_diagnosis import (
    _add_counts,
    _derive_metrics,
    _empty_counts,
    _phase_name,
    _score_region,
)
from .observable_registration_temporal_pixel_similarity import _decode_video


SCHEMA = "sim2claw.observable_registration_post_environment_primitive_edge_residual_reattribution_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_post_environment_primitive_edge_residual_reattribution_receipt.v1"
ROWS_SCHEMA = "sim2claw.observable_registration_post_environment_primitive_edge_residual_reattribution_rows.v1"
CONTRACT_PATH = REPO_ROOT / "configs/evaluations/observable_registration_post_environment_primitive_edge_residual_reattribution_v1.json"
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_post_environment_primitive_edge_residual_reattribution_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_post_environment_primitive_edge_residual_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="post-environment edge residual")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    timeline = contract["timeline"]
    _require(
        timeline == {
            "decoded_frame_count": 531,
            "scored_sample_range_inclusive": [0, 515],
            "scored_frame_count": 516,
            "width_px": 640,
            "height_px": 480,
            "fps": 20.0,
        },
        "timeline drifted",
    )
    counterfactual = contract["counterfactual"]
    _require(
        counterfactual == {
            "line_primitive_count": 24,
            "line_width_px": 1,
            "union_with_decoded_or58_simulator_canny_edges": True,
            "metric_inherited_unchanged_from_or55": True,
            "motion_union_inherited_unchanged_from_or55": True,
            "board_polygon_inherited_unchanged_from_or26": True,
        },
        "counterfactual drifted",
    )
    _require(
        contract["regions"] == {
            "classes": ["motion_union", "nonmotion_board", "nonmotion_outside_board"],
            "mutually_exclusive": True,
            "exhaustive": True,
        },
        "region partition drifted",
    )
    _require(contract["decision_rule"]["target_pass_allowed"] is False, "diagnostic cannot pass target")
    _require(not any(contract["resource_boundary"].values()), "resource boundary widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _edge_map(frame: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Canny(
        gray,
        int(config["canny_low_threshold"]),
        int(config["canny_high_threshold"]),
    ) > 0


def _mean_frame_f1(
    values: list[tuple[np.ndarray, np.ndarray]], kernel: np.ndarray
) -> float:
    scores: list[float] = []
    for physical, simulator in values:
        physical_dilated = cv2.dilate(physical.astype(np.uint8), kernel) > 0
        simulator_dilated = cv2.dilate(simulator.astype(np.uint8), kernel) > 0
        denominator = int(np.sum(physical)) + int(np.sum(simulator))
        matched = int(np.sum(physical & simulator_dilated)) + int(
            np.sum(simulator & physical_dilated)
        )
        scores.append(1.0 if denominator == 0 else matched / denominator)
    return float(np.mean(np.asarray(scores, dtype=np.float64)))


def evaluate_post_environment_primitive_edge_residual_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR65 one-run receipt already exists")
    contract = load_post_environment_primitive_edge_residual_contract(contract_path, root=root)
    or55 = _bound_json(contract["sources"]["or55_contract"], root=root, label="OR55 contract")
    or26 = _bound_json(contract["sources"]["or26_receipt"], root=root, label="OR26 receipt")
    or58 = _bound_json(contract["sources"]["or58_receipt"], root=root, label="OR58 receipt")
    or59 = _bound_json(contract["sources"]["or59_receipt"], root=root, label="OR59 receipt")
    scene = _bound_json(contract["sources"]["or63_scene_spec"], root=root, label="OR63 scene spec")
    or64 = _bound_json(contract["sources"]["or64_receipt"], root=root, label="OR64 receipt")
    or64_closeout = _bound_json(contract["sources"]["or64_closeout"], root=root, label="OR64 closeout")
    _require(
        or58["all_acceptance_gates_pass"] is False
        and or59["status"] == "PASS_EDGE_RESIDUAL_MECHANISM_ATTRIBUTED_TARGET_STILL_OPEN"
        and scene["physical_pixels_embedded"] is False
        and scene["background_plate"] is False
        and scene["texture"] is False
        and len(scene["line_primitives"]) == 24
        and or64["status"] == "PASS_PIXEL_FREE_ENVIRONMENT_PRIMITIVE_EDGE_HEADROOM_ADVANCE"
        and or64_closeout["result"]["target_pass"] is False,
        "predecessor boundary drifted",
    )
    timeline = contract["timeline"]
    physical_frames = _decode_video(
        _bound_path(contract["sources"]["physical_video"], root=root, label="physical"),
        width=int(timeline["width_px"]),
        height=int(timeline["height_px"]),
    )
    simulator_frames = _decode_video(
        _bound_path(contract["sources"]["or58_candidate_video"], root=root, label="OR58 candidate"),
        width=int(timeline["width_px"]),
        height=int(timeline["height_px"]),
    )
    _require(len(physical_frames) == len(simulator_frames) == 531, "decoded video length drifted")

    edge_config = or55["metric"]["edge"]
    motion_config = or55["metric"]["motion_union"]
    phases = or55["timeline"]["phases"]
    class_order = list(contract["regions"]["classes"])
    tolerance_size = int(edge_config["tolerance_dilation_kernel_px"])
    tolerance_kernel = np.ones((tolerance_size, tolerance_size), dtype=np.uint8)
    motion_size = int(motion_config["dilation_kernel_px"])
    motion_kernel = np.ones((motion_size, motion_size), dtype=np.uint8)
    blur = int(motion_config["grayscale_gaussian_kernel_px"])

    board_mask_u8 = np.zeros((480, 640), dtype=np.uint8)
    corners = np.asarray(
        or26["camera_and_display_registration"]["physical_playing_corners_px"],
        dtype=np.int32,
    )
    cv2.fillConvexPoly(board_mask_u8, corners, 1)
    board_mask = board_mask_u8 > 0
    _require(int(np.sum(board_mask)) > 50000, "board mask is implausibly small")

    vector_mask_u8 = np.zeros((480, 640), dtype=np.uint8)
    for primitive in scene["line_primitives"]:
        x0, y0, x1, y1 = [int(value) for value in primitive["endpoints_xyxy_px"]]
        cv2.line(vector_mask_u8, (x0, y0), (x1, y1), 1, 1, cv2.LINE_8)
    vector_mask = vector_mask_u8 > 0
    _require(int(np.sum(vector_mask)) > 0, "empty vector skeleton")

    baseline_aggregate = {name: _empty_counts() for name in class_order}
    post_vector_aggregate = {name: _empty_counts() for name in class_order}
    phase_totals = {
        str(phase["name"]): {name: _empty_counts() for name in class_order}
        for phase in phases
    }
    previous_physical: np.ndarray | None = None
    previous_simulator: np.ndarray | None = None
    baseline_frame_edges: list[tuple[np.ndarray, np.ndarray]] = []
    post_vector_frame_edges: list[tuple[np.ndarray, np.ndarray]] = []
    rows: list[dict[str, Any]] = []

    for sample_index in range(int(timeline["scored_frame_count"])):
        physical_frame = physical_frames[sample_index]
        simulator_frame = simulator_frames[sample_index]
        physical_edges = _edge_map(physical_frame, edge_config)
        baseline_edges = _edge_map(simulator_frame, edge_config)
        post_vector_edges = baseline_edges | vector_mask
        physical_dilated = cv2.dilate(physical_edges.astype(np.uint8), tolerance_kernel) > 0
        baseline_dilated = cv2.dilate(baseline_edges.astype(np.uint8), tolerance_kernel) > 0
        post_vector_dilated = cv2.dilate(post_vector_edges.astype(np.uint8), tolerance_kernel) > 0

        physical_gray = cv2.cvtColor(physical_frame, cv2.COLOR_BGR2GRAY)
        simulator_gray = cv2.cvtColor(simulator_frame, cv2.COLOR_BGR2GRAY)
        physical_blurred = cv2.GaussianBlur(physical_gray, (blur, blur), 0.0)
        simulator_blurred = cv2.GaussianBlur(simulator_gray, (blur, blur), 0.0)
        if previous_physical is None or previous_simulator is None:
            motion_union = np.zeros((480, 640), dtype=bool)
        else:
            physical_delta = cv2.absdiff(physical_blurred, previous_physical)
            simulator_delta = cv2.absdiff(simulator_blurred, previous_simulator)
            motion_union = np.logical_or(
                physical_delta >= int(motion_config["physical_difference_threshold"]),
                simulator_delta >= int(motion_config["simulator_difference_threshold"]),
            )
            motion_union = cv2.dilate(motion_union.astype(np.uint8), motion_kernel) > 0
        previous_physical = physical_blurred
        previous_simulator = simulator_blurred
        masks = {
            "motion_union": motion_union,
            "nonmotion_board": (~motion_union) & board_mask,
            "nonmotion_outside_board": (~motion_union) & (~board_mask),
        }
        coverage = sum(mask.astype(np.uint8) for mask in masks.values())
        _require(bool(np.all(coverage == 1)), "region masks are not a partition")

        phase = _phase_name(sample_index, phases)
        row_regions: dict[str, Any] = {}
        for name in class_order:
            baseline_counts = _score_region(
                physical_edges, baseline_edges, physical_dilated, baseline_dilated, masks[name]
            )
            post_vector_counts = _score_region(
                physical_edges, post_vector_edges, physical_dilated, post_vector_dilated, masks[name]
            )
            _add_counts(baseline_aggregate[name], baseline_counts)
            _add_counts(post_vector_aggregate[name], post_vector_counts)
            _add_counts(phase_totals[phase][name], post_vector_counts)
            row_regions[name] = {
                "baseline": _derive_metrics(baseline_counts),
                "post_vector": _derive_metrics(post_vector_counts),
            }
        baseline_frame_edges.append((physical_edges, baseline_edges))
        post_vector_frame_edges.append((physical_edges, post_vector_edges))
        rows.append(
            {
                "sample_index": sample_index,
                "phase": phase,
                "motion_union_pixel_count": int(np.sum(motion_union)),
                "regions": row_regions,
            }
        )

    baseline_mean = _mean_frame_f1(baseline_frame_edges, tolerance_kernel)
    post_vector_mean = _mean_frame_f1(post_vector_frame_edges, tolerance_kernel)
    expected_baseline_mean = float(or58["metrics"]["tolerant_edge_f1"]["mean"])
    expected_post_vector_mean = float(
        or64["prefix_summaries"]["24"]["full_timeline_counterfactual_tolerant_edge_f1"]["mean"]
    )
    _require(abs(baseline_mean - expected_baseline_mean) < 1e-12, "OR58 mean edge metric did not reproduce")
    _require(abs(post_vector_mean - expected_post_vector_mean) < 1e-12, "OR64 full-line mean edge metric did not reproduce")

    for name in class_order:
        predecessor = or59["aggregate_region_metrics"][name]
        for key, value in baseline_aggregate[name].items():
            _require(int(predecessor[key]) == int(value), f"OR59 {name} {key} did not reproduce")

    baseline_denominator = sum(
        int(values["physical_edge_count"]) + int(values["simulator_edge_count"])
        for values in baseline_aggregate.values()
    )
    post_vector_denominator = sum(
        int(values["physical_edge_count"]) + int(values["simulator_edge_count"])
        for values in post_vector_aggregate.values()
    )
    region_metrics: dict[str, Any] = {}
    for name in class_order:
        baseline_metrics = _derive_metrics(baseline_aggregate[name])
        post_vector_metrics = _derive_metrics(post_vector_aggregate[name])
        baseline_metrics["edge_denominator_share"] = int(baseline_metrics["edge_denominator"]) / baseline_denominator
        post_vector_metrics["edge_denominator_share"] = int(post_vector_metrics["edge_denominator"]) / post_vector_denominator
        region_metrics[name] = {
            "baseline": baseline_metrics,
            "post_vector": post_vector_metrics,
            "tolerant_edge_f1_change": float(post_vector_metrics["tolerant_edge_f1"]) - float(baseline_metrics["tolerant_edge_f1"]),
            "unmatched_edge_mass_change": int(post_vector_metrics["unmatched_edge_mass"]) - int(baseline_metrics["unmatched_edge_mass"]),
        }
    phase_metrics = {
        phase: {name: _derive_metrics(values) for name, values in regions.items()}
        for phase, regions in phase_totals.items()
    }
    selected_class = max(
        class_order,
        key=lambda name: (
            int(region_metrics[name]["post_vector"]["unmatched_edge_mass"]),
            int(region_metrics[name]["post_vector"]["edge_denominator"]),
            -class_order.index(name),
        ),
    )
    selected_mechanism = contract["decision_rule"]["mechanism_by_class"][selected_class]

    output_directory.mkdir(parents=True, exist_ok=True)
    rows_path = output_directory / "post_vector_edge_region_rows.json"
    atomic_write_json(rows_path, {"schema_version": ROWS_SCHEMA, "experiment_id": contract["experiment_id"], "rows": rows})
    execution = {
        "diagnostic_frame_evaluations": 516,
        "line_primitives_applied": 24,
        "renderer_runs": 0,
        "simulator_replays": 0,
        "candidate_videos": 0,
        "bgr_pixel_outputs": 0,
        "image_outputs": 0,
        "texture_outputs": 0,
        "physical_pixel_composites": 0,
        "geometric_warps": 0,
        "scene_mutations": 0,
        "action_changes": 0,
        "state_changes": 0,
        "validation_or_stress_selections": 0,
        "hardware_actions": 0,
    }
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": "PASS_POST_ENVIRONMENT_PRIMITIVE_EDGE_RESIDUAL_REATTRIBUTION",
        "proof_class": contract["proof_class"],
        "source_bindings": {name: binding["sha256"] for name, binding in contract["sources"].items()},
        "timeline": {"decoded_frame_count": 531, "scored_frame_count": 516, "first_scored_sample": 0, "last_scored_sample": 515},
        "predecessor_reproduction": {
            "or58_mean_frame_tolerant_edge_f1": baseline_mean,
            "or58_expected_mean_frame_tolerant_edge_f1": expected_baseline_mean,
            "or58_exact_within_1e_12": True,
            "or59_aggregate_region_counts_exact": True,
            "or64_full_24_line_mean_frame_tolerant_edge_f1": post_vector_mean,
            "or64_expected_full_24_line_mean_frame_tolerant_edge_f1": expected_post_vector_mean,
            "or64_exact_within_1e_12": True,
        },
        "aggregate_region_metrics": region_metrics,
        "phase_post_vector_region_metrics": phase_metrics,
        "mechanism_selection": {
            "rule": contract["decision_rule"]["select_class_by"],
            "selected_class": selected_class,
            "selected_next_mechanism": selected_mechanism,
            "target_pass_allowed": False,
        },
        "outputs": {
            "post_vector_edge_region_rows_path": rows_path.name,
            "post_vector_edge_region_rows_sha256": sha256_file(rows_path),
        },
        "execution": execution,
        "all_acceptance_gates_pass": False,
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    evaluate_post_environment_primitive_edge_residual_once()


if __name__ == "__main__":
    main()
