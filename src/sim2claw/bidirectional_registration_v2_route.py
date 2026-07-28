"""Compile and audit the motion-free v2 registration route.

This module can only build exact setup arrays and run CPU/fp64 geometry and
visibility screens.  It does not construct a robot gateway or open a camera.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import cv2
import mujoco
import numpy as np

from .grasp import _pinch_offset, _pinch_point
from .learning_factory_artifacts import sha256_file
from .paths import REPO_ROOT
from .recorded_replay import _compile_model
from .replay_eligibility import action_sha256
from .wrist_view_reposition import (
    _physical_to_model_position,
    preview_wrist_view_actions,
)


ROUTE_SCHEMA = "sim2claw.bidirectional_pawn_push_v2_registration_route.v1"
ACQUISITION_SCHEMA = (
    "sim2claw.bidirectional_pawn_push_v2_registration_acquisition.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.bidirectional_pawn_push_v2_registration_route_preview.v1"
)
DEFAULT_ROUTE = (
    REPO_ROOT
    / "configs/hardware/"
    "bidirectional_pawn_push_v2_registration_route_v1.json"
)


class BidirectionalRegistrationV2RouteError(RuntimeError):
    """The preregistered route, static geometry, or visibility gate failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BidirectionalRegistrationV2RouteError(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BidirectionalRegistrationV2RouteError(
            f"cannot read JSON {path}: {error}"
        ) from error
    _require(isinstance(value, dict), f"expected object in {path}")
    return value


def _bound(binding: Mapping[str, Any]) -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "bound path escaped repository",
    )
    path = (REPO_ROOT / relative).resolve()
    _require(
        path.is_file() and sha256_file(path) == binding.get("sha256"),
        f"bound source changed: {relative}",
    )
    return path


def load_route(
    path: Path = DEFAULT_ROUTE,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    path = path.resolve()
    route = _json(path)
    _require(route.get("schema_version") == ROUTE_SCHEMA, "route schema changed")
    _require(
        route.get("status") == "frozen_for_cpu_fp64_preview_no_motion_authority",
        "route status widened",
    )
    acquisition_path = _bound(route["acquisition_contract"])
    acquisition = _json(acquisition_path)
    _require(
        acquisition.get("schema_version") == ACQUISITION_SCHEMA,
        "acquisition schema changed",
    )
    motion = route.get("motion_contract") or {}
    _require(motion and not any(motion.values()), "route improperly authorizes motion")
    return route, acquisition, acquisition_path


def _interpolate(
    start: np.ndarray,
    stop: np.ndarray,
    *,
    sample_hz: int,
    maximum_slew: float,
) -> np.ndarray:
    delta = float(np.max(np.abs(stop - start)))
    sample_count = max(
        2,
        int(math.ceil(delta / maximum_slew * sample_hz)) + 1,
    )
    return np.linspace(start, stop, sample_count, dtype=np.float64)


def _append_segment(
    rows: list[np.ndarray],
    start: np.ndarray,
    stop: np.ndarray,
    *,
    sample_hz: int,
    maximum_slew: float,
) -> None:
    segment = _interpolate(
        start,
        stop,
        sample_hz=sample_hz,
        maximum_slew=maximum_slew,
    )
    rows.extend(segment if not rows else segment[1:])


def compile_exact_route(
    route: Mapping[str, Any],
    acquisition: Mapping[str, Any],
    *,
    observed_start: np.ndarray | None = None,
) -> dict[str, Any]:
    compile_spec = route["compile"]
    sample_hz = int(compile_spec["sample_hz"])
    maximum_slew = float(
        compile_spec["maximum_body_slew_degrees_per_second"]
    )
    hold_samples = int(compile_spec["stationary_hold_samples_per_target"])
    expected_start = np.asarray(
        route["source_rebase"]["expected_degrees_percent"],
        dtype=np.float64,
    )
    start = (
        expected_start
        if observed_start is None
        else np.asarray(observed_start, dtype=np.float64)
    )
    _require(start.shape == (6,), "route start must have six values")
    _require(
        float(np.max(np.abs(start - expected_start)))
        <= float(route["source_rebase"]["maximum_absolute_delta_degrees"]),
        "fresh start differs from the frozen rebase envelope",
    )
    safe = np.asarray(
        route["source_egress"]["target_degrees_percent"],
        dtype=np.float64,
    )
    egress_rows: list[np.ndarray] = []
    _append_segment(
        egress_rows,
        start,
        safe,
        sample_hz=sample_hz,
        maximum_slew=maximum_slew,
    )
    egress = np.ascontiguousarray(egress_rows, dtype="<f8")

    targets = {
        item["target_id"]: np.asarray(
            item["physical_degrees_percent"], dtype=np.float64
        )
        for split_name in ("fit_targets", "heldout_targets")
        for item in acquisition["split"][split_name]
    }
    _require(
        set(route["capture_order"]) == set(targets),
        "capture order does not cover the frozen split exactly",
    )
    main_rows: list[np.ndarray] = [safe.copy()]
    capture_slices: list[dict[str, Any]] = []
    current = safe
    for target_id in route["capture_order"]:
        target = targets[target_id]
        _append_segment(
            main_rows,
            current,
            target,
            sample_hz=sample_hz,
            maximum_slew=maximum_slew,
        )
        hold_start = len(main_rows) - 1
        main_rows.extend([target.copy() for _ in range(hold_samples - 1)])
        capture_slices.append(
            {
                "target_id": target_id,
                "start_index": hold_start,
                "end_index_exclusive": hold_start + hold_samples,
                "sample_count": hold_samples,
            }
        )
        current = target
    if route["return"]["return_to_source_egress_target_first"]:
        _append_segment(
            main_rows,
            current,
            safe,
            sample_hz=sample_hz,
            maximum_slew=maximum_slew,
        )
        current = safe
    for waypoint in route["return"]["waypoints_degrees_percent"]:
        target = np.asarray(waypoint, dtype=np.float64)
        _append_segment(
            main_rows,
            current,
            target,
            sample_hz=sample_hz,
            maximum_slew=maximum_slew,
        )
        current = target
    main = np.ascontiguousarray(main_rows, dtype="<f8")
    return {
        "sample_hz": sample_hz,
        "maximum_slew": maximum_slew,
        "start": start,
        "safe": safe,
        "egress": egress,
        "main": main,
        "capture_slices": capture_slices,
        "targets": targets,
    }


def _maximum_rate(actions: np.ndarray, sample_hz: int) -> float:
    if len(actions) < 2:
        return 0.0
    return float(np.max(np.abs(np.diff(actions, axis=0))) * sample_hz)


def _set_pose(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    qpos_addresses: np.ndarray,
    model_position: np.ndarray,
) -> None:
    data.qpos[qpos_addresses] = model_position
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)


def _geom_inventory(
    model: mujoco.MjModel,
) -> tuple[list[int], list[int], list[int]]:
    jaw_bodies = {"left_gripper", "left_moving_jaw_so101_v1"}
    jaw: list[int] = []
    board: list[int] = []
    pawns: list[int] = []
    for geom_id in range(model.ngeom):
        body_name = mujoco.mj_id2name(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            int(model.geom_bodyid[geom_id]),
        )
        if body_name in jaw_bodies:
            jaw.append(geom_id)
        elif body_name == "chess_board":
            board.append(geom_id)
        elif body_name and "pawn_" in body_name:
            pawns.append(geom_id)
    _require(jaw and board and pawns, "collision geometry inventory is incomplete")
    return jaw, board, pawns


def _minimum_distance(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    first: list[int],
    second: list[int],
    *,
    limit_m: float,
) -> tuple[float, tuple[int, int] | None]:
    best = limit_m
    pair: tuple[int, int] | None = None
    for left in first:
        for right in second:
            distance = float(
                mujoco.mj_geomDistance(
                    model, data, left, right, best, None
                )
            )
            if distance < best:
                best = distance
                pair = (left, right)
    return best, pair


def _distance_audit(
    actions: np.ndarray,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    model, _ = _compile_model(dict(candidate), base_directory=None)
    data = mujoco.MjData(model)
    joint_names = list(candidate["bindings"]["joint_names"])
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    addresses = np.asarray(
        [model.jnt_qposadr[joint_id] for joint_id in joint_ids],
        dtype=np.int32,
    )
    model_actions = _physical_to_model_position(actions, candidate)
    jaw, board, pawns = _geom_inventory(model)
    rows = {
        "board": {"distance_m": 0.2, "pair": None, "row_index": None},
        "pawns": {"distance_m": 0.2, "pair": None, "row_index": None},
    }
    for row_index, model_position in enumerate(model_actions):
        _set_pose(model, data, addresses, model_position)
        for name, targets in (("board", board), ("pawns", pawns)):
            distance, pair = _minimum_distance(
                model,
                data,
                jaw,
                targets,
                limit_m=float(rows[name]["distance_m"]),
            )
            if distance < float(rows[name]["distance_m"]):
                rows[name] = {
                    "distance_m": distance,
                    "pair": (
                        [
                            mujoco.mj_id2name(
                                model,
                                mujoco.mjtObj.mjOBJ_BODY,
                                int(model.geom_bodyid[item]),
                            )
                            for item in pair
                        ]
                        if pair is not None
                        else None
                    ),
                    "row_index": row_index,
                }
    return rows


def _pinch_points(
    physical: np.ndarray,
    candidate: Mapping[str, Any],
) -> np.ndarray:
    model, _ = _compile_model(dict(candidate), base_directory=None)
    data = mujoco.MjData(model)
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in candidate["bindings"]["joint_names"]
    ]
    addresses = np.asarray(
        [model.jnt_qposadr[item] for item in joint_ids], dtype=np.int32
    )
    model_positions = _physical_to_model_position(physical, candidate)
    _set_pose(model, data, addresses, model_positions[0])
    pinch_local = _pinch_offset(model, data, "left")
    result = []
    for row in model_positions:
        _set_pose(model, data, addresses, row)
        result.append(_pinch_point(model, data, "left", pinch_local).copy())
    return np.asarray(result)


def _board_world_corners(
    candidate: Mapping[str, Any],
    side_m: float,
) -> np.ndarray:
    model, _ = _compile_model(dict(candidate), base_directory=None)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "chess_board"
    )
    _require(body_id >= 0, "compiled scene lacks chess board")
    local = np.asarray(
        [
            [-side_m / 2.0, -side_m / 2.0, 0.017],
            [side_m / 2.0, -side_m / 2.0, 0.017],
            [side_m / 2.0, side_m / 2.0, 0.017],
            [-side_m / 2.0, side_m / 2.0, 0.017],
        ],
        dtype=np.float64,
    )
    rotation = data.xmat[body_id].reshape(3, 3)
    return local @ rotation.T + data.xpos[body_id]


def _visibility_audit(
    route: Mapping[str, Any],
    acquisition: Mapping[str, Any],
    compiled: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    overlay_path: Path,
) -> dict[str, Any]:
    proxy = route["static_c922_visibility_proxy"]
    source = _bound(proxy["source_frame"])
    frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
    _require(frame is not None, "cannot decode C922 visibility source")
    image_corners = np.asarray(proxy["playing_corners_px"], dtype=np.float64)
    side_m = float(acquisition["board_model"]["playing_side_design_prior_mm"]) / 1000.0
    world_corners = _board_world_corners(candidate, side_m)
    permutation = np.asarray(proxy["board_corner_permutation"], dtype=np.int32)
    camera_matrix = np.asarray(
        proxy["nominal_camera_matrix"], dtype=np.float64
    )
    distortion = np.asarray(proxy["distortion"], dtype=np.float64)
    solved, rvec, tvec = cv2.solvePnP(
        world_corners[permutation],
        image_corners,
        camera_matrix,
        distortion,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    _require(bool(solved), "visibility proxy PnP did not solve")
    ordered = list(route["capture_order"])
    target_vectors = np.asarray(
        [compiled["targets"][target_id] for target_id in ordered],
        dtype=np.float64,
    )
    points = _pinch_points(target_vectors, candidate)
    pixels, _ = cv2.projectPoints(
        points, rvec, tvec, camera_matrix, distortion
    )
    pixels = pixels.reshape(-1, 2)
    width, height = int(frame.shape[1]), int(frame.shape[0])
    margins = np.column_stack(
        (
            pixels[:, 0],
            width - 1 - pixels[:, 0],
            pixels[:, 1],
            height - 1 - pixels[:, 1],
        )
    )
    minimum_margin = float(np.min(margins))
    rotation, _ = cv2.Rodrigues(rvec)
    camera_world = (-rotation.T @ tvec).reshape(3)
    board_center = np.mean(world_corners, axis=0)
    camera_height = float(camera_world[2] - board_center[2])

    model, _ = _compile_model(dict(candidate), base_directory=None)
    data = mujoco.MjData(model)
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in candidate["bindings"]["joint_names"]
    ]
    addresses = np.asarray(
        [model.jnt_qposadr[item] for item in joint_ids], dtype=np.int32
    )
    model_positions = _physical_to_model_position(target_vectors, candidate)
    allowed_bodies = set(proxy["reference_visible_bodies"])
    maximum_surface_offset = float(proxy["maximum_reference_surface_offset_m"])
    line_of_sight = []
    for target_id, model_position, point in zip(
        ordered, model_positions, points, strict=True
    ):
        _set_pose(model, data, addresses, model_position)
        vector = point - camera_world
        target_distance = float(np.linalg.norm(vector))
        direction = vector / target_distance
        geom_id = np.asarray([-1], dtype=np.int32)
        hit_distance = float(
            mujoco.mj_ray(
                model,
                data,
                camera_world,
                direction,
                None,
                True,
                -1,
                geom_id,
            )
        )
        hit_body = (
            mujoco.mj_id2name(
                model,
                mujoco.mjtObj.mjOBJ_BODY,
                int(model.geom_bodyid[geom_id[0]]),
            )
            if geom_id[0] >= 0
            else None
        )
        surface_offset = target_distance - hit_distance
        passed = bool(
            geom_id[0] >= 0
            and hit_body in allowed_bodies
            and 0.0 <= surface_offset <= maximum_surface_offset
        )
        line_of_sight.append(
            {
                "target_id": target_id,
                "target_distance_m": target_distance,
                "first_hit_distance_m": hit_distance,
                "first_hit_body": hit_body,
                "reference_surface_offset_m": surface_offset,
                "passed": passed,
            }
        )

    cv2.polylines(
        frame,
        [np.rint(image_corners).astype(np.int32).reshape(-1, 1, 2)],
        True,
        (0, 220, 0),
        2,
        cv2.LINE_AA,
    )
    for target_id, pixel in zip(ordered, pixels, strict=True):
        point = tuple(np.rint(pixel).astype(int))
        color = (255, 160, 0) if "heldout" in target_id else (0, 80, 255)
        cv2.circle(frame, point, 5, color, -1, cv2.LINE_AA)
        cv2.putText(
            frame,
            target_id.replace("v2-", ""),
            (point[0] + 6, point[1] - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            color,
            1,
            cv2.LINE_AA,
        )
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    _require(cv2.imwrite(str(overlay_path), frame), "could not write overlay")
    return {
        "proxy_only": True,
        "source_frame_path": str(source),
        "source_frame_sha256": sha256_file(source),
        "board_corner_permutation": permutation.tolist(),
        "nominal_camera_matrix": camera_matrix.tolist(),
        "camera_world_m": camera_world.tolist(),
        "camera_height_above_board_center_m": camera_height,
        "reference_line_of_sight": {
            "allowed_first_hit_bodies": sorted(allowed_bodies),
            "maximum_reference_surface_offset_m": maximum_surface_offset,
            "all_passed": all(row["passed"] for row in line_of_sight),
            "target_rows": line_of_sight,
        },
        "target_rows": [
            {
                "target_id": target_id,
                "model_pinch_world_m": point.tolist(),
                "predicted_pixel": pixel.tolist(),
                "minimum_image_margin_px": float(np.min(margin)),
            }
            for target_id, point, pixel, margin in zip(
                ordered, points, pixels, margins, strict=True
            )
        ],
        "minimum_predicted_reference_image_margin_px": minimum_margin,
        "overlay_path": str(overlay_path),
        "overlay_sha256": sha256_file(overlay_path),
    }


def evaluate_route(
    *,
    route_path: Path = DEFAULT_ROUTE,
    output_root: Path,
    observed_start: np.ndarray | None = None,
) -> dict[str, Any]:
    route, acquisition, acquisition_path = load_route(route_path)
    output_root = output_root.resolve()
    _require(not output_root.exists(), "refusing to overwrite V02 output")
    output_root.mkdir(parents=True)
    compiled = compile_exact_route(
        route, acquisition, observed_start=observed_start
    )
    manifest_path = _bound(route["candidate_manifest"])
    manifest = _json(manifest_path)
    candidate = manifest["candidate_config"]

    egress_preview = preview_wrist_view_actions(
        [compiled["egress"]],
        manifest_path,
        recovery_source_contact_admission=True,
    )
    main_preview = preview_wrist_view_actions(
        [compiled["main"]],
        manifest_path,
    )
    all_actions = np.concatenate(
        [compiled["egress"], compiled["main"][1:]], axis=0
    ).astype("<f8", copy=False)
    distance = _distance_audit(all_actions, candidate)

    v00_path = _bound(acquisition["sources"]["v00_design_receipt"])
    v00 = _json(v00_path)
    preflight = v00["hardware_preflight"]
    lower = np.asarray(
        [
            -120.26373626373626,
            -106.63736263736264,
            -102.10989010989012,
            -107.47252747252747,
            -180.0,
            0.0,
        ]
    )
    upper = np.asarray(
        [
            120.26373626373626,
            106.63736263736264,
            102.10989010989012,
            107.47252747252747,
            180.0,
            100.0,
        ]
    )
    limits_pass = bool(
        np.all(all_actions >= lower) and np.all(all_actions <= upper)
    )
    maximum_rate = max(
        _maximum_rate(compiled["egress"], compiled["sample_hz"]),
        _maximum_rate(compiled["main"], compiled["sample_hz"]),
    )
    overlay_path = output_root / "c922_visibility_proxy.png"
    visibility = _visibility_audit(
        route,
        acquisition,
        compiled,
        candidate,
        overlay_path=overlay_path,
    )

    egress_path = output_root / "source_egress.npy"
    main_path = output_root / "capture_and_return.npy"
    np.save(egress_path, compiled["egress"], allow_pickle=False)
    np.save(main_path, compiled["main"], allow_pickle=False)
    anchor_receipt_path = _bound(
        route["return"]["final_anchor_prior_physical_evidence"]
    )
    anchor_receipt = _json(anchor_receipt_path)
    final_anchor_ok = bool(
        anchor_receipt.get("status")
        == "completed_wrist_view_reposition_stage"
        and anchor_receipt.get("physical_follower_torque_enabled") is False
        and anchor_receipt.get("error") is None
        and np.array_equal(
            compiled["main"][-1],
            np.asarray(
                route["return"]["waypoints_degrees_percent"][-1],
                dtype="<f8",
            ),
        )
    )
    gates_spec = route["static_gates"]
    gates = {
        "source_egress_preview": bool(
            egress_preview["no_new_or_worsened_kinematic_contact"]
            and not egress_preview["final_contact_pairs"]
        ),
        "main_route_preview": bool(
            main_preview["no_new_or_worsened_kinematic_contact"]
            and not main_preview["external_contact_pairs"]
        ),
        "joint_limits": limits_pass,
        "maximum_slew": maximum_rate
        <= float(gates_spec["maximum_body_slew_degrees_per_second"])
        + 1e-9,
        "jaw_to_pawns": float(distance["pawns"]["distance_m"])
        >= float(gates_spec["minimum_jaw_to_any_pawn_clearance_m"]),
        "jaw_to_board": float(distance["board"]["distance_m"])
        >= float(gates_spec["minimum_jaw_to_board_clearance_m"]),
        "c922_visibility_proxy": float(
            visibility["minimum_predicted_reference_image_margin_px"]
        )
        >= float(gates_spec["minimum_predicted_reference_image_margin_px"]),
        "capture_reference_line_of_sight": bool(
            visibility["reference_line_of_sight"]["all_passed"]
        ),
        "capture_target_count": len(compiled["capture_slices"])
        >= int(gates_spec["minimum_capture_target_count"]),
        "final_anchor": final_anchor_ok,
        "no_motion_authority": not any(route["motion_contract"].values()),
    }
    reviewer_decision = "CONTINUE" if all(gates.values()) else "REDIRECT"
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "completed_cpu_fp64_static_route_and_visibility_preview",
        "proof_class": "cpu_fp64_static_registration_route_preview_only",
        "route_path": str(route_path.resolve()),
        "route_sha256": sha256_file(route_path.resolve()),
        "acquisition_contract_path": str(acquisition_path),
        "acquisition_contract_sha256": sha256_file(acquisition_path),
        "candidate_manifest_path": str(manifest_path),
        "candidate_manifest_sha256": sha256_file(manifest_path),
        "fresh_start_source": (
            "caller_observed_torque_off_preflight"
            if observed_start is not None
            else "frozen_v00_observation"
        ),
        "follower_start_degrees": compiled["start"].tolist(),
        "sample_hz": compiled["sample_hz"],
        "source_egress": {
            "sample_count": int(len(compiled["egress"])),
            "duration_seconds": (len(compiled["egress"]) - 1)
            / compiled["sample_hz"],
            "action_sha256": action_sha256(compiled["egress"]),
            "raw_c_order_sha256": hashlib.sha256(
                compiled["egress"].tobytes(order="C")
            ).hexdigest(),
            "npy_path": str(egress_path),
            "npy_sha256": sha256_file(egress_path),
            "preview": egress_preview,
        },
        "capture_and_return": {
            "sample_count": int(len(compiled["main"])),
            "duration_seconds": (len(compiled["main"]) - 1)
            / compiled["sample_hz"],
            "action_sha256": action_sha256(compiled["main"]),
            "raw_c_order_sha256": hashlib.sha256(
                compiled["main"].tobytes(order="C")
            ).hexdigest(),
            "npy_path": str(main_path),
            "npy_sha256": sha256_file(main_path),
            "capture_slices": compiled["capture_slices"],
            "preview": main_preview,
        },
        "maximum_commanded_slew_degrees_per_second": maximum_rate,
        "calibrated_limits": {
            "minimum": lower.tolist(),
            "maximum": upper.tolist(),
            "passed": limits_pass,
            "follower_calibration_sha256": preflight[
                "follower_calibration_sha256"
            ],
        },
        "external_clearance": distance,
        "visibility": visibility,
        "final_anchor_prior_receipt_path": str(anchor_receipt_path),
        "final_anchor_prior_receipt_sha256": sha256_file(anchor_receipt_path),
        "gates": gates,
        "reviewer": {
            "kind": "deterministic_static_gate_reviewer",
            "decision": reviewer_decision,
            "evidence_anchor": 100 if reviewer_decision == "CONTINUE" else 75,
        },
        "physical_motion_commanded": False,
        "camera_opened": False,
        "gateway_constructed": False,
        "counted_physical_attempts": 0,
    }
    receipt_path = output_root / "evaluation.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt["receipt_path"] = str(receipt_path)
    receipt["receipt_sha256"] = sha256_file(receipt_path)
    return receipt
