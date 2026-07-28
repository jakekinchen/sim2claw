#!/usr/bin/env python3
"""Fit one Pi camera-only refresh and score frozen geometric held-out stages."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import least_squares

from tools.fit_pi_current_three_link_bundle import ThreeLinkBundle


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_PATH = Path(__file__).resolve()
PROJECTION_TOOL_PATH = ROOT / "tools/fit_pi_current_three_link_bundle.py"
CONTRACT_SCHEMA = "sim2claw.pi_camera_extrinsic_refresh_contract.v1"
CANDIDATE_SCHEMA = "sim2claw.pi_camera_extrinsic_refresh_candidate.v1"
EVALUATION_SCHEMA = "sim2claw.pi_camera_extrinsic_refresh_evaluation.v1"
DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected object in {path}")
    return value


def _write_once(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _bound_path(specification: dict[str, Any], label: str) -> Path:
    path = _path(str(specification["path"]))
    if not path.is_file() or sha256(path) != specification["sha256"]:
        raise RuntimeError(f"{label} path or SHA changed")
    return path


def load_contract(path: Path) -> dict[str, Any]:
    contract = _read(path.resolve())
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise RuntimeError("unexpected camera-refresh contract schema")
    _bound_path(contract["source_candidate"], "source candidate")
    _bound_path(contract["packet"], "packet")
    fit = contract["fit_observation"]
    _bound_path(
        {
            "path": fit["execution_receipt_path"],
            "sha256": fit["execution_receipt_sha256"],
        },
        "fit execution",
    )
    _bound_path(
        {"path": fit["pi_image_path"], "sha256": fit["pi_image_sha256"]},
        "fit Pi image",
    )
    if (
        fit.get("fit_tag_ids") != [1, 2]
        or fit.get("diagnostic_excluded_tag_ids") != [0]
        or contract.get("fit_scope", {}).get("fit_on_heldout_stages_forbidden")
        is not True
        or contract.get("authority", {}).get("camera_extrinsic_promotion")
        is not False
    ):
        raise RuntimeError("camera-refresh scope or authority changed")
    return contract


def detect_tags(path: Path) -> dict[int, np.ndarray]:
    image = cv2.imread(str(path))
    if image is None or image.shape[:2] != (864, 1536):
        raise RuntimeError(f"invalid Pi image: {path}")
    corners, identifiers, _ = cv2.aruco.ArucoDetector(DICTIONARY).detectMarkers(image)
    found: dict[int, list[np.ndarray]] = {}
    if identifiers is not None:
        for identifier, corner in zip(identifiers.ravel(), corners, strict=True):
            tag_id = int(identifier)
            if tag_id in (0, 1, 2):
                found.setdefault(tag_id, []).append(corner[0].astype(np.float64))
    return {tag_id: rows[0] for tag_id, rows in found.items() if len(rows) == 1}


def _metrics(errors: list[np.ndarray]) -> dict[str, float]:
    values = np.concatenate(errors)
    return {
        "corner_rmse_px": float(np.sqrt(np.mean(values**2))),
        "corner_max_px": float(np.max(values)),
    }


def _execution(path: Path, stage_index: int, action_sha: str) -> dict[str, Any]:
    receipt = _read(path)
    if (
        receipt.get("status") != "completed_wrist_view_reposition_stage"
        or receipt.get("stage_index") != stage_index
        or receipt.get("action_sha256") != action_sha
        or receipt.get("physical_follower_torque_enabled") is not False
        or receipt.get("error") is not None
    ):
        raise RuntimeError("execution receipt is not an admitted completed stage")
    return receipt


def fit(contract_path: Path, output_path: Path) -> dict[str, Any]:
    contract = load_contract(contract_path)
    fit_spec = contract["fit_observation"]
    source_path = _bound_path(contract["source_candidate"], "source candidate")
    source = _read(source_path)
    execution_path = _path(fit_spec["execution_receipt_path"])
    receipt = _execution(
        execution_path,
        int(fit_spec["stage_index"]),
        str(fit_spec["action_sha256"]),
    )
    image_path = _path(fit_spec["pi_image_path"])
    observations = detect_tags(image_path)
    fit_ids = [int(value) for value in fit_spec["fit_tag_ids"]]
    if any(tag_id not in observations for tag_id in fit_ids):
        raise RuntimeError("fit image lacks a unique required tag")

    bundle = ThreeLinkBundle(float(source["intrinsics"]["focal_pixels"]))
    parameters = np.asarray(source["parameters"]["parameter_vector"], dtype=np.float64)
    body_map = {
        int(tag_id): value["body"]
        for tag_id, value in source["tag_model"]["tags"].items()
    }
    joints = np.asarray(receipt["final_actual_degrees"], dtype=np.float64)

    def residual(camera: np.ndarray) -> np.ndarray:
        candidate = parameters.copy()
        candidate[:6] = camera
        return np.concatenate(
            [
                (
                    bundle.project(
                        candidate,
                        {"tag_id": tag_id, "joint_degrees": joints},
                        body_map,
                    )
                    - observations[tag_id]
                ).ravel()
                for tag_id in fit_ids
            ]
        )

    result = least_squares(
        residual,
        parameters[:6],
        bounds=(
            np.asarray([-np.pi] * 3 + [-3.0] * 3),
            np.asarray([np.pi] * 3 + [3.0] * 3),
        ),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=5000,
    )
    refreshed = parameters.copy()
    refreshed[:6] = result.x
    by_tag: dict[str, dict[str, float]] = {}
    fit_errors = []
    for tag_id in sorted(observations):
        errors = np.linalg.norm(
            bundle.project(
                refreshed,
                {"tag_id": tag_id, "joint_degrees": joints},
                body_map,
            )
            - observations[tag_id],
            axis=1,
        )
        by_tag[str(tag_id)] = _metrics([errors])
        if tag_id in fit_ids:
            fit_errors.append(errors)
    metrics = _metrics(fit_errors)
    gates = contract["gates"]
    passed = (
        len(fit_ids) >= int(gates["minimum_fit_tag_count"])
        and metrics["corner_rmse_px"] <= float(gates["fit_corner_rmse_max_px"])
        and metrics["corner_max_px"] <= float(gates["fit_corner_max_px"])
    )
    candidate = {
        "schema_version": CANDIDATE_SCHEMA,
        "status": "camera_only_fit_passed_heldout_unopened" if passed else "camera_only_fit_rejected",
        "proof_class": "physical_pi_camera_extrinsic_stage_1_fit_diagnostic",
        "contract": {"path": str(contract_path.resolve()), "sha256": sha256(contract_path)},
        "source_candidate": {"path": str(source_path), "sha256": sha256(source_path)},
        "implementation": {
            "path": str(IMPLEMENTATION_PATH),
            "sha256": sha256(IMPLEMENTATION_PATH),
            "projection_tool_path": str(PROJECTION_TOOL_PATH),
            "projection_tool_sha256": sha256(PROJECTION_TOOL_PATH),
        },
        "fit_execution": {
            "path": str(execution_path),
            "sha256": sha256(execution_path),
            "stage_index": fit_spec["stage_index"],
            "action_sha256": fit_spec["action_sha256"],
            "final_actual_degrees": joints.tolist(),
        },
        "fit_image": {"path": str(image_path), "sha256": sha256(image_path)},
        "fit_tag_ids": fit_ids,
        "diagnostic_excluded_tag_ids": fit_spec["diagnostic_excluded_tag_ids"],
        "parameters": {
            "source_parameter_vector": parameters.tolist(),
            "refreshed_parameter_vector": refreshed.tolist(),
            "camera_world_rotation_vector_radians": refreshed[:3].tolist(),
            "camera_world_translation_m": refreshed[3:6].tolist(),
            "camera_parameter_delta": (refreshed[:6] - parameters[:6]).tolist(),
            "all_non_camera_parameters_byte_for_value_frozen": bool(
                np.array_equal(refreshed[6:], parameters[6:])
            ),
        },
        "fit_metrics": {**metrics, "by_tag": by_tag},
        "optimizer": {
            "success": bool(result.success),
            "optimality": float(result.optimality),
            "function_evaluations": int(result.nfev),
        },
        "all_fit_gates_passed": passed,
        "heldout_stages_accessed": [],
        "authority": dict(contract["authority"]),
    }
    _write_once(output_path, candidate)
    return candidate


def evaluate(
    contract_path: Path,
    candidate_path: Path,
    execution_directory: Path,
    output_path: Path,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    candidate = _read(candidate_path)
    if (
        candidate.get("schema_version") != CANDIDATE_SCHEMA
        or candidate.get("status") != "camera_only_fit_passed_heldout_unopened"
        or candidate.get("contract", {}).get("sha256") != sha256(contract_path)
        or candidate.get("implementation", {}).get("sha256")
        != sha256(IMPLEMENTATION_PATH)
        or candidate.get("implementation", {}).get("projection_tool_sha256")
        != sha256(PROJECTION_TOOL_PATH)
    ):
        raise RuntimeError("camera-refresh candidate is not heldout-ready")
    receipt_path = execution_directory / "execution_receipt.json"
    receipt_value = _read(receipt_path)
    stage_index = int(receipt_value.get("stage_index", -1))
    heldout = next(
        (value for value in contract["heldout_stages"] if value["stage_index"] == stage_index),
        None,
    )
    if heldout is None:
        raise RuntimeError("execution is not a frozen heldout stage")
    receipt = _execution(receipt_path, stage_index, heldout["action_sha256"])
    if receipt.get("capture_hold_action_sha256") != heldout["capture_hold_action_sha256"]:
        raise RuntimeError("heldout capture-hold bytes changed")
    image_path = execution_directory / "pi_imx708_torque_on_hold.jpg"
    if (
        (receipt.get("pi_hold_still") or {}).get("sha256") != sha256(image_path)
        or receipt.get("capture_mode") != "c922_plus_pi_hold"
    ):
        raise RuntimeError("heldout Pi image or camera mode is not receipt-bound")

    source = _read(_bound_path(contract["source_candidate"], "source candidate"))
    bundle = ThreeLinkBundle(float(source["intrinsics"]["focal_pixels"]))
    parameters = np.asarray(
        candidate["parameters"]["refreshed_parameter_vector"], dtype=np.float64
    )
    body_map = {
        int(tag_id): value["body"]
        for tag_id, value in source["tag_model"]["tags"].items()
    }
    fit_ids = [int(value) for value in candidate["fit_tag_ids"]]
    fit_image = detect_tags(_path(contract["fit_observation"]["pi_image_path"]))
    heldout_image = detect_tags(image_path)
    if any(tag_id not in fit_image or tag_id not in heldout_image for tag_id in fit_ids):
        raise RuntimeError("heldout comparison lacks a unique fit tag")
    fit_joints = np.asarray(
        candidate["fit_execution"]["final_actual_degrees"], dtype=np.float64
    )
    heldout_joints = np.asarray(receipt["final_actual_degrees"], dtype=np.float64)
    absolute_errors = []
    relative_errors = []
    by_tag = {}
    for tag_id in fit_ids:
        predicted_fit = bundle.project(
            parameters,
            {"tag_id": tag_id, "joint_degrees": fit_joints},
            body_map,
        )
        predicted_heldout = bundle.project(
            parameters,
            {"tag_id": tag_id, "joint_degrees": heldout_joints},
            body_map,
        )
        absolute = np.linalg.norm(predicted_heldout - heldout_image[tag_id], axis=1)
        relative = np.linalg.norm(
            (predicted_heldout - predicted_fit)
            - (heldout_image[tag_id] - fit_image[tag_id]),
            axis=1,
        )
        absolute_errors.append(absolute)
        relative_errors.append(relative)
        by_tag[str(tag_id)] = {
            "absolute": _metrics([absolute]),
            "anchor_relative_displacement": _metrics([relative]),
        }
    absolute = _metrics(absolute_errors)
    relative = _metrics(relative_errors)
    gates = contract["gates"]
    samples = [
        json.loads(line)
        for line in (execution_directory / "joint_samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    rate_limited = sum(bool(row.get("rate_limited")) for row in samples)
    safety_clamped = sum(bool(row.get("safety_clamped")) for row in samples)
    passed = (
        absolute["corner_rmse_px"] <= float(gates["heldout_corner_rmse_max_px"])
        and absolute["corner_max_px"] <= float(gates["heldout_corner_max_px"])
        and relative["corner_rmse_px"]
        <= float(gates["heldout_anchor_relative_displacement_rmse_max_px"])
        and relative["corner_max_px"]
        <= float(gates["heldout_anchor_relative_displacement_max_px"])
        and rate_limited <= int(gates["gateway_rate_limited_samples_maximum"])
        and safety_clamped <= int(gates["gateway_safety_clamped_samples_maximum"])
    )
    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "status": "heldout_gates_passed_no_promotion" if passed else "heldout_rejected_no_promotion",
        "proof_class": "prospective_physical_pi_camera_extrinsic_geometric_hold_diagnostic",
        "contract": {"path": str(contract_path.resolve()), "sha256": sha256(contract_path)},
        "candidate": {"path": str(candidate_path.resolve()), "sha256": sha256(candidate_path)},
        "execution": {
            "path": str(receipt_path.resolve()),
            "sha256": sha256(receipt_path),
            "stage_index": stage_index,
            "action_sha256": heldout["action_sha256"],
            "capture_hold_action_sha256": heldout["capture_hold_action_sha256"],
        },
        "image": {"path": str(image_path.resolve()), "sha256": sha256(image_path)},
        "fit_tag_ids": fit_ids,
        "metrics": {
            "absolute": absolute,
            "anchor_relative_displacement": relative,
            "by_tag": by_tag,
            "gateway_rate_limited_samples": rate_limited,
            "gateway_safety_clamped_samples": safety_clamped,
        },
        "all_gates_passed": passed,
        "authority": dict(contract["authority"]),
    }
    _write_once(output_path, evaluation)
    return evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("fit", "evaluate"), required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--execution", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "fit":
        if args.candidate is not None or args.execution is not None:
            raise SystemExit("fit accepts no --candidate or --execution")
        result = fit(args.contract, args.output)
    else:
        if args.candidate is None or args.execution is None:
            raise SystemExit("evaluate requires --candidate and --execution")
        result = evaluate(args.contract, args.candidate, args.execution, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
