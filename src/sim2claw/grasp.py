"""Scripted single-piece grasp probe for the photo-aligned chess workcell.

This module drives one attached SO-101 through a constructed side pinch of a
rotation-symmetric chess piece: hover beside the piece, advance, close the
jaw under the crown flange, and lift. It is a simulation capability probe
with a written receipt — it grants no policy, hardware, or physical claim.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .paths import DEFAULT_OUTPUT_ROOT
from .render import write_rgb_png
from .scene import ROBOT_JOINTS, build_scene_spec, initialize_robot_poses

REACH_JOINTS = ROBOT_JOINTS[:5]
JAW_OPEN_RAD = 1.35
JAW_SHUT_RAD = -0.28
SETTLE_STEPS = 300
LIFT_HEIGHT_M = 0.14
SUCCESS_RISE_M = 0.04

# Neck heights above each piece origin where a pinch clears the base discs
# but sits under a wider crown feature that catches the jaw during lift.
NECK_HEIGHT_M = {
    "rook": 0.030,
    "queen": 0.033,
    "king": 0.034,
    "bishop": 0.029,
    "pawn": 0.039,
    "knight": 0.028,
}
PREFERRED_KINDS = ("rook", "queen", "bishop", "pawn", "king", "knight")


@dataclass
class GraspPhase:
    name: str
    steps: int
    tip_error_m: float
    piece_height_m: float
    jaw_piece_contacts: int


@dataclass
class GraspReport:
    piece: str
    arm: str
    mount_distance_m: float
    initial_piece_height_m: float
    final_piece_height_m: float
    piece_rise_m: float
    lift_contact_fraction: float
    success: bool
    phases: list[GraspPhase] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    proof_class: str = "simulation_scripted_grasp_probe"
    physical_authority: bool = False


class GraspSetupError(RuntimeError):
    """The scene does not expose what the grasp probe requires."""


def _named_id(model: mujoco.MjModel, kind: mujoco.mjtObj, name: str) -> int:
    resolved = mujoco.mj_name2id(model, kind, name)
    if resolved < 0:
        raise GraspSetupError(f"scene is missing required element: {name}")
    return resolved


def _jaw_tip_point(model: mujoco.MjModel, data: mujoco.MjData, arm: str) -> np.ndarray:
    tips = [
        _named_id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{arm}_fixed_jaw_sph_tip{index}")
        for index in (1, 2, 3)
    ]
    return np.mean([data.geom_xpos[tip] for tip in tips], axis=0)


def _pinch_offset(
    model: mujoco.MjModel, data: mujoco.MjData, arm: str
) -> np.ndarray:
    """Calibrate the pad-gap center relative to the fixed-jaw tip cluster.

    Kinematically shuts the jaw on a scratch copy of the state, finds the
    moving-pad geom nearest the fixed tips, and expresses the midpoint as an
    offset in the tip body frame. Reach solves then aim this pinch point, so
    pieces land between the pads instead of at the fingertip.
    """

    scratch = mujoco.MjData(model)
    scratch.qpos[:] = data.qpos
    jaw_joint = _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{arm}_gripper")
    scratch.qpos[model.jnt_qposadr[jaw_joint]] = 0.08
    mujoco.mj_forward(model, scratch)

    tips = _jaw_tip_point(model, scratch, arm)
    moving_body = _named_id(
        model, mujoco.mjtObj.mjOBJ_BODY, f"{arm}_moving_jaw_so101_v1"
    )
    pad_candidates = [
        np.array(scratch.geom_xpos[geom_id])
        for geom_id in range(model.ngeom)
        if int(model.geom_bodyid[geom_id]) == moving_body
        and model.geom_contype[geom_id] != 0
    ]
    if not pad_candidates:
        raise GraspSetupError("moving jaw exposes no collision geoms")
    pad = min(pad_candidates, key=lambda point: float(np.linalg.norm(point - tips)))
    midpoint = (tips + pad) / 2.0

    tip_geom = _named_id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{arm}_fixed_jaw_sph_tip2")
    tip_body = int(model.geom_bodyid[tip_geom])
    rotation = np.array(scratch.xmat[tip_body]).reshape(3, 3)
    return rotation.T @ (midpoint - tips)


def _pinch_point(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    arm: str,
    offset_local: np.ndarray,
) -> np.ndarray:
    tip_geom = _named_id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{arm}_fixed_jaw_sph_tip2")
    tip_body = int(model.geom_bodyid[tip_geom])
    rotation = np.array(data.xmat[tip_body]).reshape(3, 3)
    return _jaw_tip_point(model, data, arm) + rotation @ offset_local


def _jaw_body_ids(model: mujoco.MjModel, arm: str) -> set[int]:
    fixed_geom = _named_id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{arm}_fixed_jaw_box1")
    moving_body = _named_id(
        model, mujoco.mjtObj.mjOBJ_BODY, f"{arm}_moving_jaw_so101_v1"
    )
    return {int(model.geom_bodyid[fixed_geom]), moving_body}


def _arm_dof_columns(model: mujoco.MjModel, arm: str) -> list[int]:
    columns = []
    for joint in REACH_JOINTS:
        joint_id = _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{arm}_{joint}")
        columns.append(int(model.jnt_dofadr[joint_id]))
    return columns


def _actuator_map(model: mujoco.MjModel, arm: str) -> dict[str, int]:
    return {
        joint: _named_id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"{arm}_{joint}")
        for joint in ROBOT_JOINTS
    }


def _piece_bodies(model: mujoco.MjModel) -> dict[str, int]:
    pieces = {}
    for body_id in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        if name and "_" in name and name.split("_")[0] in ("white", "black"):
            pieces[name] = body_id
    if len(pieces) != 32:
        raise GraspSetupError(f"expected 32 chess pieces, found {len(pieces)}")
    return pieces


def _select_piece(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    mount: np.ndarray,
    requested: str | None,
) -> tuple[str, int]:
    pieces = _piece_bodies(model)
    if requested is not None:
        if requested not in pieces:
            raise GraspSetupError(f"unknown piece body: {requested}")
        return requested, pieces[requested]
    best: tuple[float, str, int] | None = None
    for kind in PREFERRED_KINDS:
        for name, body_id in pieces.items():
            if name.split("_")[1] != kind:
                continue
            distance = float(np.linalg.norm(data.xpos[body_id][:2] - mount[:2]))
            if best is None or distance < best[0]:
                best = (distance, name, body_id)
        if best is not None:
            return best[1], best[2]
    raise GraspSetupError("no candidate piece found")


def _solve_reach(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    arm: str,
    target: np.ndarray,
    pinch_local: np.ndarray,
    *,
    iterations: int = 160,
    damping: float = 0.02,
    step_limit: float = 0.15,
) -> tuple[dict[str, float], float]:
    """Damped least-squares position solve for the five reach joints.

    Solves on a scratch copy so the live simulation state is never moved
    kinematically. Returns the solved reach pose and the residual pinch-point
    distance in meters; callers drive actuators toward the pose.
    """

    scratch = mujoco.MjData(model)
    scratch.qpos[:] = data.qpos
    columns = _arm_dof_columns(model, arm)
    tip_geom = _named_id(model, mujoco.mjtObj.mjOBJ_GEOM, f"{arm}_fixed_jaw_sph_tip2")
    tip_body = int(model.geom_bodyid[tip_geom])
    joint_ids = [
        _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{arm}_{joint}")
        for joint in REACH_JOINTS
    ]
    jacp = np.zeros((3, model.nv))
    identity = np.eye(3)
    residual = float("inf")
    for _ in range(iterations):
        mujoco.mj_forward(model, scratch)
        tip = _pinch_point(model, scratch, arm, pinch_local)
        error = target - tip
        residual = float(np.linalg.norm(error))
        if residual < 0.0015:
            break
        mujoco.mj_jac(model, scratch, jacp, None, tip, tip_body)
        jacobian = jacp[:, columns]
        gain = jacobian @ jacobian.T + (damping**2) * identity
        update = jacobian.T @ np.linalg.solve(gain, error)
        update = np.clip(update, -step_limit, step_limit)
        for joint_id, delta in zip(joint_ids, update, strict=True):
            address = model.jnt_qposadr[joint_id]
            low, high = model.jnt_range[joint_id]
            scratch.qpos[address] = float(
                np.clip(scratch.qpos[address] + delta, low, high)
            )
    pose = {
        joint: float(scratch.qpos[model.jnt_qposadr[joint_id]])
        for joint, joint_id in zip(REACH_JOINTS, joint_ids, strict=True)
    }
    return pose, residual


def _drive(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    actuators: dict[str, int],
    reach_targets: dict[str, float],
    jaw_target: float,
    steps: int,
    *,
    piece_body: int,
    jaw_bodies: set[int],
) -> tuple[int, int]:
    """Step physics toward actuator targets; count jaw-piece contact steps."""

    start: dict[str, float] = {}
    for joint, actuator_id in actuators.items():
        start[joint] = float(data.ctrl[actuator_id])
    goal = {
        joint: (jaw_target if joint == "gripper" else reach_targets[joint])
        for joint in actuators
    }
    ramp_steps = max(1, min(steps // 2, 160))
    contact_steps = 0
    for step_index in range(steps):
        blend = min(1.0, (step_index + 1) / ramp_steps)
        for joint, actuator_id in actuators.items():
            data.ctrl[actuator_id] = start[joint] + blend * (
                goal[joint] - start[joint]
            )
        mujoco.mj_step(model, data)
        touching = False
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            bodies = {
                int(model.geom_bodyid[contact.geom1]),
                int(model.geom_bodyid[contact.geom2]),
            }
            if piece_body in bodies and bodies & jaw_bodies:
                touching = True
                break
        if touching:
            contact_steps += 1
    return contact_steps, steps


def _reach_pose(model: mujoco.MjModel, data: mujoco.MjData, arm: str) -> dict[str, float]:
    pose = {}
    for joint in REACH_JOINTS:
        joint_id = _named_id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{arm}_{joint}")
        pose[joint] = float(data.qpos[model.jnt_qposadr[joint_id]])
    return pose


def run_grasp_probe(
    *,
    arm: str = "left",
    piece: str | None = None,
    output_root: Path | None = None,
    render_frames: bool = True,
) -> GraspReport:
    if arm not in ("left", "right"):
        raise GraspSetupError("arm must be 'left' or 'right'")
    output_dir = (output_root or DEFAULT_OUTPUT_ROOT) / "grasp_probe"
    output_dir.mkdir(parents=True, exist_ok=True)

    spec = build_scene_spec()
    model = spec.compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    for _ in range(SETTLE_STEPS):
        mujoco.mj_step(model, data)

    mount_body = _named_id(model, mujoco.mjtObj.mjOBJ_BODY, f"{arm}_base")
    mount = np.array(data.xpos[mount_body])
    piece_name, piece_body = _select_piece(model, data, mount, piece)
    kind = piece_name.split("_")[1]
    neck_offset = NECK_HEIGHT_M[kind]

    actuators = _actuator_map(model, arm)
    jaw_bodies = _jaw_body_ids(model, arm)
    pinch_local = _pinch_offset(model, data, arm)
    initial_height = float(data.xpos[piece_body][2])
    report = GraspReport(
        piece=piece_name,
        arm=arm,
        mount_distance_m=float(
            np.linalg.norm(data.xpos[piece_body][:2] - mount[:2])
        ),
        initial_piece_height_m=initial_height,
        final_piece_height_m=initial_height,
        piece_rise_m=0.0,
        lift_contact_fraction=0.0,
        success=False,
    )

    def record_phase(name: str, steps: int, residual: float, contacts: int) -> None:
        report.phases.append(
            GraspPhase(
                name=name,
                steps=steps,
                tip_error_m=round(residual, 5),
                piece_height_m=round(float(data.xpos[piece_body][2]), 5),
                jaw_piece_contacts=contacts,
            )
        )

    def snapshot(tag: str) -> None:
        if not render_frames:
            return
        renderer = mujoco.Renderer(model, height=704, width=1056)
        try:
            renderer.update_scene(data, camera="workcell")
            frame = renderer.render()
        finally:
            renderer.close()
        frame_path = output_dir / f"{tag}.png"
        write_rgb_png(frame_path, frame)
        report.artifacts[tag] = str(frame_path)

    snapshot("00_settled")

    piece_xy = np.array(data.xpos[piece_body][:2])
    away = mount[:2] - piece_xy
    away /= max(float(np.linalg.norm(away)), 1e-9)
    neck = np.array(
        [piece_xy[0], piece_xy[1], float(data.xpos[piece_body][2]) + neck_offset]
    )
    stand_off = neck + np.array([away[0] * 0.055, away[1] * 0.055, 0.03])

    pose, residual = _solve_reach(model, data, arm, stand_off, pinch_local)
    contacts, steps = _drive(
        model, data, actuators, pose, JAW_OPEN_RAD, 420,
        piece_body=piece_body, jaw_bodies=jaw_bodies,
    )
    record_phase("stand_off", steps, residual, contacts)
    snapshot("01_stand_off")

    pose, residual = _solve_reach(model, data, arm, neck, pinch_local)
    contacts, steps = _drive(
        model, data, actuators, pose, JAW_OPEN_RAD, 380,
        piece_body=piece_body, jaw_bodies=jaw_bodies,
    )
    record_phase("advance", steps, residual, contacts)
    snapshot("02_advance")

    contacts, steps = _drive(
        model, data, actuators, pose, JAW_SHUT_RAD, 420,
        piece_body=piece_body, jaw_bodies=jaw_bodies,
    )
    record_phase("close", steps, 0.0, contacts)
    snapshot("03_close")

    lifted = neck + np.array([0.0, 0.0, LIFT_HEIGHT_M])
    lift_pose, residual = _solve_reach(model, data, arm, lifted, pinch_local)
    lift_contacts, lift_steps = _drive(
        model, data, actuators, lift_pose, JAW_SHUT_RAD, 500,
        piece_body=piece_body, jaw_bodies=jaw_bodies,
    )
    record_phase("lift", lift_steps, residual, lift_contacts)

    hold_contacts, hold_steps = _drive(
        model, data, actuators, lift_pose, JAW_SHUT_RAD, 300,
        piece_body=piece_body, jaw_bodies=jaw_bodies,
    )
    record_phase("hold", hold_steps, 0.0, hold_contacts)
    snapshot("04_lifted")

    report.final_piece_height_m = float(data.xpos[piece_body][2])
    report.piece_rise_m = report.final_piece_height_m - initial_height
    report.lift_contact_fraction = (lift_contacts + hold_contacts) / float(
        lift_steps + hold_steps
    )
    report.success = (
        report.piece_rise_m >= SUCCESS_RISE_M and report.lift_contact_fraction >= 0.6
    )

    receipt_path = output_dir / "grasp_probe_receipt.json"
    receipt_path.write_text(
        json.dumps(asdict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report.artifacts["receipt"] = str(receipt_path)
    return report
