#!/usr/bin/env python3
"""Evaluate receipt-bound C922 pose P2 as an added fit observation.

J/S/K/L/P2 are fit observations.  M remains retrospective diagnostic data.
The tool reuses the predecessor's exact extraction, board, camera, and full-CAD
functions, but fits one static base delta across the five-pose successor split.
It does not control hardware or promote a candidate.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.optimize import least_squares

from sim2claw.recorded_replay import _compile_model
from tools import evaluate_current_c922_board_base_registration as predecessor
from tools.evaluate_current_multiview_cad_bundle import _set_pose


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "configs/evaluations/current_c922_pose_p2_successor_v1.json"
)
ACQUISITION_CONTRACT = (
    ROOT / "configs/evaluations/current_c922_pose_p2_fit_acquisition_v1.json"
)
FIT_POSES = ("J", "S", "K", "L", "P2")
RETROSPECTIVE_POSES = ("M",)


def load_contracts() -> tuple[dict[str, Any], dict[str, Any]]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.current_c922_pose_p2_successor.v1"
        or tuple(contract["split"]["fit_poses"]) != FIT_POSES
        or tuple(contract["split"]["retrospective_diagnostic_only"])
        != RETROSPECTIVE_POSES
        or contract["split"]["future_heldout_poses"]
    ):
        raise RuntimeError("P2 successor contract changed")
    for key in ("predecessor_contract", "pose_P2_acquisition_contract"):
        source = contract["sources"][key]
        if predecessor.sha256(ROOT / source["path"]) != source["sha256"]:
            raise RuntimeError(f"successor source hash changed: {key}")

    acquisition = json.loads(ACQUISITION_CONTRACT.read_text(encoding="utf-8"))
    if (
        acquisition["status"] != "frozen_before_physical_capture"
        or tuple(acquisition["successor_fit_split"]["fit_poses"]) != FIT_POSES
        or acquisition["route"]["selection_was_frozen_before_capture"]
        is not True
    ):
        raise RuntimeError("P2 acquisition was not frozen before capture")
    predecessor_contract = predecessor.load_contract()
    return contract, predecessor_contract


def fit_base_for_poses(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    model_config: dict[str, Any],
    observations: dict[str, dict[str, Any]],
    frames: dict[str, np.ndarray],
    origin: np.ndarray,
    basis: np.ndarray,
    camera: dict[str, Any],
) -> dict[str, Any]:
    distances = {
        name: predecessor.distance_image(frames[name]) for name in FIT_POSES
    }
    points: dict[str, np.ndarray] = {}
    for name in FIT_POSES:
        _set_pose(
            model,
            data,
            model_config,
            np.asarray(observations[name]["joint_position_degrees"]),
            np.zeros(5),
        )
        points[name] = predecessor.body_hull_samples(
            model,
            data,
            origin,
            basis,
            camera,
            predecessor.BASE_BODIES,
            8,
        )
        if not len(points[name]):
            return {"status": "base_not_projected", "solutions": []}

    def residual(parameters: np.ndarray) -> np.ndarray:
        edge = np.concatenate(
            [
                predecessor.edge_values(
                    points[name], parameters, camera, distances[name]
                )
                / 8.0
                for name in FIT_POSES
            ]
        )
        prior = np.r_[
            parameters[:3] / math.radians(2.0),
            parameters[3:] / 0.01,
        ]
        return np.r_[edge, prior]

    starts = (
        np.zeros(6),
        np.asarray((0, 0, math.radians(2), 0.01, 0, 0)),
        np.asarray((0, 0, -math.radians(2), -0.01, 0, 0)),
        np.asarray((math.radians(2), 0, 0, 0, 0.01, 0)),
        np.asarray((-math.radians(2), 0, 0, 0, -0.01, 0)),
    )
    solutions = []
    for start in starts:
        result = least_squares(
            residual,
            start,
            bounds=(
                np.r_[[-math.radians(10)] * 3, [-0.05] * 3],
                np.r_[[math.radians(10)] * 3, [0.05] * 3],
            ),
            max_nfev=300,
        )
        edge = np.concatenate(
            [
                predecessor.edge_values(
                    points[name], result.x, camera, distances[name]
                )
                for name in FIT_POSES
            ]
        )
        solutions.append(
            {
                "parameters": result.x.tolist(),
                "edge_median_px": float(np.median(edge)),
                "edge_p90_px": float(np.percentile(edge, 90)),
                "cost": float(result.cost),
            }
        )
    solutions.sort(key=lambda item: item["cost"])
    near = [
        item
        for item in solutions
        if item["cost"] <= solutions[0]["cost"] * 1.05 + 1e-9
    ]
    parameters = np.asarray([item["parameters"] for item in near])
    translation_spread = (
        float(
            np.max(
                np.linalg.norm(
                    parameters[:, None, 3:] - parameters[None, :, 3:],
                    axis=2,
                )
            )
            * 1000.0
        )
        if len(parameters) > 1
        else 0.0
    )
    rotation_spread = (
        float(
            np.degrees(
                np.max(
                    np.linalg.norm(
                        parameters[:, None, :3] - parameters[None, :, :3],
                        axis=2,
                    )
                )
            )
        )
        if len(parameters) > 1
        else 0.0
    )
    selected = np.asarray(solutions[0]["parameters"])
    return {
        "status": "conditional_fit",
        "fit_poses": list(FIT_POSES),
        "selected_parameters": selected.tolist(),
        "selected_edge_median_px": solutions[0]["edge_median_px"],
        "selected_edge_p90_px": solutions[0]["edge_p90_px"],
        "near_optimum_translation_spread_mm": translation_spread,
        "near_optimum_rotation_spread_degrees": rotation_spread,
        "fit_bound_active": bool(
            np.any(np.abs(selected[:3]) > math.radians(9.99))
            or np.any(np.abs(selected[3:]) > 0.0499)
        ),
        "solutions": solutions,
    }


def hypothesis_metrics_for_poses(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    model_config: dict[str, Any],
    observations: dict[str, dict[str, Any]],
    frames: dict[str, np.ndarray],
    origin: np.ndarray,
    basis: np.ndarray,
    camera: dict[str, Any],
    base_parameters: np.ndarray,
    offsets: np.ndarray,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in (*FIT_POSES, *RETROSPECTIVE_POSES):
        _set_pose(
            model,
            data,
            model_config,
            np.asarray(observations[name]["joint_position_degrees"]),
            offsets,
        )
        points = predecessor.body_hull_samples(
            model, data, origin, basis, camera, None, 5
        )
        values = predecessor.edge_values(
            points,
            base_parameters,
            camera,
            predecessor.distance_image(frames[name]),
        )
        result[name] = {
            "sample_count": int(len(values)),
            "median_px": float(np.median(values)),
            "p90_px": float(np.percentile(values, 90)),
            "clipped_rmse_px": float(np.sqrt(np.mean(values**2))),
        }
    result["fit_aggregate"] = {
        "mean_pose_median_px": float(
            np.mean([result[name]["median_px"] for name in FIT_POSES])
        ),
        "mean_pose_p90_px": float(
            np.mean([result[name]["p90_px"] for name in FIT_POSES])
        ),
    }
    return result


def monotonic_line_evidence_union(
    supports: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    first = next(iter(supports.values()))
    result: dict[str, Any] = {
        "method": (
            "union_of_unique_seed_lattice_lines_directly_supported_by_each_"
            "frozen_observation_group"
        )
    }
    for axis in ("row", "column"):
        expected = first[f"expected_{axis}_intercepts_px"]
        evidence = []
        for index, value in enumerate(expected):
            sources = [
                name
                for name, support in supports.items()
                if any(
                    abs(value - supported) < 1e-6
                    for supported in support[
                        f"supported_{axis}_intercepts_px"
                    ]
                )
            ]
            if sources:
                evidence.append(
                    {
                        "lattice_index": index,
                        "reference_intercept_px": value,
                        "source_groups": sources,
                    }
                )
        result[f"supported_{axis}_lines"] = evidence
        result[f"strong_{axis}_line_count"] = len(evidence)
    return result


def evaluate(output_directory: Path) -> dict[str, Any]:
    cv2.ocl.setUseOpenCL(False)
    contract, predecessor_contract = load_contracts()
    frames: dict[str, np.ndarray] = {}
    extraction: dict[str, Any] = {}
    predecessor_sources = predecessor_contract["sources"]["observations"]
    for name in ("J", "S", "K", "L", "M"):
        frames[name], extraction[name] = predecessor.validate_and_extract(
            name, predecessor_sources[name]
        )
    frames["P2"], extraction["P2"] = predecessor.validate_and_extract(
        "P2", contract["sources"]["pose_P2"]
    )

    image_corners = np.asarray(
        predecessor_contract["board"]["initial_image_playing_corners_px"],
        dtype=np.float64,
    )
    p2_support = predecessor.board_line_support(
        {"P2": frames["P2"]}, image_corners
    )
    predecessor_fit_support = predecessor.board_line_support(
        {name: frames[name] for name in ("J", "S", "K", "L")},
        image_corners,
    )
    raw_fit_cluster_union = predecessor.board_line_support(
        {name: frames[name] for name in FIT_POSES}, image_corners
    )
    fit_support = monotonic_line_evidence_union(
        {
            "J_S_K_L": predecessor_fit_support,
            "P2": p2_support,
        }
    )
    p2_gray = cv2.cvtColor(frames["P2"], cv2.COLOR_BGR2GRAY)
    corner_ok, p2_corners = cv2.findChessboardCornersSB(
        p2_gray,
        (7, 7),
        flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY,
    )
    p2_chessboard = {
        "pattern": [7, 7],
        "found": bool(corner_ok),
        "corner_count": int(0 if p2_corners is None else len(p2_corners)),
    }

    manifest = json.loads(
        (
            ROOT
            / predecessor_contract["sources"]["exact_CAD_scene"]["path"]
        ).read_text(encoding="utf-8")
    )
    model_config = manifest["candidate_config"]
    model, _ = _compile_model(model_config, base_directory=None)
    data = mujoco.MjData(model)
    origin, basis = predecessor.board_frame()
    nominal_side = (
        predecessor_contract["board"]["square_side_design_prior_mm"] * 8e-3
    )

    d4_candidates = []
    for permutation in predecessor.square_symmetries():
        camera = predecessor.solve_camera(
            nominal_side, permutation, image_corners
        )
        base_fit = fit_base_for_poses(
            model,
            data,
            model_config,
            extraction,
            frames,
            origin,
            basis,
            camera,
        )
        d4_candidates.append(
            {
                "permutation": list(permutation),
                "camera": camera,
                "base": base_fit,
                "ranking_cost": (
                    base_fit["solutions"][0]["cost"]
                    if base_fit.get("solutions")
                    else math.inf
                ),
            }
        )
    d4_candidates.sort(key=lambda item: item["ranking_cost"])
    selected = d4_candidates[0]
    camera = selected["camera"]
    base_fit = selected["base"]
    base_parameters = np.asarray(base_fit["selected_parameters"])

    sensitivity = []
    for square_mm in predecessor_contract["board"][
        "sensitivity_square_side_mm"
    ]:
        item = predecessor.solve_camera(
            square_mm * 8e-3,
            tuple(selected["permutation"]),
            image_corners,
        )
        sensitivity.append(
            {
                "square_side_mm": square_mm,
                "focal_px": item["focal_px"],
                "camera_translation_norm_m": float(
                    np.linalg.norm(item["tvec_m"])
                ),
                "corner_rmse_px": item["corner_rmse_px"],
                "fit_bound_active": item["fit_bound_active"],
            }
        )

    hypotheses = {}
    for name, key in (
        ("identity", "identity_joint_zero_offsets_degrees"),
        ("stage_d", "stage_d_joint_zero_offsets_degrees"),
    ):
        hypotheses[name] = hypothesis_metrics_for_poses(
            model,
            data,
            model_config,
            extraction,
            frames,
            origin,
            basis,
            camera,
            base_parameters,
            np.asarray(predecessor_contract["fixed_hypotheses"][key]),
        )

    validation = {
        name: hypotheses[name]["M"]["p90_px"]
        for name in ("identity", "stage_d")
    }
    winner = min(validation, key=validation.get)
    loser = "stage_d" if winner == "identity" else "identity"
    winner_margin = validation[loser] - validation[winner]
    gates = contract["gates"]
    gate_results = {
        "P2_joint_frame_binding": abs(
            extraction["P2"]["joint_time_delta_ms"]
        )
        <= gates["maximum_joint_to_frame_delta_ms"],
        "P2_direct_row_support": p2_support["strong_row_line_count"]
        >= gates["minimum_directly_supported_lattice_lines_per_axis"],
        "P2_direct_column_support": p2_support["strong_column_line_count"]
        >= gates["minimum_directly_supported_lattice_lines_per_axis"],
        "fit_union_direct_row_support": fit_support["strong_row_line_count"]
        >= gates["minimum_directly_supported_lattice_lines_per_axis"],
        "fit_union_direct_column_support": fit_support[
            "strong_column_line_count"
        ]
        >= gates["minimum_directly_supported_lattice_lines_per_axis"],
        "board_camera_coordinate_fit": camera["corner_rmse_px"]
        <= gates["maximum_board_coordinate_rmse_px"],
        "camera_condition": camera["jacobian_condition_number"]
        <= gates["maximum_camera_jacobian_condition_number"],
        "camera_fit_interior": not camera["fit_bound_active"],
        "base_translation_multistart": base_fit[
            "near_optimum_translation_spread_mm"
        ]
        <= gates["maximum_base_multistart_translation_spread_mm"],
        "base_rotation_multistart": base_fit[
            "near_optimum_rotation_spread_degrees"
        ]
        <= gates["maximum_base_multistart_rotation_spread_degrees"],
        "base_fit_interior": not base_fit["fit_bound_active"],
        "retrospective_validation_winner_edge": validation[winner]
        <= gates["retrospective_validation_winner_p90_max_px"],
        "retrospective_validation_hypothesis_margin": winner_margin
        >= gates["retrospective_validation_winner_margin_min_px"],
        "independent_metric_anchor": False,
        "nonplanar_intrinsic_or_distortion_evidence": False,
        "future_heldout": bool(contract["split"]["future_heldout_poses"]),
    }
    failed = [name for name, passed in gate_results.items() if not passed]
    status = (
        "conditional_candidate_all_gates_passed"
        if not failed
        else "identifiability_failed_no_P13_candidate"
    )
    result = {
        "schema_version": "sim2claw.current_c922_pose_p2_successor.result.v1",
        "status": status,
        "proof_class": contract["proof_class"],
        "contract_sha256": predecessor.sha256(CONTRACT),
        "contract_digest": predecessor.canonical_digest(contract),
        "split": contract["split"],
        "extraction": extraction,
        "pose_P2_board_observability": p2_support,
        "pose_P2_full_7x7_detection": p2_chessboard,
        "predecessor_fit_board_observability": predecessor_fit_support,
        "raw_five_pose_cluster_union_diagnostic": raw_fit_cluster_union,
        "fit_union_board_observability": fit_support,
        "conditional_camera": camera,
        "square_side_sensitivity": sensitivity,
        "d4_candidates": d4_candidates,
        "conditional_base": base_fit,
        "hypotheses": hypotheses,
        "retrospective_validation": {
            "winner_by_p90_only": winner,
            "winner_margin_px": winner_margin,
            "identity_p90_px": validation["identity"],
            "stage_d_p90_px": validation["stage_d"],
            "promotion_interpretation": (
                "none_without_all_metric_nonplanar_and_future_heldout_gates"
            ),
        },
        "gate_results": gate_results,
        "failed_gates": failed,
        "exact_remaining_blockers": [
            "P2 direct support for at least seven unique playing-lattice lines on each axis",
            "shared board-camera corner fit below the frozen error gate without active parameter bounds",
            "one shared base fit with no active search bounds",
            "independently measured board square side or another metric anchor",
            "nonplanar intrinsic or distortion calibration",
            "one unopened future heldout pose captured after successor candidate freeze",
        ],
        "authority": contract["authority"],
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_directory / "P2-exact.png"), frames["P2"])
    (output_directory / "evaluation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "runs/c922-board-base-registration/"
        "20260726-current-c922-pose-p2-successor-v1",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate(args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
