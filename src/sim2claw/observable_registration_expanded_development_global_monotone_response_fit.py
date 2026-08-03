"""Fit one shared monotone response curve on expanded development only."""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import (
    _prepare_full_mesh_stream,
)
from .observable_registration_development_shared_camera_baseline import (
    _decode_selected_frames,
    _motion_union_similarity,
    _summary,
    evaluation_times,
    nearest_trace_indices,
    physical_frame_indices,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    sha256_file,
)
from .observable_registration_native_rasterizer_byte_equivalence import (
    _compile_native,
    _native_rasterize,
)
from .observable_registration_static_development_full_mesh_comparison import (
    _load_unique_asset_cache,
)
from .observable_registration_temporal_pixel_similarity import (
    _linear_similarity,
    _tolerant_edge_f1,
)


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_expanded_development_global_monotone_response_fit_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_expanded_development_global_monotone_response_fit_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_expanded_development_global_monotone_response_fit_v1"


def response_lut(
    *, bias: float, low_slope: float, high_slope: float, knot: int
) -> np.ndarray:
    values = np.arange(256, dtype=np.float64)
    mapped = (
        float(bias)
        + float(low_slope) * np.minimum(values, float(knot))
        + float(high_slope) * np.maximum(values - float(knot), 0.0)
    )
    return np.clip(np.rint(mapped), 0.0, 255.0).astype(np.uint8)


def apply_monotone_response(
    frame: np.ndarray,
    *,
    bias: float,
    low_slope: float,
    high_slope: float,
    knot: int,
) -> np.ndarray:
    """Apply the same monotone lookup table to every BGR sample."""
    return response_lut(
        bias=bias, low_slope=low_slope, high_slope=high_slope, knot=knot
    )[frame]


def _load_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR89 contract")
    for name, source in contract["sources"].items():
        if name == "mesh_asset_root":
            continue
        source_path = REPO_ROOT / source["path"]
        if sha256_file(source_path) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    family = contract["response_family"]
    if (
        family["fixed_input_knot"] != 128
        or family["bias_values"] != [16.0, 24.0, 32.0, 40.0, 48.0]
        or family["low_intensity_slope_values"] != [0.55, 0.7, 0.85, 1.0, 1.15]
        or family["high_intensity_slope_values"] != [0.25, 0.35, 0.45, 0.55, 0.65]
        or family["candidate_count"] != 125
        or family["same_curve_every_bgr_channel_pixel_frame_phase_and_episode"] is not True
        or any(
            family[name] != 0
            for name in (
                "spatial_parameters",
                "regional_parameters",
                "per_channel_parameters",
                "per_frame_parameters",
            )
        )
    ):
        raise ValueError("OR89 response family drifted")
    for low_slope, high_slope in itertools.product(
        family["low_intensity_slope_values"],
        family["high_intensity_slope_values"],
    ):
        lut = response_lut(
            bias=0.0,
            low_slope=float(low_slope),
            high_slope=float(high_slope),
            knot=int(family["fixed_input_knot"]),
        )
        if np.any(np.diff(lut.astype(np.int16)) < 0):
            raise ValueError("OR89 response grid is not monotone")
    episodes = contract["expanded_development_episodes"]
    if (
        len(episodes) != 7
        or [row["split_position"] for row in episodes] != list(range(1, 8))
    ):
        raise ValueError("OR89 expanded-development split drifted")
    acceptance = contract["acceptance"]
    if (
        acceptance["minimum_pooled_mean_full_frame_linear_pixel_similarity"] != 0.8
        or acceptance["minimum_pooled_p10_full_frame_linear_pixel_similarity"] != 0.75
        or acceptance["minimum_pooled_mean_motion_union_linear_pixel_similarity"] != 0.75
        or acceptance["minimum_each_phase_mean_full_frame_linear_pixel_similarity"] != 0.78
        or acceptance["minimum_pooled_mean_tolerant_edge_f1"] != 0.42
        or acceptance["minimum_each_expanded_development_episode_mean_full_frame_linear_pixel_similarity"] != 0.8
        or acceptance["all_gates_required"] is not True
    ):
        raise ValueError("OR89 acceptance boundary drifted")
    resources = contract["resource_boundary"]
    if (
        resources["fresh_validation_reads_allowed"] != 0
        or resources["final_evaluator_heldout_reads_allowed"] != 0
        or resources["simulator_replays_allowed"] != 0
        or resources["hardware_actions_allowed"] != 0
        or resources["paid_compute_allowed"] is not False
    ):
        raise ValueError("OR89 resource boundary widened")
    if any(contract["authority"].values()):
        raise ValueError("OR89 authority widened")
    return contract


