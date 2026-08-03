"""Render a fixed synthetic vector environment layer and score its video."""

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
from .observable_registration_edge_preserving_response_frontier import _partition_summary
from .observable_registration_static_appearance_factorization import (
    _range_indices,
    _score_candidate_video,
)
from .observable_registration_temporal_pixel_similarity import (
    _decode_video,
    _linear_similarity,
    _summary,
    _tolerant_edge_f1,
)


SCHEMA = "sim2claw.observable_registration_static_vector_environment_video_render_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_static_vector_environment_video_render_receipt.v1"
MATERIAL_SCHEMA = "sim2claw.observable_registration_static_vector_environment_material_spec.v1"
CANDIDATES_SCHEMA = "sim2claw.observable_registration_static_vector_environment_candidates.v1"
ROWS_SCHEMA = "sim2claw.observable_registration_static_vector_environment_video_metric_rows.v1"
CONTRACT_PATH = REPO_ROOT / "configs/evaluations/observable_registration_static_vector_environment_video_render_v1.json"
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_static_vector_environment_video_render_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_static_vector_environment_video_render_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="static vector environment render")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    timeline = contract["timeline"]
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    _require(
        timeline["frame_count"] == 531
        and timeline["available_physical_sample_range_inclusive"] == [0, 515]
        and timeline["missing_physical_sample_range_inclusive"] == [516, 530]
        and timeline["width_px"] == 640
        and timeline["height_px"] == 480
        and timeline["fps"] == 20.0
        and timeline["selection_may_read_only_development"] is True
        and {name: len(indices) for name, indices in partitions.items()}
        == {"development": 220, "validation": 180, "stress": 116}
        and set().union(*(set(indices) for indices in partitions.values())) == set(range(516)),
        "timeline drifted",
    )
    family = contract["candidate_family"]
    _require(
        family == {
            "stroke_width_px": [1],
            "alpha": [0.25, 0.5],
            "candidate_count": 2,
            "primitive_order": "or63_lines_then_or66_contours",
            "primitive_count": 56,
            "palette_source": "or63_scene_spec.static_material_palette_bgr",
            "palette_color_count": 6,
            "palette_assignment": "per_primitive_minimum_development_mean_absolute_error_after_alpha_blend",
            "one_palette_color_per_primitive": True,
            "one_alpha_for_all_primitives_and_frames": True,
            "minimum_development_mean_full_frame_linear_pixel_similarity": 0.80,
            "selection_rule": "maximum_development_tolerant_edge_f1_then_p10_pixel_then_mean_pixel_then_lower_alpha",
        },
        "candidate family drifted",
    )
    render = contract["render"]
    _require(
        render == {
            "base_video": "or58_candidate_video",
            "codec": "mp4v",
            "output_fps": 20.0,
            "render_all_531_frames": True,
            "score_after_video_decode": True,
            "static_screen_space_vector_layer": True,
            "physical_pixels_embedded": False,
            "background_plate": False,
            "physical_texture": False,
        },
        "render boundary drifted",
    )
    _require(contract["evaluation"]["all_five_gates_required"] is True, "full gate set relaxed")
    limits = contract["resource_boundary"]
    _require(limits["emitted_candidate_video_limit"] == 1, "video limit drifted")
    _require(not any(value for key, value in limits.items() if key != "emitted_candidate_video_limit"), "resource boundary widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _primitive_masks(
    line_scene: dict[str, Any], contour_scene: dict[str, Any], width: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for primitive in line_scene["line_primitives"]:
        mask = np.zeros((480, 640), dtype=np.uint8)
        x0, y0, x1, y1 = [int(value) for value in primitive["endpoints_xyxy_px"]]
        cv2.line(mask, (x0, y0), (x1, y1), 1, width, cv2.LINE_8)
        rows.append({"primitive_id": primitive["primitive_id"], "source_family": "or63_line", "mask": mask > 0})
    for primitive in contour_scene["curve_and_finite_shape_primitives"]:
        mask = np.zeros((480, 640), dtype=np.uint8)
        points = np.asarray(primitive["vertices_xy_px"], dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(mask, [points], True, 1, width, cv2.LINE_8)
        rows.append({"primitive_id": primitive["primitive_id"], "source_family": "or66_contour", "mask": mask > 0})
    return rows


def _fit_assignments(
    physical_frames: list[np.ndarray],
    base_frames: list[np.ndarray],
    development: list[int],
    primitives: list[dict[str, Any]],
    palette: np.ndarray,
    alpha: float,
) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    for primitive in primitives:
        mask = primitive["mask"]
        physical_values = np.concatenate([physical_frames[index][mask] for index in development]).astype(np.float32)
        base_values = np.concatenate([base_frames[index][mask] for index in development]).astype(np.float32)
        losses: list[float] = []
        for color in palette:
            predicted = np.rint((1.0 - alpha) * base_values + alpha * color).clip(0.0, 255.0)
            losses.append(float(np.mean(np.abs(physical_values - predicted))))
        selected_index = min(range(len(losses)), key=lambda index: (losses[index], index))
        assignments.append(
            {
                "primitive_id": primitive["primitive_id"],
                "source_family": primitive["source_family"],
                "palette_index": selected_index,
                "palette_bgr": [int(value) for value in palette[selected_index]],
                "development_mean_absolute_error": losses[selected_index],
            }
        )
    return assignments


def _static_layer(
    primitives: list[dict[str, Any]], assignments: list[dict[str, Any]]
) -> tuple[np.ndarray, np.ndarray]:
    layer = np.zeros((480, 640, 3), dtype=np.float32)
    union = np.zeros((480, 640), dtype=bool)
    for primitive, assignment in zip(primitives, assignments, strict=True):
        mask = primitive["mask"]
        layer[mask] = np.asarray(assignment["palette_bgr"], dtype=np.float32)
        union |= mask
    return layer, union


def _render(frame: np.ndarray, layer: np.ndarray, union: np.ndarray, alpha: float) -> np.ndarray:
    rendered = frame.copy()
    rendered[union] = np.rint(
        (1.0 - alpha) * rendered[union].astype(np.float32) + alpha * layer[union]
    ).clip(0.0, 255.0).astype(np.uint8)
    return rendered


def evaluate_static_vector_environment_video_render_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR67 one-run receipt already exists")
    contract = load_static_vector_environment_video_render_contract(contract_path, root=root)
    or55 = _bound_json(contract["sources"]["or55_contract"], root=root, label="OR55 contract")
    or26 = _bound_json(contract["sources"]["or26_receipt"], root=root, label="OR26 receipt")
    or58 = _bound_json(contract["sources"]["or58_receipt"], root=root, label="OR58 receipt")
    line_scene = _bound_json(contract["sources"]["or63_scene_spec"], root=root, label="OR63 scene")
    contour_scene = _bound_json(contract["sources"]["or66_scene_spec"], root=root, label="OR66 scene")
    or66 = _bound_json(contract["sources"]["or66_closeout"], root=root, label="OR66 closeout")
    _require(
        or26["trace_playback"]["actions_changed"] is False
        and or26["trace_playback"]["physics_rerun"] is False
        and or58["mean_and_temporal_distribution_gates_pass"] is True
        and len(line_scene["line_primitives"]) == 24
        and len(contour_scene["curve_and_finite_shape_primitives"]) == 32
        and line_scene["physical_pixels_embedded"] is False
        and contour_scene["physical_pixels_embedded"] is False
        and or66["result"]["counterfactual_edge_gate_reached"] is True,
        "predecessor boundary drifted",
    )
    physical_frames = _decode_video(
        _bound_path(contract["sources"]["physical_video"], root=root, label="physical"), width=640, height=480
    )
    base_frames = _decode_video(
        _bound_path(contract["sources"]["or58_candidate_video"], root=root, label="OR58 candidate"), width=640, height=480
    )
    _require(len(physical_frames) == len(base_frames) == 531, "decoded video length drifted")
    timeline = contract["timeline"]
    partitions = {
        name: _range_indices(timeline[f"{name}_ranges_inclusive"])
        for name in ("development", "validation", "stress")
    }
    development = partitions["development"]
    family = contract["candidate_family"]
    palette = np.rint(
        np.asarray([row["bgr"] for row in line_scene["static_material_palette_bgr"]], dtype=np.float32)
    ).clip(0.0, 255.0)
    _require(palette.shape == (6, 3), "palette drifted")
    primitives = _primitive_masks(line_scene, contour_scene, width=1)
    _require(len(primitives) == 56, "primitive count drifted")
    edge_config = or55["metric"]["edge"]
    candidates: list[dict[str, Any]] = []
    candidate_materials: dict[str, Any] = {}
    for alpha_value in family["alpha"]:
        alpha = float(alpha_value)
        assignments = _fit_assignments(
            physical_frames, base_frames, development, primitives, palette, alpha
        )
        layer, union = _static_layer(primitives, assignments)
        primary: list[float] = []
        edges: list[float] = []
        for index in development:
            rendered = _render(base_frames[index], layer, union, alpha)
            primary.append(_linear_similarity(physical_frames[index], rendered))
            edges.append(
                _tolerant_edge_f1(
                    cv2.cvtColor(physical_frames[index], cv2.COLOR_BGR2GRAY),
                    cv2.cvtColor(rendered, cv2.COLOR_BGR2GRAY),
                    edge_config,
                )
            )
        primary_summary = _summary(primary)
        edge_summary = _summary(edges)
        key = f"alpha_{alpha:.2f}"
        candidates.append(
            {
                "alpha": alpha,
                "stroke_width_px": 1,
                "development_full_frame_linear_pixel_similarity": primary_summary,
                "development_tolerant_edge_f1": edge_summary,
                "eligible_mean_target": float(primary_summary["mean"])
                >= float(family["minimum_development_mean_full_frame_linear_pixel_similarity"]),
                "rendered_pixel_count": int(np.sum(union)),
            }
        )
        candidate_materials[key] = {"assignments": assignments, "layer": layer, "union": union}
    eligible = [candidate for candidate in candidates if candidate["eligible_mean_target"]]
    selection_pool = eligible if eligible else candidates
    selected = max(
        selection_pool,
        key=lambda item: (
            float(item["development_tolerant_edge_f1"]["mean"]),
            float(item["development_full_frame_linear_pixel_similarity"]["p10"]),
            float(item["development_full_frame_linear_pixel_similarity"]["mean"]),
            -float(item["alpha"]),
        ),
    )
    selected_alpha = float(selected["alpha"])
    selected_material = candidate_materials[f"alpha_{selected_alpha:.2f}"]
    output_directory.mkdir(parents=True, exist_ok=True)
    video_path = output_directory / "simulator_vector_environment_candidate.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 20.0, (640, 480))
    _require(writer.isOpened(), "candidate video writer did not open")
    try:
        for frame in base_frames:
            writer.write(
                _render(frame, selected_material["layer"], selected_material["union"], selected_alpha)
            )
    finally:
        writer.release()
    decoded_candidate = _decode_video(video_path, width=640, height=480)
    _require(len(decoded_candidate) == 531, "candidate video decode length drifted")
    partition_scores: dict[str, Any] = {}
    for name, indices in partitions.items():
        partition_scores[name] = {
            "or58_baseline": _partition_summary(physical_frames, base_frames, indices, edge_config=edge_config),
            "decoded_candidate": _partition_summary(physical_frames, decoded_candidate, indices, edge_config=edge_config),
        }
    metrics, metric_rows, gates = _score_candidate_video(
        physical_frames, decoded_candidate, contract=contract, or26=or26, or55_contract=or55
    )
    all_pass = all(gates.values())
    status = (
        "PASS_TEMPORAL_PIXEL_SIMILARITY_TARGET_STATIC_VECTOR_VIDEO"
        if all_pass
        else "TERMINAL_STATIC_VECTOR_VIDEO_BELOW_FULL_TARGET"
    )
    material_document = {
        "schema_version": MATERIAL_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "selection_inputs": "development_only",
        "static_for_all_frames": True,
        "alpha": selected_alpha,
        "stroke_width_px": 1,
        "rendered_pixel_count": int(np.sum(selected_material["union"])),
        "physical_pixels_embedded": False,
        "background_plate": False,
        "texture": False,
        "assignments": selected_material["assignments"],
    }
    material_path = output_directory / "material_spec.json"
    candidates_path = output_directory / "candidate_table.json"
    rows_path = output_directory / "metric_rows.json"
    atomic_write_json(material_path, material_document)
    atomic_write_json(
        candidates_path,
        {
            "schema_version": CANDIDATES_SCHEMA,
            "experiment_id": contract["experiment_id"],
            "selection_inputs": "development_only",
            "eligible_candidate_count": len(eligible),
            "candidates": candidates,
            "selected": selected,
        },
    )
    atomic_write_json(rows_path, {"schema_version": ROWS_SCHEMA, "experiment_id": contract["experiment_id"], "rows": metric_rows})
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "source_bindings": {name: binding["sha256"] for name, binding in contract["sources"].items()},
        "selection": {
            "selection_inputs": "development_only",
            "candidate_count": len(candidates),
            "eligible_mean_target_candidate_count": len(eligible),
            "selected_alpha": selected_alpha,
            "selected_stroke_width_px": 1,
            "selected_rendered_pixel_count": int(np.sum(selected_material["union"])),
            "validation_and_stress_used_for_selection": False,
        },
        "partition_scores": partition_scores,
        "metrics": metrics,
        "acceptance_gates": gates,
        "all_acceptance_gates_pass": all_pass,
        "actions_and_timestamps_unchanged": True,
        "physical_pixels_embedded": False,
        "outputs": {
            "candidate_video_path": video_path.name,
            "candidate_video_sha256": sha256_file(video_path),
            "material_spec_path": material_path.name,
            "material_spec_sha256": sha256_file(material_path),
            "candidate_table_path": candidates_path.name,
            "candidate_table_sha256": sha256_file(candidates_path),
            "metric_rows_path": rows_path.name,
            "metric_rows_sha256": sha256_file(rows_path),
        },
        "execution": {
            "development_candidates_evaluated": 2,
            "static_vector_video_renders": 1,
            "emitted_candidate_videos": 1,
            "decoded_candidate_videos": 1,
            "mujoco_renderer_runs": 0,
            "simulator_replays": 0,
            "dependency_installs": 0,
            "colima_starts": 0,
            "physical_pixel_composites": 0,
            "geometric_warps": 0,
            "action_changes": 0,
            "timestamp_changes": 0,
            "state_changes": 0,
            "missing_frame_fills": 0,
            "validation_or_stress_selections": 0,
            "hardware_actions": 0,
        },
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    evaluate_static_vector_environment_video_render_once()


if __name__ == "__main__":
    main()
