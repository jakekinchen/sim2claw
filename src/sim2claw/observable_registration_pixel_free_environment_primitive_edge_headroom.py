"""Evaluate edge-only headroom from frozen pixel-free environment vectors."""

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
from .observable_registration_static_appearance_factorization import _range_indices
from .observable_registration_temporal_pixel_similarity import _decode_video, _summary


SCHEMA = (
    "sim2claw.observable_registration_pixel_free_environment_primitive_edge_headroom_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_pixel_free_environment_primitive_edge_headroom_receipt.v1"
)
ROWS_SCHEMA = (
    "sim2claw.observable_registration_pixel_free_environment_primitive_edge_headroom_rows.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_pixel_free_environment_primitive_edge_headroom_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_pixel_free_environment_primitive_edge_headroom_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_environment_primitive_edge_headroom_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="environment primitive edge headroom")
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
        and {name: len(values) for name, values in partitions.items()}
        == {"development": 220, "validation": 180, "stress": 116}
        and set().union(*(set(values) for values in partitions.values()))
        == set(range(516)),
        "timeline partitions drifted",
    )
    counterfactual = contract["counterfactual"]
    _require(
        counterfactual["primitive_prefix_counts"] == [8, 16, 24]
        and counterfactual["line_width_px"] == 1
        and counterfactual["union_with_decoded_or58_simulator_canny_edges"] is True
        and counterfactual["evaluate_all_prefixes"] is True
        and counterfactual["selection_allowed"] is False
        and counterfactual["metric"]
        == {
            "canny_low_threshold": 50,
            "canny_high_threshold": 150,
            "tolerance_dilation_kernel_px": 3,
        },
        "counterfactual drifted",
    )
    _require(
        contract["acceptance"]["target_pass_allowed"] is False,
        "counterfactual cannot pass target",
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


def _edge_f1(
    physical: np.ndarray,
    simulator: np.ndarray,
    kernel: np.ndarray,
) -> float:
    physical_dilated = cv2.dilate(physical.astype(np.uint8), kernel) > 0
    simulator_dilated = cv2.dilate(simulator.astype(np.uint8), kernel) > 0
    denominator = int(np.sum(physical)) + int(np.sum(simulator))
    if denominator == 0:
        return 1.0
    matched = int(np.sum(physical & simulator_dilated)) + int(
        np.sum(simulator & physical_dilated)
    )
    return float(matched / denominator)


def evaluate_environment_primitive_edge_headroom_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR64 one-run receipt already exists")
    contract = load_environment_primitive_edge_headroom_contract(
        contract_path, root=root
    )
    or58 = _bound_json(
        contract["sources"]["or58_receipt"], root=root, label="OR58 receipt"
    )
    or63 = _bound_json(
        contract["sources"]["or63_closeout"], root=root, label="OR63 closeout"
    )
    scene = _bound_json(
        contract["sources"]["or63_scene_spec"], root=root, label="OR63 scene spec"
    )
    _require(
        or58["all_acceptance_gates_pass"] is False
        and or63["status"]
        == "PASS_PIXEL_FREE_STATIC_ENVIRONMENT_OBSERVATION_SPECIFICATION"
        and scene["physical_pixels_embedded"] is False
        and scene["background_plate"] is False
        and scene["texture"] is False
        and len(scene["line_primitives"]) == 24,
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
    metric = contract["counterfactual"]["metric"]
    kernel_size = int(metric["tolerance_dilation_kernel_px"])
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
    prefixes = [int(value) for value in contract["counterfactual"]["primitive_prefix_counts"]]
    vector_masks: dict[int, np.ndarray] = {}
    for prefix in prefixes:
        mask = np.zeros((480, 640), dtype=np.uint8)
        for primitive in scene["line_primitives"][:prefix]:
            x0, y0, x1, y1 = [int(value) for value in primitive["endpoints_xyxy_px"]]
            cv2.line(mask, (x0, y0), (x1, y1), 1, 1, cv2.LINE_8)
        vector_masks[prefix] = mask > 0
    rows: list[dict[str, Any]] = []
    baseline_values: list[float] = []
    prefix_values = {prefix: [] for prefix in prefixes}
    for sample_index in range(516):
        physical = _edges(physical_frames[sample_index], metric)
        simulator = _edges(simulator_frames[sample_index], metric)
        baseline = _edge_f1(physical, simulator, kernel)
        baseline_values.append(baseline)
        counterfactuals: dict[str, float] = {}
        for prefix in prefixes:
            value = _edge_f1(physical, simulator | vector_masks[prefix], kernel)
            prefix_values[prefix].append(value)
            counterfactuals[str(prefix)] = value
        rows.append(
            {
                "sample_index": sample_index,
                "baseline_tolerant_edge_f1": baseline,
                "counterfactual_tolerant_edge_f1_by_prefix": counterfactuals,
            }
        )
    reproduced_mean = float(np.mean(np.asarray(baseline_values, dtype=np.float64)))
    expected_mean = float(or58["metrics"]["tolerant_edge_f1"]["mean"])
    _require(abs(reproduced_mean - expected_mean) < 1e-12, "OR58 edge metric did not reproduce")
    timeline = contract["timeline"]
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    prefix_summaries: dict[str, Any] = {}
    for prefix in prefixes:
        partition_rows: dict[str, Any] = {}
        for name, indices in partitions.items():
            baseline = _summary([baseline_values[index] for index in indices])
            candidate = _summary([prefix_values[prefix][index] for index in indices])
            partition_rows[name] = {
                "baseline_tolerant_edge_f1": baseline,
                "counterfactual_tolerant_edge_f1": candidate,
                "absolute_mean_improvement": float(candidate["mean"])
                - float(baseline["mean"]),
            }
        full = _summary(prefix_values[prefix])
        prefix_summaries[str(prefix)] = {
            "partition_scores": partition_rows,
            "full_timeline_counterfactual_tolerant_edge_f1": full,
            "full_timeline_absolute_mean_improvement": float(full["mean"])
            - reproduced_mean,
            "remaining_gap_to_edge_gate": max(
                0.0,
                float(contract["acceptance"]["edge_gate_reference"])
                - float(full["mean"]),
            ),
            "counterfactual_edge_gate_reached": float(full["mean"])
            >= float(contract["acceptance"]["edge_gate_reference"]),
        }
    full_prefix = str(prefixes[-1])
    validation_improvement = float(
        prefix_summaries[full_prefix]["partition_scores"]["validation"]
        ["absolute_mean_improvement"]
    )
    advance = validation_improvement >= float(
        contract["acceptance"][
            "minimum_validation_absolute_mean_edge_f1_improvement"
        ]
    )
    status = (
        "PASS_PIXEL_FREE_ENVIRONMENT_PRIMITIVE_EDGE_HEADROOM_ADVANCE"
        if advance
        else "TERMINAL_LINE_PRIMITIVE_EDGE_HEADROOM_INSUFFICIENT"
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    rows_path = output_directory / "edge_headroom_rows.json"
    atomic_write_json(
        rows_path,
        {"schema_version": ROWS_SCHEMA, "experiment_id": contract["experiment_id"], "rows": rows},
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "source_bindings": {
            name: binding["sha256"] for name, binding in contract["sources"].items()
        },
        "or58_reproduction": {
            "mean_frame_tolerant_edge_f1": reproduced_mean,
            "expected_mean_frame_tolerant_edge_f1": expected_mean,
            "exact_within_1e_12": True,
        },
        "primitive_prefixes_evaluated_without_selection": prefixes,
        "prefix_summaries": prefix_summaries,
        "acceptance_gates": {
            "minimum_validation_absolute_mean_edge_f1_improvement": advance,
        },
        "mechanism_headroom_advance": advance,
        "target_pass_allowed": False,
        "outputs": {
            "edge_headroom_rows_path": rows_path.name,
            "edge_headroom_rows_sha256": sha256_file(rows_path),
        },
        "execution": {
            "frame_evaluations": 516,
            "primitive_prefixes_evaluated": len(prefixes),
            "renderer_runs": 0,
            "simulator_replays": 0,
            "candidate_videos": 0,
            "image_outputs": 0,
            "texture_outputs": 0,
            "physical_pixel_composites": 0,
            "geometric_warps": 0,
            "scene_mutations": 0,
            "validation_or_stress_selections": 0,
            "hardware_actions": 0,
        },
        "next_mechanism": (
            "implement_explicit_environment_geometry_from_or63_vectors_when_renderer_available"
            if advance
            else "expand_pixel_free_environment_primitive_family_beyond_lines"
        ),
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    evaluate_environment_primitive_edge_headroom_once()


if __name__ == "__main__":
    main()