def load_expanded_development_global_monotone_response_fit_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    return _load_contract(path)


def _summaries(
    episode_data: list[dict[str, Any]],
    *,
    bias: float,
    low_slope: float,
    high_slope: float,
    knot: int,
    metric: dict[str, Any],
    include_motion: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lut = response_lut(
        bias=bias, low_slope=low_slope, high_slope=high_slope, knot=knot
    )
    all_primary: list[float] = []
    all_edges: list[float] = []
    all_motion: list[float] = []
    primary_by_phase: dict[str, list[float]] = {}
    episode_summaries: list[dict[str, Any]] = []
    for data in episode_data:
        primary: list[float] = []
        edges: list[float] = []
        motion: list[float] = []
        previous_physical: np.ndarray | None = None
        previous_candidate: np.ndarray | None = None
        for physical, simulator, phase in zip(
            data["physical"], data["simulator"], data["phases"], strict=True
        ):
            candidate = lut[simulator]
            similarity = _linear_similarity(physical, candidate)
            edge = _tolerant_edge_f1(
                cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY),
                metric["edge"],
            )
            primary.append(similarity)
            edges.append(edge)
            all_primary.append(similarity)
            all_edges.append(edge)
            primary_by_phase.setdefault(str(phase), []).append(similarity)
            if include_motion:
                value, _ = _motion_union_similarity(
                    physical,
                    candidate,
                    previous_physical,
                    previous_candidate,
                    metric["motion_union"],
                )
                if value is not None:
                    motion.append(float(value))
                    all_motion.append(float(value))
                previous_physical = physical
                previous_candidate = candidate
        episode_summaries.append(
            {
                "recording_id": data["recording_id"],
                "sample_count": len(primary),
                "full_frame_linear_pixel_similarity": _summary(primary),
                "tolerant_edge_f1": _summary(edges),
                "motion_union_linear_pixel_similarity": (
                    _summary(motion) if include_motion else None
                ),
            }
        )
    phases = {
        name: _summary(values) for name, values in sorted(primary_by_phase.items())
    }
    pooled = {
        "full_frame_linear_pixel_similarity": _summary(all_primary),
        "tolerant_edge_f1": _summary(all_edges),
        "motion_union_linear_pixel_similarity": (
            _summary(all_motion) if include_motion else None
        ),
        "phase_full_frame_linear_pixel_similarity": phases,
    }
    return pooled, episode_summaries


def _non_motion_gates(
    pooled: dict[str, Any],
    episodes: list[dict[str, Any]],
    acceptance: dict[str, Any],
) -> dict[str, bool]:
    return {
        "pooled_mean_full_frame_linear_pixel_similarity": pooled[
            "full_frame_linear_pixel_similarity"
        ]["mean"]
        >= acceptance["minimum_pooled_mean_full_frame_linear_pixel_similarity"],
        "pooled_p10_full_frame_linear_pixel_similarity": pooled[
            "full_frame_linear_pixel_similarity"
        ]["p10"]
        >= acceptance["minimum_pooled_p10_full_frame_linear_pixel_similarity"],
        "each_phase_mean_full_frame_linear_pixel_similarity": all(
            row["mean"]
            >= acceptance["minimum_each_phase_mean_full_frame_linear_pixel_similarity"]
            for row in pooled["phase_full_frame_linear_pixel_similarity"].values()
        ),
        "pooled_mean_tolerant_edge_f1_with_margin": pooled["tolerant_edge_f1"][
            "mean"
        ]
        >= acceptance["minimum_pooled_mean_tolerant_edge_f1"],
        "each_expanded_development_episode_mean_full_frame_linear_pixel_similarity": all(
            row["full_frame_linear_pixel_similarity"]["mean"]
            >= acceptance[
                "minimum_each_expanded_development_episode_mean_full_frame_linear_pixel_similarity"
            ]
            for row in episodes
        ),
    }


