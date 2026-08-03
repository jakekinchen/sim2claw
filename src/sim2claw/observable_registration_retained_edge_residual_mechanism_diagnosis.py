"""Attribute the OR58 edge deficit without producing another candidate."""

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
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)
from .observable_registration_temporal_pixel_similarity import _decode_video


SCHEMA = (
    "sim2claw.observable_registration_retained_edge_residual_mechanism_diagnosis_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_retained_edge_residual_mechanism_diagnosis_receipt.v1"
)
ROWS_SCHEMA = (
    "sim2claw.observable_registration_retained_edge_residual_mechanism_diagnosis_rows.v1"
)
TILES_SCHEMA = (
    "sim2claw.observable_registration_retained_edge_residual_mechanism_diagnosis_tiles.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_retained_edge_residual_mechanism_diagnosis_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_retained_edge_residual_mechanism_diagnosis_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_retained_edge_residual_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="retained edge residual diagnosis")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    timeline = contract["timeline"]
    _require(
        timeline["decoded_frame_count"] == 531
        and timeline["scored_sample_range_inclusive"] == [0, 515]
        and timeline["scored_frame_count"] == 516
        and timeline["width_px"] == 640
        and timeline["height_px"] == 480
        and timeline["fps"] == 20.0,
        "timeline drifted",
    )
    regions = contract["regions"]
    _require(
        regions["classes"]
        == ["motion_union", "nonmotion_board", "nonmotion_outside_board"]
        and regions["mutually_exclusive"] is True
        and regions["exhaustive"] is True,
        "region partition drifted",
    )
    aggregation = contract["aggregation"]
    _require(
        aggregation["edge_population_weighted"] is True
        and aggregation["tile_columns"] == 8
        and aggregation["tile_rows"] == 6,
        "aggregation drifted",
    )
    _require(
        contract["decision_rule"]["target_pass_allowed"] is False,
        "diagnostic cannot pass target",
    )
    _require(
        not any(contract["resource_boundary"].values()),
        "resource boundary widened",
    )
    _require(all(contract["prohibitions"].values()), "prohibition relaxed")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _empty_counts() -> dict[str, int]:
    return {
        "physical_edge_count": 0,
        "simulator_edge_count": 0,
        "physical_matched_edge_count": 0,
        "simulator_matched_edge_count": 0,
    }


def _add_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key in target:
        target[key] += int(source[key])


def _score_region(
    physical_edges: np.ndarray,
    simulator_edges: np.ndarray,
    physical_dilated: np.ndarray,
    simulator_dilated: np.ndarray,
    mask: np.ndarray,
) -> dict[str, int]:
    return {
        "physical_edge_count": int(np.sum(physical_edges & mask)),
        "simulator_edge_count": int(np.sum(simulator_edges & mask)),
        "physical_matched_edge_count": int(
            np.sum(physical_edges & simulator_dilated & mask)
        ),
        "simulator_matched_edge_count": int(
            np.sum(simulator_edges & physical_dilated & mask)
        ),
    }


def _derive_metrics(counts: dict[str, int]) -> dict[str, float | int]:
    physical = int(counts["physical_edge_count"])
    simulator = int(counts["simulator_edge_count"])
    physical_matched = int(counts["physical_matched_edge_count"])
    simulator_matched = int(counts["simulator_matched_edge_count"])
    denominator = physical + simulator
    matched = physical_matched + simulator_matched
    return {
        **counts,
        "edge_denominator": denominator,
        "matched_edge_mass": matched,
        "unmatched_edge_mass": denominator - matched,
        "physical_edge_recall": 1.0 if physical == 0 else physical_matched / physical,
        "simulator_edge_precision": (
            1.0 if simulator == 0 else simulator_matched / simulator
        ),
        "tolerant_edge_f1": 1.0 if denominator == 0 else matched / denominator,
    }


def _phase_name(sample_index: int, phases: list[dict[str, Any]]) -> str:
    for phase in phases:
        start, stop = [int(value) for value in phase["sample_range_inclusive"]]
        if start <= sample_index <= stop:
            return str(phase["name"])
    raise FactoryArtifactError(f"sample {sample_index} has no phase")


def evaluate_retained_edge_residual_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR59 one-run receipt already exists")
    contract = load_retained_edge_residual_contract(contract_path, root=root)
    or55 = _bound_json(
        contract["sources"]["or55_contract"], root=root, label="OR55 contract"
    )
    or26 = _bound_json(
        contract["sources"]["or26_receipt"], root=root, label="OR26 receipt"
    )
    or58 = _bound_json(
        contract["sources"]["or58_receipt"], root=root, label="OR58 receipt"
    )
    _require(
        or58["status"] == "PASS_MEAN_AND_TEMPORAL_PIXEL_TARGET_EDGE_GATE_REMAINS"
        and or58["mean_and_temporal_distribution_gates_pass"] is True
        and or58["all_acceptance_gates_pass"] is False
        and or58["acceptance_gates"]["mean_tolerant_edge_f1"] is False,
        "OR58 boundary drifted",
    )
    timeline = contract["timeline"]
    physical_frames = _decode_video(
        _bound_path(contract["sources"]["physical_video"], root=root, label="physical"),
        width=int(timeline["width_px"]),
        height=int(timeline["height_px"]),
    )
    simulator_frames = _decode_video(
        _bound_path(
            contract["sources"]["or58_candidate_video"],
            root=root,
            label="OR58 candidate",
        ),
        width=int(timeline["width_px"]),
        height=int(timeline["height_px"]),
    )
    _require(
        len(physical_frames) == len(simulator_frames) == 531,
        "decoded video length drifted",
    )
    scored_count = int(timeline["scored_frame_count"])
    edge_config = or55["metric"]["edge"]
    motion_config = or55["metric"]["motion_union"]
    phases = or55["timeline"]["phases"]
    corners = np.asarray(
        or26["camera_and_display_registration"]["physical_playing_corners_px"],
        dtype=np.int32,
    )
    board_mask_u8 = np.zeros((480, 640), dtype=np.uint8)
    cv2.fillConvexPoly(board_mask_u8, corners, 1)
    board_mask = board_mask_u8 > 0
    _require(int(np.sum(board_mask)) > 50000, "board mask is implausibly small")
    tolerance_kernel = np.ones(
        (
            int(edge_config["tolerance_dilation_kernel_px"]),
            int(edge_config["tolerance_dilation_kernel_px"]),
        ),
        dtype=np.uint8,
    )
    motion_kernel = np.ones(
        (
            int(motion_config["dilation_kernel_px"]),
            int(motion_config["dilation_kernel_px"]),
        ),
        dtype=np.uint8,
    )
    blur = int(motion_config["grayscale_gaussian_kernel_px"])
    class_order = list(contract["regions"]["classes"])
    aggregate = {name: _empty_counts() for name in class_order}
    phase_totals = {
        str(phase["name"]): {name: _empty_counts() for name in class_order}
        for phase in phases
    }
    tile_columns = int(contract["aggregation"]["tile_columns"])
    tile_rows = int(contract["aggregation"]["tile_rows"])
    tile_width = 640 // tile_columns
    tile_height = 480 // tile_rows
    tiles = [
        {
            "tile_row": row,
            "tile_column": column,
            "bounds_xyxy": [
                column * tile_width,
                row * tile_height,
                (column + 1) * tile_width,
                (row + 1) * tile_height,
            ],
            "counts": _empty_counts(),
        }
        for row in range(tile_rows)
        for column in range(tile_columns)
    ]
    rows: list[dict[str, Any]] = []
    previous_physical: np.ndarray | None = None
    previous_simulator: np.ndarray | None = None
    reproduced_frame_f1: list[float] = []
    for sample_index in range(scored_count):
        physical_gray = cv2.cvtColor(physical_frames[sample_index], cv2.COLOR_BGR2GRAY)
        simulator_gray = cv2.cvtColor(simulator_frames[sample_index], cv2.COLOR_BGR2GRAY)
        physical_edges = cv2.Canny(
            physical_gray,
            int(edge_config["canny_low_threshold"]),
            int(edge_config["canny_high_threshold"]),
        ) > 0
        simulator_edges = cv2.Canny(
            simulator_gray,
            int(edge_config["canny_low_threshold"]),
            int(edge_config["canny_high_threshold"]),
        ) > 0
        physical_dilated = cv2.dilate(physical_edges.astype(np.uint8), tolerance_kernel) > 0
        simulator_dilated = cv2.dilate(simulator_edges.astype(np.uint8), tolerance_kernel) > 0
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
        region_rows: dict[str, Any] = {}
        frame_total = _empty_counts()
        for name in class_order:
            counts = _score_region(
                physical_edges,
                simulator_edges,
                physical_dilated,
                simulator_dilated,
                masks[name],
            )
            _add_counts(aggregate[name], counts)
            _add_counts(phase_totals[phase][name], counts)
            _add_counts(frame_total, counts)
            region_rows[name] = _derive_metrics(counts)
        frame_metrics = _derive_metrics(frame_total)
        reproduced_frame_f1.append(float(frame_metrics["tolerant_edge_f1"]))
        rows.append(
            {
                "sample_index": sample_index,
                "phase": phase,
                "motion_union_pixel_count": int(np.sum(motion_union)),
                "regions": region_rows,
                "full_frame": frame_metrics,
            }
        )
        for tile in tiles:
            x0, y0, x1, y1 = tile["bounds_xyxy"]
            physical_tile = physical_edges[y0:y1, x0:x1]
            simulator_tile = simulator_edges[y0:y1, x0:x1]
            counts = {
                "physical_edge_count": int(np.sum(physical_tile)),
                "simulator_edge_count": int(np.sum(simulator_tile)),
                "physical_matched_edge_count": int(
                    np.sum(
                        physical_tile
                        & simulator_dilated[y0:y1, x0:x1]
                    )
                ),
                "simulator_matched_edge_count": int(
                    np.sum(
                        simulator_tile
                        & physical_dilated[y0:y1, x0:x1]
                    )
                ),
            }
            _add_counts(tile["counts"], counts)
    reproduced_mean = float(np.mean(np.asarray(reproduced_frame_f1, dtype=np.float64)))
    expected_mean = float(or58["metrics"]["tolerant_edge_f1"]["mean"])
    _require(abs(reproduced_mean - expected_mean) < 1e-12, "OR58 edge metric did not reproduce")
    total_denominator = sum(
        int(counts["physical_edge_count"]) + int(counts["simulator_edge_count"])
        for counts in aggregate.values()
    )
    aggregate_metrics: dict[str, Any] = {}
    for name in class_order:
        metrics = _derive_metrics(aggregate[name])
        metrics["edge_denominator_share"] = (
            int(metrics["edge_denominator"]) / total_denominator
        )
        aggregate_metrics[name] = metrics
    phase_metrics = {
        phase: {name: _derive_metrics(counts) for name, counts in values.items()}
        for phase, values in phase_totals.items()
    }
    tile_metrics: list[dict[str, Any]] = []
    for tile in tiles:
        metrics = _derive_metrics(tile.pop("counts"))
        tile_metrics.append({**tile, **metrics})
    tile_metrics.sort(
        key=lambda item: (
            -int(item["unmatched_edge_mass"]),
            -int(item["edge_denominator"]),
            int(item["tile_row"]),
            int(item["tile_column"]),
        )
    )
    selected_class = max(
        class_order,
        key=lambda name: (
            int(aggregate_metrics[name]["unmatched_edge_mass"]),
            int(aggregate_metrics[name]["edge_denominator"]),
            -class_order.index(name),
        ),
    )
    selected_mechanism = contract["decision_rule"]["mechanism_by_class"][selected_class]
    remaining = _empty_counts()
    for name in class_order:
        if name != selected_class:
            _add_counts(remaining, aggregate[name])
    output_directory.mkdir(parents=True, exist_ok=True)
    rows_path = output_directory / "edge_region_rows.json"
    tiles_path = output_directory / "edge_tile_rows.json"
    atomic_write_json(
        rows_path,
        {"schema_version": ROWS_SCHEMA, "experiment_id": contract["experiment_id"], "rows": rows},
    )
    atomic_write_json(
        tiles_path,
        {
            "schema_version": TILES_SCHEMA,
            "experiment_id": contract["experiment_id"],
            "rows_ranked_worst_first": tile_metrics,
        },
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": "PASS_EDGE_RESIDUAL_MECHANISM_ATTRIBUTED_TARGET_STILL_OPEN",
        "proof_class": contract["proof_class"],
        "source_bindings": {
            name: binding["sha256"] for name, binding in contract["sources"].items()
        },
        "timeline": {
            "decoded_frame_count": 531,
            "scored_frame_count": scored_count,
            "first_scored_sample": 0,
            "last_scored_sample": scored_count - 1,
        },
        "or58_reproduction": {
            "mean_frame_tolerant_edge_f1": reproduced_mean,
            "expected_mean_frame_tolerant_edge_f1": expected_mean,
            "exact_within_1e_12": True,
        },
        "aggregate_region_metrics": aggregate_metrics,
        "phase_region_metrics": phase_metrics,
        "counterfactual_excluding_dominant_class": {
            "excluded_class": selected_class,
            **_derive_metrics(remaining),
            "diagnostic_only_not_an_acceptance_gate": True,
        },
        "mechanism_selection": {
            "rule": contract["decision_rule"]["select_class_by"],
            "selected_class": selected_class,
            "selected_next_mechanism": selected_mechanism,
            "target_pass_allowed": False,
        },
        "spatial_residual": {
            "tile_count": len(tile_metrics),
            "worst_five_tiles": tile_metrics[:5],
        },
        "outputs": {
            "edge_region_rows_path": rows_path.name,
            "edge_region_rows_sha256": sha256_file(rows_path),
            "edge_tile_rows_path": tiles_path.name,
            "edge_tile_rows_sha256": sha256_file(tiles_path),
        },
        "execution": {
            "diagnostic_frame_evaluations": scored_count,
            "candidate_videos": 0,
            "renderer_runs": 0,
            "physics_integrations": 0,
            "action_changes": 0,
            "state_changes": 0,
            "geometric_warps": 0,
            "response_fits": 0,
            "per_frame_transforms": 0,
            "physical_pixel_composites": 0,
            "hardware_actions": 0,
        },
        "all_acceptance_gates_pass": False,
        "claim_limits": {
            "diagnostic_only": True,
            "same_video_target_pass": False,
            "episode_specific_visual_replay_only": True,
            "metric_camera_calibration": False,
            "physics_fidelity": False,
            "global_mapping_approval": False,
            "simulator_promotion": False,
            "task_transfer": False,
        },
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    evaluate_retained_edge_residual_once()


if __name__ == "__main__":
    main()
