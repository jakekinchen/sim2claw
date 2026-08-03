"""Camera-only fit from four static development initial frames."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import differential_evolution

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_development_shared_camera_baseline import _summary
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    render_capability_frame,
    sha256_file,
)
from .observable_registration_temporal_pixel_similarity import (
    _linear_similarity,
    _tolerant_edge_f1,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_development_initial_shared_3d_camera_fit_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_development_initial_shared_3d_camera_fit_v1"


def camera_from_vector(vector: np.ndarray) -> dict[str, Any]:
    target = np.asarray(vector[:3], dtype=np.float64)
    azimuth = np.deg2rad(float(vector[3]))
    elevation = np.deg2rad(float(vector[4]))
    distance = float(vector[5])
    direction = np.asarray(
        [
            np.cos(elevation) * np.cos(azimuth),
            np.cos(elevation) * np.sin(azimuth),
            np.sin(elevation),
        ],
        dtype=np.float64,
    )
    return {
        "name": "or73_shared_development_camera",
        "position": (target + distance * direction).tolist(),
        "target": target.tolist(),
        "fov_degrees": float(vector[6]),
    }


def _read_initial_physical_frame(path: Path, *, width: int, height: int) -> np.ndarray:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"cannot open development video: {path}")
    ok, frame = capture.read()
    capture.release()
    if not ok or frame.shape != (480, 640, 3):
        raise ValueError("development initial frame unavailable or shape drifted")
    oriented = cv2.flip(frame, -1)
    return cv2.resize(oriented, (width, height), interpolation=cv2.INTER_AREA)


def _render(
    scene: dict[str, Any], trace: dict[str, Any], camera: dict[str, Any], *, width: int, height: int, background_rgb: list[int]
) -> np.ndarray:
    candidate_scene = dict(scene)
    candidate_scene["suggested_camera"] = camera
    renderer_contract = {
        "renderer": {
            "width_px": width,
            "height_px": height,
            "recognized_geom_types": ["plane", "box", "sphere", "ellipsoid", "cylinder", "capsule", "mesh"],
            "background_rgb": background_rgb,
        },
        "sources": {"development_state_trace": {"frame_index": 0}},
    }
    one_frame = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
    frame, _ = render_capability_frame(candidate_scene, one_frame, renderer_contract)
    return frame


def _metrics(physical: np.ndarray, simulator: np.ndarray, edge: dict[str, Any]) -> dict[str, float]:
    linear = _linear_similarity(physical, simulator)
    edge_f1 = _tolerant_edge_f1(
        cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
        cv2.cvtColor(simulator, cv2.COLOR_BGR2GRAY),
        edge,
    )
    return {
        "full_frame_linear_pixel_similarity": linear,
        "tolerant_edge_f1": edge_f1,
        "objective": 0.8 * edge_f1 + 0.2 * linear,
    }


def fit_once(
    contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR73 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    baseline_contract = json.loads((REPO_ROOT / contract["sources"]["or72_contract"]["path"]).read_text())
    episodes = baseline_contract["episodes"]
    if len(episodes) != 4 or any(episode["split_role"] != "development" for episode in episodes):
        raise ValueError("development episode boundary drifted")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    for episode in episodes:
        for binding in (episode["physical_video"], episode["state_trace"]):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"episode source hash mismatch: {binding['path']}")

    search = contract["search"]
    search_width = int(search["search_width_px"])
    search_height = int(search["search_height_px"])
    physical_search: list[np.ndarray] = []
    traces: list[dict[str, Any]] = []
    for episode in episodes:
        physical_search.append(
            _read_initial_physical_frame(
                REPO_ROOT / episode["physical_video"]["path"],
                width=search_width,
                height=search_height,
            )
        )
        traces.append(json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text()))

    edge = contract["metric"]["edge"]
    background = contract["renderer"]["background_rgb"]
    evaluation_count = 0
    best_history: list[dict[str, Any]] = []
    best_score = -np.inf

    def evaluate_vector(vector: np.ndarray) -> tuple[float, list[dict[str, float]]]:
        camera = camera_from_vector(vector)
        values: list[dict[str, float]] = []
        for physical, trace in zip(physical_search, traces, strict=True):
            simulator = _render(scene, trace, camera, width=search_width, height=search_height, background_rgb=background)
            values.append(_metrics(physical, simulator, edge))
        return float(np.mean([value["objective"] for value in values])), values

    def objective(vector: np.ndarray) -> float:
        nonlocal evaluation_count, best_score
        score, values = evaluate_vector(vector)
        evaluation_count += 1
        if score > best_score:
            best_score = score
            best_history.append(
                {
                    "evaluation_count": evaluation_count,
                    "score": score,
                    "vector": np.asarray(vector, dtype=np.float64).tolist(),
                    "mean_edge_f1": float(np.mean([value["tolerant_edge_f1"] for value in values])),
                    "mean_full_frame_similarity": float(np.mean([value["full_frame_linear_pixel_similarity"] for value in values])),
                }
            )
        return -score

    default_camera = scene["suggested_camera"]
    default_metrics = [
        _metrics(
            physical,
            _render(scene, trace, default_camera, width=search_width, height=search_height, background_rgb=background),
            edge,
        )
        for physical, trace in zip(physical_search, traces, strict=True)
    ]
    result = differential_evolution(
        objective,
        bounds=[tuple(float(value) for value in bound) for bound in contract["camera_family"]["bounds"]],
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
        raise RuntimeError("camera search exceeded the frozen evaluation budget")
    selected_vector = np.asarray(result.x, dtype=np.float64)
    selected_camera = camera_from_vector(selected_vector)
    selected_score, selected_search_metrics = evaluate_vector(selected_vector)

    output_directory.mkdir(parents=True, exist_ok=True)
    output_width = int(contract["renderer"]["output_width_px"])
    output_height = int(contract["renderer"]["output_height_px"])
    final_rows: list[dict[str, Any]] = []
    for episode, trace in zip(episodes, traces, strict=True):
        physical = _read_initial_physical_frame(
            REPO_ROOT / episode["physical_video"]["path"],
            width=output_width,
            height=output_height,
        )
        simulator = _render(scene, trace, selected_camera, width=output_width, height=output_height, background_rgb=background)
        ok, encoded = cv2.imencode(".png", simulator, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if not ok:
            raise RuntimeError("failed to encode selected camera image")
        image_path = output_directory / f"{episode['recording_id']}.png"
        image_path.write_bytes(encoded.tobytes())
        final_rows.append(
            {
                "recording_id": episode["recording_id"],
                "metrics": _metrics(physical, simulator, edge),
                "candidate_image": {
                    "path": str(image_path.relative_to(REPO_ROOT)),
                    "sha256": sha256_file(image_path),
                },
            }
        )

    default_mean_edge = float(np.mean([value["tolerant_edge_f1"] for value in default_metrics]))
    default_mean_linear = float(np.mean([value["full_frame_linear_pixel_similarity"] for value in default_metrics]))
    selected_mean_edge = float(np.mean([value["tolerant_edge_f1"] for value in selected_search_metrics]))
    selected_mean_linear = float(np.mean([value["full_frame_linear_pixel_similarity"] for value in selected_search_metrics]))
    acceptance = contract["acceptance"]
    gates = {
        "mean_edge_improvement": selected_mean_edge - default_mean_edge >= acceptance["minimum_selected_minus_default_mean_edge_f1"],
        "mean_full_frame_not_worse": selected_mean_linear - default_mean_linear >= acceptance["minimum_selected_minus_default_mean_full_frame_similarity"],
        "each_episode_objective_not_worse": all(selected["objective"] >= default["objective"] for selected, default in zip(selected_search_metrics, default_metrics, strict=True)),
        "one_shared_vector": len(selected_vector) == 7,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_development_initial_shared_3d_camera_fit_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_SHARED_3D_CAMERA_STATIC_DEVELOPMENT_ADVANCE" if passed else "TERMINAL_SHARED_3D_CAMERA_STATIC_FIT_GATE_FAILED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "selected": {
            "parameter_order": contract["camera_family"]["parameter_order"],
            "vector": selected_vector.tolist(),
            "camera": selected_camera,
            "search_objective": selected_score,
            "search_metrics_by_episode": [
                {"recording_id": episode["recording_id"], **metrics}
                for episode, metrics in zip(episodes, selected_search_metrics, strict=True)
            ],
            "final_metrics_by_episode": final_rows,
        },
        "default": {
            "camera": default_camera,
            "search_metrics_by_episode": [
                {"recording_id": episode["recording_id"], **metrics}
                for episode, metrics in zip(episodes, default_metrics, strict=True)
            ],
        },
        "summary": {
            "default_mean_edge_f1": default_mean_edge,
            "selected_mean_edge_f1": selected_mean_edge,
            "mean_edge_f1_improvement": selected_mean_edge - default_mean_edge,
            "default_mean_full_frame_similarity": default_mean_linear,
            "selected_mean_full_frame_similarity": selected_mean_linear,
            "mean_full_frame_similarity_improvement": selected_mean_linear - default_mean_linear,
            "selected_final_mean_full_frame_similarity": float(np.mean([row["metrics"]["full_frame_linear_pixel_similarity"] for row in final_rows])),
            "selected_final_mean_edge_f1": float(np.mean([row["metrics"]["tolerant_edge_f1"] for row in final_rows])),
        },
        "optimizer": {
            "candidate_evaluations": evaluation_count,
            "search_renders": evaluation_count * 4,
            "success_flag": bool(result.success),
            "message": str(result.message),
            "best_history": best_history,
        },
        "gates": gates,
        "execution": {
            "development_physical_video_decodes": 4,
            "development_physical_frames_for_fit": 4,
            "development_state_trace_reads": 4,
            "final_renders": 4,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "candidate_videos": 0,
            "simulator_replays": 0,
            "appearance_fits": 0,
            "time_fits": 0,
            "state_or_physics_fits": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "prohibited_candidate_inputs_read": [],
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_SELECTED_CAMERA_AND_RUN_FULL_DEVELOPMENT_TIMELINE" if passed else "DO_NOT_ADVANCE_CAMERA_FAMILY",
        "next_transition": "freeze_or74_selected_camera_full_development_timeline" if passed else "diagnose_camera_family_without_validation_or_heldout",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(fit_once(), sort_keys=True))
