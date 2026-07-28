"""Independent, optimizer-free reviewer for the frozen V4 rigid fit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .bidirectional_registration_rigid_fit import (
    _lattice,
    _task_plane_errors,
)
from .bidirectional_registration_v2_fit import (
    _hold_means,
    _model_jaw_midpoints,
    project,
)
from .paths import REPO_ROOT


class RigidRegistrationReviewError(RuntimeError):
    """The frozen fit review could not be independently reproduced."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(entry: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    raw = str(entry["path"])
    if "heldout" in raw.lower():
        raise RigidRegistrationReviewError("heldout path is forbidden")
    path = REPO_ROOT / raw
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise RigidRegistrationReviewError(f"review input changed: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def _numerical_jacobian(function: Any, values: np.ndarray) -> np.ndarray:
    columns = []
    for index in range(len(values)):
        step = 1e-6 * max(1.0, abs(float(values[index])))
        left = values.copy()
        right = values.copy()
        left[index] -= step
        right[index] += step
        columns.append((function(right) - function(left)) / (2.0 * step))
    return np.column_stack(columns)


def review(contract_path: Path, output_path: Path) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    annotation_path, annotations = _load(contract["annotations"])
    candidate_path, candidate = _load(contract["candidate"])
    _, fit_receipt = _load(contract["fit_receipt"])
    _, acquisition = _load(annotations["acquisition_contract"])
    _, inherited = _load(annotations["inherited_unchanged_gate_contract"])
    _, fit_manifest = _load(annotations["fit_manifest"])
    _, wrapper = _load(annotations["candidate_manifest"])
    expected = [
        str(row["target_id"]) for row in acquisition["split"]["fit_targets"]
    ]
    members = {str(row["target_id"]): row for row in fit_manifest["members"]}
    helper_manifest = {
        "members": [
            {
                **members[target_id],
                "capture_receipt_path": str(
                    Path(members[target_id]["capture_receipt_path"]).resolve()
                ),
            }
            for target_id in expected
        ]
    }
    hold_means = _hold_means(annotations, helper_manifest)
    physical = np.asarray([hold_means[target_id] for target_id in expected])
    jaw_world = _model_jaw_midpoints(
        physical, wrapper["candidate_config"]
    )
    annotated = {
        str(row["target_id"]): row
        for row in annotations["jaw_endpoint_annotations"]["targets"]
    }
    observed = np.asarray(
        [
            (
                np.mean(np.asarray(annotated[target_id]["pass_a_tip_pixels"]), axis=0)
                + np.mean(
                    np.asarray(annotated[target_id]["pass_b_tip_pixels"]), axis=0
                )
            )
            / 2.0
            for target_id in expected
        ]
    )
    board_world, board_image = _lattice(
        annotations, wrapper["candidate_config"]
    )
    camera = np.asarray(candidate["camera_matrix_3x4"], dtype=float)
    yaw = float(candidate["robot_board_yaw_radians"])
    translation = np.asarray(candidate["robot_board_translation_xyz_m"])
    cosine, sine = np.cos(yaw), np.sin(yaw)
    rotation = np.asarray(
        [[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1.0]]
    )
    corrected = jaw_world @ rotation.T + translation
    board_error = np.linalg.norm(project(camera, board_world) - board_image, axis=1)
    hover_error = np.linalg.norm(project(camera, corrected) - observed, axis=1)
    task_error = _task_plane_errors(camera, observed, corrected)
    metrics = {
        "board_rms_px": float(np.sqrt(np.mean(board_error**2))),
        "board_max_px": float(np.max(board_error)),
        "hover_rms_px": float(np.sqrt(np.mean(hover_error**2))),
        "hover_max_px": float(np.max(hover_error)),
        "task_plane_rms_mm": float(np.sqrt(np.mean(task_error**2))),
        "task_plane_max_mm": float(np.max(task_error)),
    }

    initial_values = np.concatenate(
        (
            camera.ravel()[:11],
            [yaw],
            translation,
        )
    )

    def residual(values: np.ndarray) -> np.ndarray:
        local_camera = np.append(values[:11], 1.0).reshape(3, 4)
        local_yaw = values[11]
        c, s = np.cos(local_yaw), np.sin(local_yaw)
        local_rotation = np.asarray(
            [[c, -s, 0], [s, c, 0], [0, 0, 1.0]]
        )
        local_corrected = jaw_world @ local_rotation.T + values[12:15]
        return np.concatenate(
            (
                (project(local_camera, board_world) - board_image).ravel(),
                (project(local_camera, local_corrected) - observed).ravel(),
            )
        )

    jacobian = _numerical_jacobian(residual, initial_values)
    singular = np.linalg.svd(jacobian, compute_uv=False)
    rank = int(np.linalg.matrix_rank(jacobian))
    condition = float(singular[0] / singular[-1])
    fit_metrics = {
        "board_rms_px": fit_receipt["board_fit"]["rms_px"],
        "board_max_px": fit_receipt["board_fit"]["max_px"],
        "hover_rms_px": fit_receipt["hover_fit"]["rms_px"],
        "hover_max_px": fit_receipt["hover_fit"]["max_px"],
        "task_plane_rms_mm": fit_receipt["task_plane_fit"]["rms_mm"],
        "task_plane_max_mm": fit_receipt["task_plane_fit"]["max_mm"],
    }
    maximum_delta = max(
        abs(metrics[name] - float(fit_metrics[name])) for name in metrics
    )
    gates = acquisition["gates"]
    inherited_gates = inherited["gates"]
    checks = {
        "candidate_hash_matches_fit_receipt": (
            fit_receipt["candidate_sha256"] == _sha(candidate_path)
        ),
        "fit_receipt_all_checks_passed": all(fit_receipt["checks"].values()),
        "metric_rederivation": maximum_delta
        <= float(contract["maximum_metric_rederivation_delta"]),
        "board_gates": metrics["board_rms_px"]
        <= float(inherited_gates["maximum_board_lattice_fit_rms_px"])
        and metrics["board_max_px"]
        <= float(inherited_gates["maximum_board_lattice_fit_max_px"]),
        "hover_gates": metrics["hover_rms_px"]
        <= float(gates["maximum_fit_hover_reprojection_rms_px"])
        and metrics["hover_max_px"]
        <= float(gates["maximum_fit_hover_reprojection_max_px"]),
        "task_plane_gates": metrics["task_plane_rms_mm"]
        < float(gates["maximum_fit_task_plane_rms_mm_exclusive"])
        and metrics["task_plane_max_mm"]
        < float(inherited_gates["maximum_fit_task_plane_max_mm_exclusive"]),
        "independent_jacobian_full_rank": rank == 15,
        "independent_jacobian_condition": condition
        <= float(inherited_gates["maximum_refinement_jacobian_condition_number"]),
        "parameter_bounds_unchanged": abs(np.rad2deg(yaw))
        <= float(inherited_gates["maximum_absolute_robot_board_yaw_degrees"])
        and np.max(np.abs(translation[:2])) * 1000.0
        <= float(inherited_gates["maximum_robot_board_translation_xy_mm"])
        and abs(translation[2]) * 1000.0
        <= float(inherited_gates["maximum_absolute_robot_board_translation_z_mm"])
        + 1e-6,
        "z_saturation_disclosed_without_expansion": abs(
            abs(float(translation[2])) - 0.1
        )
        <= 1e-6
        and contract["z_bound_saturation_policy"][
            "does_not_expand_bound"
        ]
        is True,
        "authority_closed": not any(contract["authority"].values()),
    }
    checks = {name: bool(value) for name, value in checks.items()}
    admitted = all(checks.values())
    receipt = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_rigid_registration_fit_review_receipt.v1",
        "status": "CONTINUE_TO_SINGLE_SEALED_HELDOUT_OPEN" if admitted else "REDIRECT",
        "proof_class": "independent_fit_only_registration_candidate_review",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "annotation_sha256": _sha(annotation_path),
        "candidate_sha256": _sha(candidate_path),
        "fit_receipt_sha256": contract["fit_receipt"]["sha256"],
        "heldout_open_count": 0,
        "heldout_content_read": False,
        "rederived_metrics": metrics,
        "maximum_metric_rederivation_delta": maximum_delta,
        "independent_jacobian": {
            "shape": list(jacobian.shape),
            "rank": rank,
            "condition_number": condition,
            "singular_values": singular.tolist(),
        },
        "active_bound_risk": {
            "parameter": "robot_board_translation_z",
            "value_mm": float(translation[2] * 1000.0),
            "bound_mm": 100.0,
            "automatic_pass_expansion": False,
            "all_four_frozen_heldouts_required": True,
        },
        "checks": checks,
        "sealed_heldout_open_authorized": admitted,
        "authority": contract["authority"],
        "claim_boundary": "Independent fit-only review; candidate remains unpromoted and all four sealed heldouts must open together exactly once with zero refit.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt
