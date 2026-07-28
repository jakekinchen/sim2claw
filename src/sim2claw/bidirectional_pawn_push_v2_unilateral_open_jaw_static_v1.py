"""V05-UF unilateral open-jaw pawn-push static wrapper."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import bidirectional_pawn_push_v2_multistart_approach_static as _multi
from . import bidirectional_pawn_push_v2_ramped_funnel_static_v1 as _base
from . import bidirectional_pawn_push_v2_temporal_static as _static
from .grasp import _jaw_tip_point
from .paths import REPO_ROOT


UnilateralOpenJawStaticV1Error = _base.RampedFunnelStaticV1Error


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise UnilateralOpenJawStaticV1Error(
            "V05-UF path escapes repository"
        ) from error
    return resolved


def _verify(entry: Mapping[str, Any]) -> Path:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise UnilateralOpenJawStaticV1Error(
            f"bound V05-UF input changed: {path}"
        )
    return path


def _named_id(
    model: mujoco.MjModel,
    object_type: mujoco.mjtObj,
    name: str,
) -> int:
    object_id = mujoco.mj_name2id(model, object_type, name)
    if object_id < 0:
        raise UnilateralOpenJawStaticV1Error(
            f"required V05-UF object is missing: {name}"
        )
    return int(object_id)


def _moving_tip_offset(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    arm: str,
) -> np.ndarray:
    fixed_tip = _jaw_tip_point(model, data, arm)
    moving_tip_ids = [
        _named_id(
            model,
            mujoco.mjtObj.mjOBJ_GEOM,
            f"{arm}_moving_jaw_sph_tip{index}",
        )
        for index in (1, 2, 3)
    ]
    moving_tip = np.mean(
        [np.asarray(data.geom_xpos[index]) for index in moving_tip_ids],
        axis=0,
    )
    fixed_tip_geom = _named_id(
        model,
        mujoco.mjtObj.mjOBJ_GEOM,
        f"{arm}_fixed_jaw_sph_tip2",
    )
    fixed_body = int(model.geom_bodyid[fixed_tip_geom])
    rotation = np.asarray(data.xmat[fixed_body]).reshape(3, 3)
    return rotation.T @ (moving_tip - fixed_tip)


def _contact_side(
    cartesian_waypoints: list[np.ndarray],
) -> str:
    if len(cartesian_waypoints) < 4:
        raise UnilateralOpenJawStaticV1Error(
            "V05-UF guiding path is incomplete"
        )
    guide = np.asarray(cartesian_waypoints[1], dtype=np.float64)
    contact = np.asarray(cartesian_waypoints[2], dtype=np.float64)
    terminal = np.asarray(cartesian_waypoints[-1], dtype=np.float64)
    direction = terminal - contact
    direction[2] = 0.0
    norm = float(np.linalg.norm(direction))
    if norm <= 0.0:
        raise UnilateralOpenJawStaticV1Error(
            "V05-UF planar push direction changed"
        )
    direction /= norm
    perpendicular = np.asarray(
        [-direction[1], direction[0], 0.0],
        dtype=np.float64,
    )
    signed_guide = float(np.dot(guide - contact, perpendicular))
    if abs(signed_guide) < 0.002999:
        raise UnilateralOpenJawStaticV1Error(
            "V05-UF contact-side guide quantum changed"
        )
    return "fixed_jaw" if signed_guide < 0.0 else "moving_jaw"


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    public_contract = _resolve(contract_path)
    public_output = _resolve(output_directory)
    contract = json.loads(public_contract.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_unilateral_open_jaw_static.v1"
    ):
        raise UnilateralOpenJawStaticV1Error(
            "unexpected V05-UF static contract"
        )
    authorization_path = _verify(contract["authorization"])
    base_contract_path = _verify(contract["base_static_contract"])
    _verify(contract["v05_ue_static_receipt"])
    _verify(contract["base_implementation"])
    _verify(contract["multistart_implementation"])
    _verify(contract["temporal_static_implementation"])
    _verify(contract["implementation"])
    authorization = json.loads(
        authorization_path.read_text(encoding="utf-8")
    )
    base = json.loads(base_contract_path.read_text(encoding="utf-8"))
    overrides = contract["frozen_overrides"]
    if int(overrides["maximum_total_cells"]) != 576:
        raise UnilateralOpenJawStaticV1Error("V05-UF cell budget changed")
    if authorization["quarantine"]["case_ids"] != overrides[
        "quarantine_case_ids"
    ]:
        raise UnilateralOpenJawStaticV1Error(
            "V05-UF quarantine binding changed"
        )

    derived = copy.deepcopy(base)
    derived.update(
        {
            "enumeration_id": (
                "bidirectional-pawn-push-v2-unilateral-open-jaw-"
                "static-derived-v1"
            ),
            "status": (
                "compatibility_scaffold_derived_from_v05_ue_"
                "before_model_loading"
            ),
            "authorization": contract["authorization"],
        }
    )
    derived["implementation"] = contract["base_implementation"]
    public_output.mkdir(parents=True, exist_ok=True)
    derived_path = public_output / "derived_contract.json"
    derived_path.write_text(
        json.dumps(derived, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    open_jaw = float(overrides["open_jaw_target_rad"])
    source_jaw = float(overrides["source_jaw_model_rad"])
    sample_hz = float(overrides["sample_hz"])
    open_speed = float(overrides["jaw_opening_speed_percent_per_second"])
    state: dict[str, str | None] = {"expected_side": None}
    original_compile = _multi._compile_action
    original_pinch_offset = _multi._pinch_offset
    original_collision_audit = _static._collision_audit

    def unilateral_compile(
        *,
        model: mujoco.MjModel,
        qpos_addresses: list[int],
        wrapper: Mapping[str, Any],
        source_model: np.ndarray,
        branch_model: np.ndarray,
        cartesian_waypoints: list[np.ndarray],
        **kwargs: Any,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        side = _contact_side(cartesian_waypoints)
        state["expected_side"] = side

        def unilateral_tip_offset(
            local_model: mujoco.MjModel,
            local_data: mujoco.MjData,
            arm: str,
        ) -> np.ndarray:
            if side == "fixed_jaw":
                return np.zeros(3, dtype=np.float64)
            return _moving_tip_offset(local_model, local_data, arm)

        _multi._pinch_offset = unilateral_tip_offset
        try:
            open_action, metrics = original_compile(
                model=model,
                qpos_addresses=qpos_addresses,
                wrapper=wrapper,
                source_model=source_model,
                branch_model=branch_model,
                cartesian_waypoints=cartesian_waypoints,
                closed_jaw_rad=open_jaw,
                **{
                    key: value
                    for key, value in kwargs.items()
                    if key != "closed_jaw_rad"
                },
            )
        finally:
            _multi._pinch_offset = original_pinch_offset

        initial = np.asarray(source_model, dtype=np.float64).copy()
        if abs(float(initial[-1]) - source_jaw) > 1e-12:
            raise UnilateralOpenJawStaticV1Error(
                "V05-UF source jaw binding changed"
            )
        endpoints = np.asarray(
            [
                initial,
                np.concatenate((initial[:5], [open_jaw])),
            ],
            dtype="<f8",
        )
        physical = _static._physical_actions(endpoints, wrapper)
        delta_percent = float(abs(physical[1, -1] - physical[0, -1]))
        preamble_samples = max(
            1,
            int(round((delta_percent / open_speed) * sample_hz)),
        )
        preamble = np.asarray(
            [
                initial
                + (endpoints[1] - initial) * (index / preamble_samples)
                for index in range(preamble_samples + 1)
            ],
            dtype="<f8",
        )
        action = np.vstack((preamble, open_action[1:])).astype(
            "<f8",
            copy=False,
        )
        physical_action = _static._physical_actions(action, wrapper)
        constant_start = preamble_samples
        metrics.update(
            {
                "open_jaw_target_rad": open_jaw,
                "source_jaw_model_rad": source_jaw,
                "jaw_opening_preamble_samples": preamble_samples,
                "constant_open_jaw_start_row": constant_start,
                "jaw_opening_speed_percent_per_second": open_speed,
                "maximum_open_jaw_target_error_after_preamble_rad": float(
                    np.max(
                        np.abs(
                            action[constant_start:, -1] - open_jaw
                        )
                    )
                ),
                "jaw_closing_command_observed": bool(
                    np.any(np.diff(action[:, -1]) < -1e-12)
                ),
                "expected_unilateral_contact_side": side,
                "first_physical_degrees_percent": (
                    physical_action[0].tolist()
                ),
                "action_rows": len(action),
                "action_raw_float64le_sha256": hashlib.sha256(
                    action.tobytes(order="C")
                ).hexdigest(),
            }
        )
        return action, metrics

    def unilateral_collision_audit(
        *,
        model: mujoco.MjModel,
        qpos_addresses: list[int],
        seed_model: np.ndarray,
        action: np.ndarray,
        selected_piece_id: str,
        robot_bodies: set[int],
        jaw_bodies: set[int],
    ) -> dict[str, Any]:
        base_audit = original_collision_audit(
            model=model,
            qpos_addresses=qpos_addresses,
            seed_model=seed_model,
            action=action,
            selected_piece_id=selected_piece_id,
            robot_bodies=robot_bodies,
            jaw_bodies=jaw_bodies,
        )
        selected_body = _named_id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            selected_piece_id,
        )
        fixed_geom = _named_id(
            model,
            mujoco.mjtObj.mjOBJ_GEOM,
            "left_fixed_jaw_box1",
        )
        fixed_body = int(model.geom_bodyid[fixed_geom])
        moving_body = _named_id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            "left_moving_jaw_so101_v1",
        )
        board_body = _named_id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            "chess_board",
        )
        data = mujoco.MjData(model)
        sides_seen: set[str] = set()
        simultaneous_bilateral = False
        robot_board_contact = False
        for pose in action:
            data.qpos[qpos_addresses] = pose
            data.qvel[:] = 0.0
            mujoco.mj_forward(model, data)
            pose_sides: set[str] = set()
            for index in range(data.ncon):
                contact = data.contact[index]
                bodies = {
                    int(model.geom_bodyid[int(contact.geom1)]),
                    int(model.geom_bodyid[int(contact.geom2)]),
                }
                if selected_body in bodies:
                    if fixed_body in bodies:
                        pose_sides.add("fixed_jaw")
                    if moving_body in bodies:
                        pose_sides.add("moving_jaw")
                if board_body in bodies and bodies & robot_bodies:
                    robot_board_contact = True
            sides_seen |= pose_sides
            simultaneous_bilateral = (
                simultaneous_bilateral or len(pose_sides) > 1
            )
        expected = state["expected_side"]
        expected_contact = expected in sides_seen
        opposite_contact = bool(sides_seen - {str(expected)})
        strict_pass = (
            base_audit["collision_free"]
            and expected_contact
            and not opposite_contact
            and not simultaneous_bilateral
            and not robot_board_contact
        )
        return {
            **base_audit,
            "static_selected_contact_observed": expected_contact,
            "collision_free": strict_pass,
            "expected_unilateral_contact_side": expected,
            "selected_pawn_contact_sides": sorted(sides_seen),
            "expected_side_contact_observed": expected_contact,
            "opposite_jaw_selected_pawn_contact_observed": opposite_contact,
            "simultaneous_bilateral_selected_pawn_contact_observed": (
                simultaneous_bilateral
            ),
            "selected_pawn_enclosed_or_grasped": (
                opposite_contact or simultaneous_bilateral
            ),
            "robot_board_contact_observed": robot_board_contact,
            "selected_pawn_lift_commanded": False,
        }

    _multi._compile_action = unilateral_compile
    _static._collision_audit = unilateral_collision_audit
    try:
        receipt = _base.enumerate_and_freeze(derived_path, public_output)
    finally:
        _multi._compile_action = original_compile
        _multi._pinch_offset = original_pinch_offset
        _static._collision_audit = original_collision_audit

    passed = (
        receipt["statically_eligible_family_count"] >= 4
        and receipt["lane_counts"] == {
            "REAL_TO_SIM": 2,
            "SIM_TO_REAL": 2,
        }
    )
    receipt.update(
        {
            "schema_version": (
                "sim2claw."
                "bidirectional_pawn_push_v2_unilateral_open_jaw_"
                "static_receipt.v1"
            ),
            "status": (
                "unilateral_open_jaw_static_freeze_pass"
                if passed
                else "unilateral_open_jaw_static_freeze_reject"
            ),
            "proof_class": (
                "cpu_fp64_static_unilateral_open_jaw_pawn_push_"
                "collision_camera_gateway_action_freeze_only"
            ),
            "contract_path": str(public_contract.relative_to(REPO_ROOT)),
            "contract_sha256": _sha(public_contract),
            "derived_contract_path": str(derived_path.relative_to(REPO_ROOT)),
            "derived_contract_sha256": _sha(derived_path),
            "open_jaw_target_rad": open_jaw,
            "modeled_open_aperture_m": overrides[
                "modeled_open_aperture_m"
            ],
            "static_clearance_buffer_m": overrides[
                "static_clearance_buffer_m"
            ],
            "jaw_constant_during_setup_and_push": True,
            "jaw_closing_allowed": False,
            "bilateral_contact_allowed": False,
            "grasp_or_enclosure_allowed": False,
            "selected_pawn_lift_allowed": False,
            "robot_board_contact_allowed": False,
        }
    )
    receipt["claim_boundary"] = (
        "Static-only deterministic unilateral open-jaw pawn-push search. "
        "The open-jaw preamble is followed by a constant jaw command through "
        "setup and push. No grasp, lift, dynamic task outcome, physical "
        "packet, promotion, or transfer claim."
    )
    (public_output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["UnilateralOpenJawStaticV1Error", "enumerate_and_freeze"]