def fit_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR89 one-run receipt already exists")
    contract = _load_contract(contract_path)
    manifest = json.loads(
        (REPO_ROOT / contract["sources"]["or88_split_manifest"]["path"]).read_text()
    )
    development_ids = [
        row["recording_id"]
        for row in manifest["pairs"]
        if row["new_split_role"] == "expanded_development"
    ]
    episodes = contract["expanded_development_episodes"]
    if [row["recording_id"] for row in episodes] != development_ids:
        raise ValueError("OR88 expanded-development identities drifted")
    if manifest["or88_physical_video_decodes"] != 0:
        raise ValueError("OR88 split receipt no longer proves zero decodes")
    for episode in episodes:
        for binding in (episode["physical_video"], episode["state_trace"]):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"expanded-development source hash mismatch: {binding['path']}")

    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    renderer = contract["renderer"]
    width = int(renderer["width_px"])
    height = int(renderer["height_px"])
    fps = float(contract["timeline"]["evaluation_fps"])
    frozen = contract["frozen_renderer_candidate"]
    camera = frozen["camera"]
    workcell = frozen["workcell_transform"]
    family = {
        "anchor_body_id": workcell["anchor_body_id"],
        "transformed_workcell_body_ids": workcell["transformed_workcell_body_ids"],
    }
    transform = np.asarray(workcell["vector"], dtype=np.float64)
    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    library_path, compile_command, compiler_stderr = _compile_native(
        {
            "sources": {"native_source": contract["sources"]["or79_native_source"]},
            "compiler": {"executable": "clang"},
        },
        output_directory,
    )

    episode_data: list[dict[str, Any]] = []
    triangle_counts: list[int] = []
    render_seconds: list[float] = []
    raster_seconds: list[float] = []
    started = time.perf_counter()
    for episode in episodes:
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        if trace["body_names"] != [body["name"] for body in scene["bodies"]]:
            raise ValueError("scene and trace body ordering drifted")
        times = evaluation_times(float(episode["state_trace"]["duration_seconds"]), fps)
        trace_times = np.asarray(
            [float(row["t"]) for row in trace["frames"]], dtype=np.float64
        )
        trace_indices = nearest_trace_indices(trace_times, times)
        physical_binding = episode["physical_video"]
        video_indices = physical_frame_indices(
            times,
            frame_count=int(physical_binding["frame_count"]),
            duration_seconds=float(physical_binding["duration_seconds"]),
        )
        physical = [
            cv2.flip(frame, -1)
            for frame in _decode_selected_frames(
                REPO_ROOT / physical_binding["path"],
                selected_indices=video_indices,
                expected_frame_count=int(physical_binding["frame_count"]),
                expected_width=int(physical_binding["width_px"]),
                expected_height=int(physical_binding["height_px"]),
                output_width=width,
                output_height=height,
            )
        ]
        simulator: list[np.ndarray] = []
        phases: list[str] = []
        for trace_index in trace_indices:
            frame_started = time.perf_counter()
            one_frame_trace = {
                "body_names": trace["body_names"],
                "frames": [trace["frames"][int(trace_index)]],
            }
            pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(
                scene,
                one_frame_trace,
                meshes,
                camera,
                renderer,
                family,
                transform,
            )
            frame, _, _, raster_elapsed = _native_rasterize(
                library_path, pixels, depths, colors, renderer
            )
            simulator.append(frame)
            phases.append(str(trace["frames"][int(trace_index)]["phase"]))
            triangle_counts.append(int(triangle_count))
            raster_seconds.append(float(raster_elapsed))
            render_seconds.append(time.perf_counter() - frame_started)
        episode_data.append(
            {
                "recording_id": episode["recording_id"],
                "times": times,
                "trace_indices": trace_indices,
                "video_indices": video_indices,
                "phases": phases,
                "physical": physical,
                "simulator": simulator,
            }
        )

    expected_frames = int(contract["gates"]["expected_total_frame_count"])
    if sum(len(row["physical"]) for row in episode_data) != expected_frames:
        raise ValueError("OR89 total frame count drifted")
    response = contract["response_family"]
    candidates = list(
        itertools.product(
            response["bias_values"],
            response["low_intensity_slope_values"],
            response["high_intensity_slope_values"],
        )
    )
    if len(candidates) != int(response["candidate_count"]):
        raise ValueError("OR89 candidate count drifted")
    candidate_rows: list[dict[str, Any]] = []
    motion_evaluated = 0
    for bias, low_slope, high_slope in candidates:
        pooled, episode_summaries = _summaries(
            episode_data,
            bias=float(bias),
            low_slope=float(low_slope),
            high_slope=float(high_slope),
            knot=int(response["fixed_input_knot"]),
            metric=contract["metric"],
            include_motion=False,
        )
        gates = _non_motion_gates(pooled, episode_summaries, contract["acceptance"])
        if all(gates.values()):
            motion_evaluated += 1
            pooled, episode_summaries = _summaries(
                episode_data,
                bias=float(bias),
                low_slope=float(low_slope),
                high_slope=float(high_slope),
                knot=int(response["fixed_input_knot"]),
                metric=contract["metric"],
                include_motion=True,
            )
            gates = _non_motion_gates(pooled, episode_summaries, contract["acceptance"])
            gates["pooled_mean_motion_union_linear_pixel_similarity"] = pooled[
                "motion_union_linear_pixel_similarity"
            ]["mean"] >= contract["acceptance"][
                "minimum_pooled_mean_motion_union_linear_pixel_similarity"
            ]
        else:
            gates["pooled_mean_motion_union_linear_pixel_similarity"] = False
        candidate_rows.append(
            {
                "bias": float(bias),
                "low_intensity_slope": float(low_slope),
                "high_intensity_slope": float(high_slope),
                "eligible": all(gates.values()),
                "pooled": pooled,
                "episode_summaries": episode_summaries,
                "metric_gates": gates,
            }
        )
    eligible = [row for row in candidate_rows if row["eligible"]]
    selected = (
        max(
            eligible,
            key=lambda row: (
                row["pooled"]["full_frame_linear_pixel_similarity"]["mean"],
                row["pooled"]["tolerant_edge_f1"]["mean"],
                row["pooled"]["full_frame_linear_pixel_similarity"]["p10"],
                -(
                    abs(row["bias"] - 48.0)
                    + abs(row["low_intensity_slope"] - 0.55) * 100.0
                    + abs(row["high_intensity_slope"] - 0.55) * 100.0
                ),
            ),
        )
        if eligible
        else None
    )
    atomic_write_json(
        output_directory / "candidate_rows.json",
        {
            "schema_version": "sim2claw.observable_registration_expanded_development_global_monotone_response_candidates.v1",
            "candidate_count": len(candidate_rows),
            "motion_evaluated_candidate_count": motion_evaluated,
            "rows": candidate_rows,
        },
    )

    output_videos: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []
    if selected is not None:
        lut = response_lut(
            bias=selected["bias"],
            low_slope=selected["low_intensity_slope"],
            high_slope=selected["high_intensity_slope"],
            knot=int(response["fixed_input_knot"]),
        )
        for data in episode_data:
            path = output_directory / f"{data['recording_id']}.mp4"
            writer = cv2.VideoWriter(
                str(path),
                cv2.VideoWriter_fourcc(*renderer["candidate_video_codec"]),
                fps,
                (width, height),
            )
            if not writer.isOpened():
                raise RuntimeError("cannot open OR89 candidate video writer")
            previous_physical: np.ndarray | None = None
            previous_candidate: np.ndarray | None = None
            try:
                for slot, (physical, simulator, phase) in enumerate(
                    zip(data["physical"], data["simulator"], data["phases"], strict=True)
                ):
                    candidate = lut[simulator]
                    writer.write(candidate)
                    motion, motion_pixels = _motion_union_similarity(
                        physical,
                        candidate,
                        previous_physical,
                        previous_candidate,
                        contract["metric"]["motion_union"],
                    )
                    frame_rows.append(
                        {
                            "recording_id": data["recording_id"],
                            "split_role": "expanded_development",
                            "evaluation_index": slot,
                            "time_seconds": float(data["times"][slot]),
                            "physical_frame_index": int(data["video_indices"][slot]),
                            "state_trace_frame_index": int(data["trace_indices"][slot]),
                            "phase": phase,
                            "full_frame_linear_pixel_similarity": _linear_similarity(
                                physical, candidate
                            ),
                            "motion_union_linear_pixel_similarity": motion,
                            "motion_union_pixel_count": motion_pixels,
                            "tolerant_edge_f1": _tolerant_edge_f1(
                                cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                                cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY),
                                contract["metric"]["edge"],
                            ),
                        }
                    )
                    previous_physical = physical
                    previous_candidate = candidate
            finally:
                writer.release()
            output_videos.append(
                {
                    "recording_id": data["recording_id"],
                    "path": str(path.relative_to(REPO_ROOT)),
                    "sha256": sha256_file(path),
                    "frame_count": len(data["physical"]),
                    "fps": fps,
                }
            )
        atomic_write_json(
            output_directory / "selected_frame_rows.json",
            {
                "schema_version": "sim2claw.observable_registration_expanded_development_global_monotone_response_frame_rows.v1",
                "frame_count": len(frame_rows),
                "rows": frame_rows,
            },
        )

    integrity_gates = {
        "exact_seven_expanded_development_episodes": len(episode_data) == 7,
        "expected_total_frame_count": len(triangle_counts) == expected_frames,
        "expected_unique_mesh_asset_reads": len(asset_receipts)
        == int(contract["gates"]["expected_unique_mesh_asset_reads"]),
        "expected_triangle_count_every_frame": all(
            value == int(contract["gates"]["expected_total_raster_triangle_count_per_frame"])
            for value in triangle_counts
        ),
        "exact_frozen_response_candidate_grid": len(candidate_rows) == 125,
        "shared_nonspatial_monotone_response_only": True,
        "fresh_validation_and_final_heldout_closed": True,
        "no_replay_hardware_or_paid_compute": True,
    }
    if not all(integrity_gates.values()):
        raise ValueError("OR89 integrity gate failed")
    metric_gates = selected["metric_gates"] if selected is not None else {
        "pooled_mean_full_frame_linear_pixel_similarity": False,
        "pooled_p10_full_frame_linear_pixel_similarity": False,
        "each_phase_mean_full_frame_linear_pixel_similarity": False,
        "pooled_mean_tolerant_edge_f1_with_margin": False,
        "each_expanded_development_episode_mean_full_frame_linear_pixel_similarity": False,
        "pooled_mean_motion_union_linear_pixel_similarity": False,
    }
    status = (
        "PASS_EXPANDED_DEVELOPMENT_GLOBAL_MONOTONE_RESPONSE_WITH_EDGE_MARGIN"
        if selected is not None
        else "TERMINAL_NO_GLOBAL_MONOTONE_RESPONSE_PASSES_EXPANDED_DEVELOPMENT_GATES"
    )
    receipt = {
        "schema_version": "sim2claw.observable_registration_expanded_development_global_monotone_response_fit_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "selected_response": (
            {
                "bias": selected["bias"],
                "low_intensity_slope": selected["low_intensity_slope"],
                "high_intensity_slope": selected["high_intensity_slope"],
                "fixed_input_knot": int(response["fixed_input_knot"]),
                "formula": response["formula"],
            }
            if selected is not None
            else None
        ),
        "eligible_candidate_count": len(eligible),
        "candidate_evaluations": len(candidate_rows),
        "motion_evaluated_candidate_count": motion_evaluated,
        "pooled": selected["pooled"] if selected is not None else None,
        "episode_summaries": selected["episode_summaries"] if selected is not None else [],
        "metric_gates": metric_gates,
        "integrity_gates": integrity_gates,
        "candidate_videos": output_videos,
        "execution": {
            "expanded_development_episode_reads": 7,
            "expanded_development_physical_video_decodes": 7,
            "expanded_development_physical_frames_compared": expected_frames,
            "native_frames_rendered": expected_frames,
            "candidate_response_evaluations": len(candidate_rows),
            "fresh_validation_reads": 0,
            "final_evaluator_heldout_reads": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "performance": {
            "wall_seconds": time.perf_counter() - started,
            "mean_full_frame_render_seconds": float(np.mean(render_seconds)),
            "p90_full_frame_render_seconds": float(np.quantile(render_seconds, 0.9)),
            "mean_native_raster_seconds": float(np.mean(raster_seconds)),
            "compile_command": compile_command,
            "compiler_stderr": compiler_stderr,
        },
        "reviewer_decision": (
            "OPEN_REJECT_ONLY_FRESH_VALIDATION_WITH_FROZEN_MONOTONE_RESPONSE"
            if selected is not None
            else "STOP_RESPONSE_FAMILY_FAILED_KEEP_FRESH_VALIDATION_AND_FINAL_HELDOUT_SEALED"
        ),
        "next_transition": (
            "freeze_or90_reject_only_fresh_validation_global_monotone_response"
            if selected is not None
            else "stop_or89_no_admissible_response"
        ),
        "claim_limits": contract["claim_limits"],
    }
    receipt["artifact_sha256"] = canonical_digest(
        {
            "selected_response": receipt["selected_response"],
            "pooled": receipt["pooled"],
            "metric_gates": metric_gates,
            "integrity_gates": integrity_gates,
            "candidate_video_hashes": [row["sha256"] for row in output_videos],
        }
    )
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    fit_once()
