"""Motion-free canonical revalidation of the sealed V4 task-plane fit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .bidirectional_registration_rigid_fit import _task_plane_errors
from .bidirectional_registration_v2_fit import project
from .current_workcell import (
    BOARD_FILES,
    BOARD_RANKS,
    build_current_workcell_spec,
    current_square_center,
)
from .grasp import _jaw_tip_point
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position


class CanonicalTaskPlaneRegistrationError(RuntimeError):
    """A frozen input or canonical registration invariant changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(entry: Mapping[str, Any]) -> Path:
    path = REPO_ROOT / str(entry["path"])
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise CanonicalTaskPlaneRegistrationError(
            f"bound registration input changed: {path}"
        )
    return path


def _json(entry: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(entry).read_text(encoding="utf-8"))


def _evidence_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_file():
        return path
    parts = path.parts
    if "runs" in parts:
        candidate = REPO_ROOT.joinpath(*parts[parts.index("runs") :])
        if candidate.is_file():
            return candidate
    raise CanonicalTaskPlaneRegistrationError(
        f"heldout evidence path is unavailable: {raw}"
    )


def _canonical_piece_alignment(
    model: mujoco.MjModel,
    tolerance_m: float,
) -> tuple[dict[str, float], int]:
    errors: dict[str, float] = {}
    count = 0
    for rank in BOARD_RANKS:
        for file_name in BOARD_FILES:
            square = f"{file_name}{rank}"
            color = "brown" if rank in "12" else "tan"
            name = f"{color}_pawn_{square}"
            body_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_BODY, name
            )
            if body_id < 0:
                continue
            error = float(
                np.linalg.norm(
                    model.body_pos[body_id]
                    - np.asarray(current_square_center(square))
                )
            )
            errors[square] = error
            count += 1
    if count != 16 or max(errors.values(), default=np.inf) > tolerance_m:
        raise CanonicalTaskPlaneRegistrationError(
            "compiled canonical pawn layout is not aligned"
        )
    return errors, count


def _canonical_corner_world(
    model: mujoco.MjModel,
) -> tuple[list[str], np.ndarray, float]:
    order = ["a8_outer", "h8_outer", "h1_outer", "a1_outer"]
    corner_squares = [item.split("_", 1)[0] for item in order]
    centers = np.asarray(
        [current_square_center(square) for square in corner_squares],
        dtype=np.float64,
    )
    board_center = np.mean(centers, axis=0)
    extrapolated = board_center + ((centers - board_center) * (8.0 / 7.0))

    body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "chess_board"
    )
    if body_id < 0:
        raise CanonicalTaskPlaneRegistrationError(
            "canonical workcell lacks chess_board"
        )
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    side = 0.3556
    local = np.asarray(
        [
            [side / 2.0, -side / 2.0, 0.017],
            [-side / 2.0, -side / 2.0, 0.017],
            [-side / 2.0, side / 2.0, 0.017],
            [side / 2.0, side / 2.0, 0.017],
        ],
        dtype=np.float64,
    )
    rotation = data.xmat[body_id].reshape(3, 3)
    direct = local @ rotation.T + data.xpos[body_id]
    maximum_error = float(np.max(np.linalg.norm(extrapolated - direct, axis=1)))
    return order, direct, maximum_error


def _current_jaw_midpoints(
    physical: np.ndarray,
    candidate_config: Mapping[str, Any],
) -> np.ndarray:
    model = build_current_workcell_spec().compile()
    data = mujoco.MjData(model)
    addresses = []
    for name in candidate_config["bindings"]["joint_names"]:
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, name
        )
        if joint_id < 0:
            raise CanonicalTaskPlaneRegistrationError(
                f"canonical model joint is missing: {name}"
            )
        addresses.append(int(model.jnt_qposadr[joint_id]))
    moving_tips = [
        mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_GEOM,
            f"left_moving_jaw_sph_tip{index}",
        )
        for index in (1, 2, 3)
    ]
    if any(item < 0 for item in moving_tips):
        raise CanonicalTaskPlaneRegistrationError(
            "canonical moving jaw tip geometry is incomplete"
        )
    positions = _physical_to_model_position(physical, candidate_config)
    result = []
    for row in positions:
        data.qpos[addresses] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        fixed = _jaw_tip_point(model, data, "left")
        moving = np.mean(data.geom_xpos[moving_tips], axis=0)
        result.append((fixed + moving) / 2.0)
    return np.asarray(result, dtype=np.float64)


