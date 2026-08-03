"""Compile pixel-free static environment constraints from retained footage."""

from __future__ import annotations

import math
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
from .observable_registration_static_appearance_factorization import _range_indices
from .observable_registration_temporal_pixel_similarity import _decode_video, _summary


SCHEMA = (
    "sim2claw.observable_registration_renderer_independent_static_environment_scene_specification_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_renderer_independent_static_environment_scene_specification_receipt.v1"
)
SCENE_SCHEMA = (
    "sim2claw.observable_registration_renderer_independent_static_environment_scene_specification.v1"
)
ROWS_SCHEMA = (
    "sim2claw.observable_registration_renderer_independent_static_environment_primitive_support_rows.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_renderer_independent_static_environment_scene_specification_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_renderer_independent_static_environment_scene_specification_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_static_environment_scene_specification_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="static environment scene specification")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    timeline = contract["timeline"]
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    _require(
        timeline["decoded_frame_count"] == 531
        and timeline["scored_sample_range_inclusive"] == [0, 515]
        and timeline["development_frame_count"] == 220
        and timeline["validation_frame_count"] == 180
        and timeline["stress_frame_count"] == 116
        and timeline["selection_may_read_only_development"] is True
        and {name: len(values) for name, values in partitions.items()}
        == {"development": 220, "validation": 180, "stress": 116}
        and set().union(*(set(values) for values in partitions.values()))
        == set(range(516)),
        "timeline partitions drifted",
    )
    edge = contract["edge_extraction"]
    _require(
        edge["canny_low_threshold"] == 50
        and edge["canny_high_threshold"] == 150
        and edge["board_exclusion_dilation_px"] == 7
        and edge["minimum_development_physical_edge_occurrence"] == 0.35
        and edge["maximum_development_simulator_edge_occurrence"] == 0.10
        and edge["hough_threshold"] == 12
        and edge["minimum_line_length_px"] == 18
        and edge["maximum_line_gap_px"] == 8
        and edge["maximum_line_primitives"] == 24,
        "edge extraction drifted",
    )
    palette = contract["palette"]
    _require(
        palette["cluster_count"] == 6
        and palette["development_frame_stride"] == 10
        and palette["pixel_stride"] == 8
        and palette["opencv_rng_seed"] == 63
        and palette["attempts"] == 1,
        "palette extraction drifted",
    )
    _require(
        contract["acceptance"]["target_pass_allowed"] is False,
        "scene specification cannot pass target",
    )
    _require(
        not any(contract["resource_boundary"].values()),
        "resource boundary widened",
    )
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _edges(frame: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Canny(
        gray,
        int(config["canny_low_threshold"]),
        int(config["canny_high_threshold"]),
    ) > 0


def _extract_lines(
    stable_residual: np.ndarray, config: dict[str, Any]
) -> list[dict[str, Any]]:
    hough = cv2.HoughLinesP(
        stable_residual.astype(np.uint8) * 255,
        1.0,
        np.pi / 180.0,
        threshold=int(config["hough_threshold"]),
        minLineLength=int(config["minimum_line_length_px"]),
        maxLineGap=int(config["maximum_line_gap_px"]),
    )
    _require(hough is not None and len(hough), "no persistent residual lines found")
    candidates: list[tuple[float, tuple[int, int, int, int]]] = []
    for raw in hough[:, 0, :]:
        x0, y0, x1, y1 = [int(value) for value in raw]
        length = math.hypot(x1 - x0, y1 - y0)
        candidates.append((length, (x0, y0, x1, y1)))
    candidates.sort(key=lambda value: (-value[0], value[1]))
    occupied = np.zeros(stable_residual.shape, dtype=np.uint8)
    selected: list[dict[str, Any]] = []
    width = int(config["deduplication_line_width_px"])
    for length, endpoints in candidates:
        candidate_mask = np.zeros(stable_residual.shape, dtype=np.uint8)
        x0, y0, x1, y1 = endpoints
        cv2.line(candidate_mask, (x0, y0), (x1, y1), 1, width, cv2.LINE_8)
        denominator = int(np.sum(candidate_mask))
        overlap = int(np.sum((candidate_mask > 0) & (occupied > 0))) / denominator
        if overlap > float(config["maximum_deduplication_overlap_fraction"]):
            continue
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
        selected.append(
            {
                "primitive_id": f"outside_line_{len(selected):02d}",
                "endpoints_xyxy_px": [x0, y0, x1, y1],
                "length_px": float(length),
                "angle_degrees": float(angle),
                "development_deduplication_overlap_fraction": float(overlap),
            }
        )
        occupied = np.maximum(occupied, candidate_mask)
        if len(selected) == int(config["maximum_line_primitives"]):
            break
    return selected


def _line_skeleton(endpoints: list[int]) -> np.ndarray:
    mask = np.zeros((480, 640), dtype=np.uint8)
    x0, y0, x1, y1 = endpoints
    cv2.line(mask, (x0, y0), (x1, y1), 1, 1, cv2.LINE_8)
    return mask > 0


def _support(
    frames: list[np.ndarray],
    indices: list[int],
    skeletons: list[np.ndarray],
    *,
    edge_config: dict[str, Any],
) -> list[list[float]]:
    kernel_size = int(edge_config["support_tolerance_kernel_px"])
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
    values = [[] for _ in skeletons]
    denominators = [int(np.sum(mask)) for mask in skeletons]
    for index in indices:
        edges = _edges(frames[index], edge_config)
        dilated = cv2.dilate(edges.astype(np.uint8), kernel) > 0
        for slot, skeleton in enumerate(skeletons):
            values[slot].append(float(np.sum(skeleton & dilated) / denominators[slot]))
    return values


def _palette(
    frames: list[np.ndarray],
    development: list[int],
    outside_mask: np.ndarray,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    sampled_frames = development[:: int(config["development_frame_stride"])]
    stride = int(config["pixel_stride"])
    mask = outside_mask[::stride, ::stride]
    samples = np.concatenate(
        [frame[::stride, ::stride][mask] for frame in (frames[index] for index in sampled_frames)],
        axis=0,
    ).astype(np.float32)
    cv2.setRNGSeed(int(config["opencv_rng_seed"]))
    _, labels, centers = cv2.kmeans(
        samples,
        int(config["cluster_count"]),
        None,
        (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1),
        int(config["attempts"]),
        cv2.KMEANS_PP_CENTERS,
    )
    counts = np.bincount(labels[:, 0], minlength=int(config["cluster_count"]))
    rows = [
        {
            "bgr": [float(value) for value in centers[index]],
            "sample_fraction": float(counts[index] / np.sum(counts)),
        }
        for index in range(len(centers))
    ]
    rows.sort(key=lambda row: (-float(row["sample_fraction"]), row["bgr"]))
    return rows


def evaluate_static_environment_scene_specification_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR63 one-run receipt already exists")
    contract = load_static_environment_scene_specification_contract(
        contract_path, root=root
    )
    or26 = _bound_json(
        contract["sources"]["or26_receipt"], root=root, label="OR26 receipt"
    )
    or58 = _bound_json(
        contract["sources"]["or58_receipt"], root=root, label="OR58 receipt"
    )
    or59 = _bound_json(
        contract["sources"]["or59_receipt"], root=root, label="OR59 receipt"
    )
    or62 = _bound_json(
        contract["sources"]["or62_closeout"], root=root, label="OR62 closeout"
    )
    _require(
        or58["mean_and_temporal_distribution_gates_pass"] is True
        and or58["all_acceptance_gates_pass"] is False
        and or59["mechanism_selection"]["selected_class"]
        == "nonmotion_outside_board"
        and or62["result"]["all_local_browser_engine_routes_closed"] is True,
        "predecessor boundary drifted",
    )
    physical_frames = _decode_video(
        _bound_path(contract["sources"]["physical_video"], root=root, label="physical"),
        width=640,
        height=480,
    )
    simulator_frames = _decode_video(
        _bound_path(
            contract["sources"]["or58_candidate_video"],
            root=root,
            label="OR58 candidate",
        ),
        width=640,
        height=480,
    )
    _require(
        len(physical_frames) == len(simulator_frames) == 531,
        "decoded video length drifted",
    )
    timeline = contract["timeline"]
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    edge_config = contract["edge_extraction"]
    corners = np.asarray(
        or26["camera_and_display_registration"]["physical_playing_corners_px"],
        dtype=np.int32,
    )
    board = np.zeros((480, 640), dtype=np.uint8)
    cv2.fillConvexPoly(board, corners, 1)
    dilation = int(edge_config["board_exclusion_dilation_px"])
    board_exclusion = cv2.dilate(
        board, np.ones((dilation, dilation), dtype=np.uint8)
    ) > 0
    outside = ~board_exclusion
    development = partitions["development"]
    physical_occurrence = np.zeros((480, 640), dtype=np.uint16)
    simulator_occurrence = np.zeros((480, 640), dtype=np.uint16)
    for index in development:
        physical_occurrence += _edges(physical_frames[index], edge_config)
        simulator_occurrence += _edges(simulator_frames[index], edge_config)
    stable_residual = (
        (physical_occurrence / len(development))
        >= float(edge_config["minimum_development_physical_edge_occurrence"])
    ) & (
        (simulator_occurrence / len(development))
        <= float(edge_config["maximum_development_simulator_edge_occurrence"])
    ) & outside
    stable_residual = cv2.morphologyEx(
        stable_residual.astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((3, 3), dtype=np.uint8),
    ) > 0
    primitives = _extract_lines(stable_residual, edge_config)
    skeletons = [
        _line_skeleton(list(primitive["endpoints_xyxy_px"]))
        for primitive in primitives
    ]
    support: dict[str, dict[str, list[list[float]]]] = {}
    for partition, indices in partitions.items():
        support[partition] = {
            "physical": _support(
                physical_frames, indices, skeletons, edge_config=edge_config
            ),
            "simulator": _support(
                simulator_frames, indices, skeletons, edge_config=edge_config
            ),
        }
    rows: list[dict[str, Any]] = []
    for slot, primitive in enumerate(primitives):
        partition_rows: dict[str, Any] = {}
        for partition in partitions:
            physical_summary = _summary(support[partition]["physical"][slot])
            simulator_summary = _summary(support[partition]["simulator"][slot])
            partition_rows[partition] = {
                "physical_line_support": physical_summary,
                "simulator_line_support": simulator_summary,
                "mean_physical_minus_simulator_support": float(
                    physical_summary["mean"]
                )
                - float(simulator_summary["mean"]),
            }
        rows.append({**primitive, "partition_support": partition_rows})
    partition_aggregate: dict[str, Any] = {}
    for partition in partitions:
        physical_means = [
            float(row["partition_support"][partition]["physical_line_support"]["mean"])
            for row in rows
        ]
        simulator_means = [
            float(row["partition_support"][partition]["simulator_line_support"]["mean"])
            for row in rows
        ]
        partition_aggregate[partition] = {
            "primitive_physical_mean_support": _summary(physical_means),
            "primitive_simulator_mean_support": _summary(simulator_means),
            "mean_physical_minus_simulator_support": float(np.mean(physical_means))
            - float(np.mean(simulator_means)),
        }
    palette = _palette(
        physical_frames,
        development,
        outside,
        contract["palette"],
    )
    acceptance = contract["acceptance"]
    gates = {
        "minimum_frozen_line_primitives": len(primitives)
        >= int(acceptance["minimum_frozen_line_primitives"]),
        "minimum_validation_physical_minus_simulator_support": float(
            partition_aggregate["validation"][
                "mean_physical_minus_simulator_support"
            ]
        )
        >= float(
            acceptance["minimum_validation_physical_minus_simulator_support"]
        ),
    }
    passed = all(gates.values())
    status = (
        "PASS_PIXEL_FREE_STATIC_ENVIRONMENT_OBSERVATION_SPECIFICATION"
        if passed
        else "TERMINAL_STATIC_ENVIRONMENT_PRIMITIVES_INSUFFICIENT"
    )
    scene_document = {
        "schema_version": SCENE_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "coordinate_system": "physical_video_screen_pixels_xy_origin_top_left",
        "metric_3d_geometry": False,
        "physical_pixels_embedded": False,
        "background_plate": False,
        "texture": False,
        "selection_inputs": "development_only",
        "board_exclusion_polygon_xy_px": corners.astype(int).tolist(),
        "line_primitives": rows,
        "static_material_palette_bgr": palette,
        "future_renderer_requirement": (
            "instantiate explicit environment geometry and materials; do not use these "
            "screen-space observations as a background image or texture"
        ),
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    scene_path = output_directory / "scene_spec.json"
    rows_path = output_directory / "primitive_support_rows.json"
    atomic_write_json(scene_path, scene_document)
    atomic_write_json(
        rows_path,
        {
            "schema_version": ROWS_SCHEMA,
            "experiment_id": contract["experiment_id"],
            "rows": rows,
        },
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "source_bindings": {
            name: binding["sha256"] for name, binding in contract["sources"].items()
        },
        "partitions": {name: len(values) for name, values in partitions.items()},
        "selection": {
            "selection_inputs": "development_only",
            "validation_and_stress_used_for_selection": False,
            "stable_residual_pixel_count": int(np.sum(stable_residual)),
            "frozen_line_primitive_count": len(primitives),
            "palette_cluster_count": len(palette),
        },
        "partition_aggregate_support": partition_aggregate,
        "acceptance_gates": gates,
        "observation_specification_pass": passed,
        "target_pass_allowed": False,
        "outputs": {
            "scene_spec_path": scene_path.name,
            "scene_spec_sha256": sha256_file(scene_path),
            "primitive_support_rows_path": rows_path.name,
            "primitive_support_rows_sha256": sha256_file(rows_path),
        },
        "execution": {
            "development_frame_evaluations": len(development),
            "validation_frame_evaluations": len(partitions["validation"]),
            "stress_frame_evaluations": len(partitions["stress"]),
            "renderer_runs": 0,
            "simulator_replays": 0,
            "candidate_videos": 0,
            "image_outputs": 0,
            "texture_outputs": 0,
            "physical_pixel_composites": 0,
            "geometric_warps": 0,
            "dependency_installs": 0,
            "hardware_actions": 0,
        },
        "next_mechanism": (
            "implement_explicit_static_environment_geometry_from_pixel_free_spec_when_renderer_available"
            if passed
            else "screen_space_primitive_family_insufficient"
        ),
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    evaluate_static_environment_scene_specification_once()


if __name__ == "__main__":
    main()
