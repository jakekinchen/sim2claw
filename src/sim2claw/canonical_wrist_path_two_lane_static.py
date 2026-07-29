"""Uniform two-lane static path successor for the CC02 reset envelope."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_seeded_action_static_v2 as _static_v2
from . import canonical_wrist_path_static as _wrist
from .current_workcell import current_square_center
from .paths import REPO_ROOT


class CanonicalWristPathTwoLaneStaticError(RuntimeError):
    """The frozen two-lane static successor failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalWristPathTwoLaneStaticError(
            "two-lane input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CanonicalWristPathTwoLaneStaticError(
            f"two-lane input changed: {path}"
        )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def _compile_two_lane(
    *,
    model: mujoco.MjModel,
    addresses: list[int],
    live_seed: np.ndarray,
    candidate_config: Mapping[str, Any],
    source_xyz: np.ndarray,
    direction: np.ndarray,
    wrist_roll_rad: float,
    contact_offset_m: float,
    contact_height_m: float,
    clearance_height_m: float,
    stroke_m: float,
    closed_jaw_rad: float,
    sample_hz: float,
    target_rates: np.ndarray,
    maximum_ik_residual_m: float,
    precontact_backoff_m: float,
    lateral_offsets_m: tuple[float, float],
) -> tuple[np.ndarray, dict[str, Any]]:
    lateral = np.asarray(
        [-direction[1], direction[0], 0.0], dtype=np.float64
    )
    lane_actions: list[np.ndarray] = []
    lane_metrics: list[dict[str, Any]] = []
    for offset in lateral_offsets_m:
        action, metrics = _wrist._compile(
            model=model,
            addresses=addresses,
            live_seed=live_seed,
            candidate_config=candidate_config,
            source_xyz=source_xyz + lateral * offset,
            direction=direction,
            wrist_roll_rad=wrist_roll_rad,
            contact_offset_m=contact_offset_m,
            contact_height_m=contact_height_m,
            clearance_height_m=clearance_height_m,
            stroke_m=stroke_m,
            closed_jaw_rad=closed_jaw_rad,
            sample_hz=sample_hz,
            target_rates=target_rates,
            maximum_ik_residual_m=maximum_ik_residual_m,
            precontact_backoff_m=precontact_backoff_m,
        )
        lane_actions.append(action)
        lane_metrics.append(metrics)
    bridge = _static._interpolate_targets(
        [lane_actions[0][-1], live_seed],
        candidate_config,
        sample_hz=sample_hz,
        target_rates=target_rates,
    )
    action = np.vstack(
        (lane_actions[0], bridge[1:], lane_actions[1][1:])
    ).astype("<f8", copy=False)
    if not np.array_equal(action[0], live_seed):
        raise CanonicalWristPathTwoLaneStaticError(
            "two-lane row zero changed"
        )
    return action, {
        "lane_metrics": lane_metrics,
        "lateral_offsets_m": list(lateral_offsets_m),
        "return_to_live_seed_between_lanes": True,
        "action_rows": len(action),
        "action_raw_float64le_sha256": hashlib.sha256(
            action.tobytes(order="C")
        ).hexdigest(),
    }


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    if output_directory.exists():
        raise CanonicalWristPathTwoLaneStaticError(
            "immutable two-lane output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "base_contract",
        "base_static_receipt",
        "predecessor_closeout",
        "implementation",
        "two_lane_override",
        "output_directory",
        "unchanged_from_stroke_v5",
        "claim_boundary",
    }
    override = contract.get("two_lane_override")
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.canonical_wrist_path_two_lane_static_successor.v6"
        or not all(contract["unchanged_from_stroke_v5"].values())
        or override
        != {
            "lateral_offsets_m": [-0.003, 0.003],
            "stroke_m": 0.066,
            "return_to_live_seed_between_lanes": True,
            "derivation": (
                "the two endpoints of the frozen plus/minus 0.003 m "
                "lateral reset envelope"
            ),
            "only_outcome_relevant_change": True,
        }
    ):
        raise CanonicalWristPathTwoLaneStaticError(
            "two-lane contract widened"
        )
    stroke_contract = _json(contract["base_contract"])
    stroke_receipt = _json(contract["base_static_receipt"])
    _bound(contract["predecessor_closeout"])
    _bound(contract["implementation"])
    if (
        stroke_contract.get("schema_version")
        != "sim2claw.canonical_wrist_path_stroke_static_successor.v5"
        or stroke_receipt.get("status")
        != "canonical_wrist_path_stroke_static_pass"
        or not stroke_receipt.get("passed")
        or stroke_receipt.get("statically_eligible_family_count") != 4
    ):
        raise CanonicalWristPathTwoLaneStaticError(
            "two-lane predecessor changed"
        )
    v4 = _json(stroke_contract["base_contract"])
    base = _json(v4["base_contract"])
    for name, binding in base["inputs"].items():
        if name != "implementation":
            _bound(binding)
    manifest = _json(base["inputs"]["candidate_manifest"])
    rigid = _json(base["inputs"]["registration_candidate"])
    model, addresses, robot_bodies, jaw_bodies = (
        _static_v2._calibrated_registered_model(
            _static._registered_current_model,
            manifest["candidate_config"],
        )(rigid, float(base["simulation"]["timestep_s"]))
    )
    live_seed = np.asarray(
        base["live_seed"]["model_radians"], dtype=np.float64
    )
    initial = mujoco.MjData(model)
    initial.qpos[addresses] = live_seed
    mujoco.mj_forward(model, initial)
    families = {row["case_id"]: row for row in _static._families(model)}
    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    width, height = base["camera_gate"]["image_size_px"]
    rates = np.asarray(
        base["action"]["target_rates_per_joint"], dtype=np.float64
    )
    results: list[dict[str, Any]] = []
    admitted: list[tuple[dict[str, Any], np.ndarray]] = []
    for case in stroke_contract["cases"]:
        family = families[case["case_id"]]
        selected_id = _static._named_id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            family["selected_piece_id"],
        )
        source_xyz = initial.xpos[selected_id].copy()
        source = np.asarray(
            current_square_center(family["source_square"]),
            dtype=np.float64,
        )
        destination = np.asarray(
            current_square_center(family["destination_square"]),
            dtype=np.float64,
        )
        direction = destination - source
        direction /= np.linalg.norm(direction)
        wrist_roll = float(
            base["grid"]["wrist_roll_targets_rad"][
                case["wrist_orientation_index"]
            ]
        )
        contact_height = float(
            base["grid"]["contact_heights_m"][
                case["contact_height_index"]
            ]
        )
        row: dict[str, Any] = {
            **family,
            **case,
            "wrist_roll_target_rad": wrist_roll,
            "contact_height_m": contact_height,
            "stroke_m": float(override["stroke_m"]),
            "lateral_offsets_m": override["lateral_offsets_m"],
        }
        try:
            action, compile_metrics = _compile_two_lane(
                model=model,
                addresses=addresses,
                live_seed=live_seed,
                candidate_config=manifest["candidate_config"],
                source_xyz=source_xyz,
                direction=direction,
                wrist_roll_rad=wrist_roll,
                contact_offset_m=float(base["grid"]["contact_offset_m"]),
                contact_height_m=contact_height,
                clearance_height_m=float(
                    base["grid"]["clearance_height_m"]
                ),
                stroke_m=float(override["stroke_m"]),
                closed_jaw_rad=float(base["action"]["closed_jaw_rad"]),
                sample_hz=float(base["action"]["sample_hz"]),
                target_rates=rates,
                maximum_ik_residual_m=float(
                    base["gates"]["maximum_ik_residual_m"]
                ),
                precontact_backoff_m=0.035,
                lateral_offsets_m=(-0.003, 0.003),
            )
        except (RuntimeError, ValueError) as error:
            results.append(
                {
                    **row,
                    "status": "compile_reject",
                    "error": str(error),
                    "static_eligible": False,
                }
            )
            continue
        collision = _static._static_audit(
            model,
            addresses,
            live_seed,
            action,
            family["selected_piece_id"],
            robot_bodies,
            jaw_bodies,
        )
        gateway = _static._gateway_audit(
            action, manifest["candidate_config"], base
        )
        lateral = np.asarray(
            [-direction[1], direction[0], 0.0], dtype=np.float64
        )
        camera_points = [
            source_xyz + lateral * offset
            for offset in (-0.003, 0.003)
        ] + [
            source_xyz
            + lateral * offset
            + direction * float(override["stroke_m"])
            for offset in (-0.003, 0.003)
        ]
        pixels = _static.project(camera, np.asarray(camera_points))
        camera_margin = float(
            np.min(
                np.column_stack(
                    (
                        pixels[:, 0],
                        width - pixels[:, 0],
                        pixels[:, 1],
                        height - pixels[:, 1],
                    )
                )
            )
        )
        witness = _wrist._first_contact_witness(
            model=model,
            addresses=addresses,
            seed=live_seed,
            action=action,
            selected_name=family["selected_piece_id"],
            jaw_bodies=jaw_bodies,
        )
        checks = {
            "collision": collision["passed"],
            "gateway_limits": gateway[
                "all_rows_inside_calibrated_limits"
            ],
            "gateway_rates": gateway[
                "all_rates_within_gateway_limits"
            ],
            "camera": camera_margin
            >= base["camera_gate"]["minimum_margin_px"],
            "contact_witness": witness["observed"],
            "contact_height": witness["observed"]
            and witness[
                "contact_height_relative_initial_pawn_root_m"
            ]
            <= base["gates"]["maximum_first_contact_height_m"],
            "contact_normal": witness["observed"]
            and witness["absolute_vertical_normal_component"]
            <= base["gates"]["maximum_first_contact_abs_vertical_normal"],
        }
        result = {
            **row,
            "compile": compile_metrics,
            "collision": collision,
            "gateway": gateway,
            "camera": {
                "minimum_margin_px": camera_margin,
                "passed": checks["camera"],
            },
            "first_contact_witness": witness,
            "checks": checks,
            "static_eligible": all(checks.values()),
        }
        result["status"] = (
            "static_eligible"
            if result["static_eligible"]
            else "static_reject"
        )
        results.append(result)
        if result["static_eligible"]:
            admitted.append((result, action))
    output_directory.mkdir(parents=True)
    action_directory = output_directory / "actions"
    action_directory.mkdir()
    selected = []
    for index, (row, action) in enumerate(admitted):
        path = action_directory / f"{index:02d}.f64le"
        path.write_bytes(action.tobytes(order="C"))
        selected.append(
            {
                **row,
                "action_path": str(path.relative_to(REPO_ROOT)),
                "action_sha256": _sha(path),
                "action_shape": list(action.shape),
            }
        )
    counts = {
        direction: sum(row["direction"] == direction for row in selected)
        for direction in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    passed = len(selected) == 4 and counts == {
        "REAL_TO_SIM": 2,
        "SIM_TO_REAL": 2,
    }
    receipt = {
        "schema_version": (
            "sim2claw.canonical_wrist_path_two_lane_static_receipt.v1"
        ),
        "status": (
            "canonical_wrist_path_two_lane_static_pass"
            if passed
            else "canonical_wrist_path_two_lane_static_reject"
        ),
        "proof_class": (
            "cpu_fp64_four_family_two_lane_static_action_freeze"
        ),
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "family_count": 4,
        "grid_result_count": len(results),
        "statically_eligible_family_count": len(selected),
        "selected": selected,
        "direction_counts": counts,
        "minimum_per_direction": 2,
        "passed": passed,
        "grid_results": results,
        "dynamic_replay_executed": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": base["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CanonicalWristPathTwoLaneStaticError",
    "enumerate_and_freeze",
]