def _heldout_observations(
    annotations: Mapping[str, Any],
    open_receipt: Mapping[str, Any],
    joint_path: Path,
) -> tuple[list[str], np.ndarray, np.ndarray]:
    samples = [
        json.loads(line)
        for line in joint_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    opened = {row["opaque_id"]: row for row in open_receipt["members"]}
    annotated = {row["opaque_id"]: row for row in annotations["members"]}
    expected = [f"heldout-r4-{index:02d}" for index in range(1, 5)]
    if set(opened) != set(expected) or set(annotated) != set(expected):
        raise CanonicalTaskPlaneRegistrationError(
            "sealed heldout membership changed"
        )
    physical = []
    observed = []
    for opaque_id in expected:
        member = opened[opaque_id]
        receipt_path = _evidence_path(str(member["capture_receipt_path"]))
        if _sha(receipt_path) != member["capture_receipt_sha256"]:
            raise CanonicalTaskPlaneRegistrationError(
                "heldout capture receipt changed"
            )
        capture = json.loads(receipt_path.read_text(encoding="utf-8"))
        first = int(capture["scored_hold_first_host_continuous_ns"])
        last = int(capture["scored_hold_last_host_continuous_ns"])
        rows = [
            row["actual_physical_units"]
            for row in samples
            if first <= int(row["host_continuous_ns"]) <= last
        ]
        if len(rows) != int(capture["scored_hold_sample_count"]):
            raise CanonicalTaskPlaneRegistrationError(
                "heldout hold sample count changed"
            )
        physical.append(np.mean(np.asarray(rows, dtype=np.float64), axis=0))
        annotation = annotated[opaque_id]
        first_tips = np.asarray(
            annotation["pass_a_tip_pixels"], dtype=np.float64
        )
        second_tips = np.asarray(
            annotation["pass_b_tip_pixels"], dtype=np.float64
        )
        observed.append(
            (np.mean(first_tips, axis=0) + np.mean(second_tips, axis=0))
            / 2.0
        )
    return expected, np.asarray(physical), np.asarray(observed)


def evaluate(contract_path: Path, output_path: Path) -> dict[str, Any]:
    """Recompute the frozen task-plane result through the canonical runtime."""

    if output_path.exists():
        raise CanonicalTaskPlaneRegistrationError(
            f"immutable output already exists: {output_path}"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    inputs = contract["inputs"]
    cutover = _json(inputs["hard_cutover"])
    _bound(inputs["current_workcell_implementation"])
    _bound(inputs["evaluator_implementation"])
    fit_annotations = _json(inputs["fit_annotations"])
    annotations = _json(inputs["heldout_annotations"])
    candidate = _json(inputs["candidate"])
    candidate_manifest = _json(inputs["candidate_manifest"])
    joint_path = _bound(inputs["joint_samples"])
    open_receipt = _json(inputs["heldout_open_receipt"])
    historical = _json(inputs["historical_heldout_evaluation"])
    if (
        cutover["status"] != "verified_complete"
        or cutover["authority"]["physical_authority"] is not False
        or open_receipt["heldout_pixel_open_count"] != 1
        or open_receipt["candidate_refit"] is not False
        or historical["candidate_refit"] is not False
    ):
        raise CanonicalTaskPlaneRegistrationError(
            "cutover or sealed-heldout authority changed"
        )

    model = build_current_workcell_spec().compile()
    semantics = contract["canonical_semantics"]
    piece_errors, piece_count = _canonical_piece_alignment(
        model,
        float(semantics["compiled_piece_alignment_tolerance_m"]),
    )
    corner_order, corner_world, corner_error = _canonical_corner_world(model)
    if (
        corner_order != semantics["playing_corner_order"]
        or fit_annotations["board_lattice"]["playing_corner_order"]
        != corner_order
        or corner_error
        > float(semantics["corner_world_alignment_tolerance_m"])
    ):
        raise CanonicalTaskPlaneRegistrationError(
            "canonical playing-corner association changed"
        )

    expected, physical, observed = _heldout_observations(
        annotations, open_receipt, joint_path
    )
    candidate_config = candidate_manifest["candidate_config"]
    jaw_world = _current_jaw_midpoints(physical, candidate_config)
    yaw = float(candidate["robot_board_yaw_radians"])
    cosine, sine = np.cos(yaw), np.sin(yaw)
    rotation = np.asarray(
        [[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1.0]]
    )
    corrected = (
        jaw_world @ rotation.T
        + np.asarray(candidate["robot_board_translation_xyz_m"])
    )
    camera = np.asarray(candidate["camera_matrix_3x4"], dtype=np.float64)
    projected = project(camera, corrected)
    reprojection = np.linalg.norm(projected - observed, axis=1)
    task_plane = _task_plane_errors(camera, observed, corrected)
    aggregate = {
        "reprojection_rms_px": float(np.sqrt(np.mean(reprojection**2))),
        "reprojection_max_px": float(np.max(reprojection)),
        "task_plane_rms_mm": float(np.sqrt(np.mean(task_plane**2))),
        "task_plane_max_mm": float(np.max(task_plane)),
    }
    tolerance = float(
        contract["gates"]["historical_recomputation_tolerance"]
    )
    historical_aggregate = historical["aggregate"]
    gates = contract["gates"]
    checks = {
        "canonical_runtime_loaded": True,
        "canonical_corner_order_exact": True,
        "canonical_corner_world_alignment": corner_error
        <= semantics["corner_world_alignment_tolerance_m"],
        "all_16_reset_pawns_aligned": piece_count == 16,
        "all_64_square_centers_unique": len(
            {
                tuple(np.round(current_square_center(f"{file_name}{rank}"), 12))
                for rank in BOARD_RANKS
                for file_name in BOARD_FILES
            }
        )
        == 64,
        "all_four_heldout_members": len(expected) == 4,
        "task_plane_rms": aggregate["task_plane_rms_mm"]
        < gates["maximum_task_plane_rms_mm_exclusive"],
        "task_plane_max": aggregate["task_plane_max_mm"]
        < gates["maximum_task_plane_max_mm_exclusive"],
        "reprojection_rms": aggregate["reprojection_rms_px"]
        <= gates["maximum_reprojection_rms_px"],
        "reprojection_max": aggregate["reprojection_max_px"]
        <= gates["maximum_reprojection_max_px"],
        "historical_result_reproduced": all(
            abs(aggregate[name] - float(historical_aggregate[name]))
            <= tolerance
            for name in aggregate
        ),
        "candidate_refit_false": True,
        "raw_image_reopen_false": True,
        "physical_recapture_false": True,
        "physical_authority_false": contract["authority"]["physical_motion"]
        is False,
    }
    passed = all(checks.values())
    receipt = {
        "schema_version": "sim2claw.canonical_task_plane_registration_receipt.v1",
        "status": (
            "canonical_task_plane_registration_pass"
            if passed
            else "canonical_task_plane_registration_reject"
        ),
        "proof_class": "motion_free_canonical_runtime_registration_revalidation",
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "candidate_sha256": inputs["candidate"]["sha256"],
        "current_workcell_sha256": inputs[
            "current_workcell_implementation"
        ]["sha256"],
        "corner_order": corner_order,
        "corner_world_xyz_m": corner_world.tolist(),
        "corner_alignment_max_m": corner_error,
        "piece_alignment_max_m": max(piece_errors.values()),
        "heldout_members": [
            {
                "opaque_id": opaque_id,
                "reprojection_error_px": float(reprojection[index]),
                "task_plane_error_mm": float(task_plane[index]),
            }
            for index, opaque_id in enumerate(expected)
        ],
        "aggregate": aggregate,
        "checks": checks,
        "passed": passed,
        "candidate_refit": False,
        "raw_heldout_images_reopened": False,
        "physical_recapture": False,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt
