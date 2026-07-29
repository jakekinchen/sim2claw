"""Bounded four-family stroke-only static successor for CC02."""

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


class CanonicalWristPathStrokeStaticError(RuntimeError):
    """The frozen stroke-only static successor failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalWristPathStrokeStaticError(
            "stroke successor input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CanonicalWristPathStrokeStaticError(
            f"stroke successor input changed: {path}"
        )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    if output_directory.exists():
        raise CanonicalWristPathStrokeStaticError(
            "immutable stroke successor output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "base_contract",
        "predecessor_closeout",
        "implementation",
        "stroke_override",
        "cases",
        "output_directory",
        "unchanged_from_v4",
        "claim_boundary",
    }
    override = contract.get("stroke_override")
    cases = contract.get("cases")
    if (
        set(contract) != expected
        or contract.get("schema_version")
        != "sim2claw.canonical_wrist_path_stroke_static_successor.v5"
        or not all(contract["unchanged_from_v4"].values())
        or override
        != {
            "from_m": 0.06,
            "to_m": 0.066,
            "derivation": (
                "existing 0.060 m stroke plus the full 0.006 m "
                "span of the frozen plus/minus 0.003 m reset uncertainty"
            ),
            "only_outcome_relevant_change": True,
        }
        or not isinstance(cases, list)
        or len(cases) != 4
        or len({row.get("case_id") for row in cases}) != 4
        or sum(row.get("direction") == "REAL_TO_SIM" for row in cases) != 2
        or sum(row.get("direction") == "SIM_TO_REAL" for row in cases) != 2
    ):
        raise CanonicalWristPathStrokeStaticError(
            "stroke successor contract widened"
        )
    v4 = _json(contract["base_contract"])
    _bound(contract["predecessor_closeout"])
    _bound(contract["implementation"])
    if (
        v4.get("schema_version")
        != "sim2claw.canonical_wrist_path_static_successor.v4"
        or v4["path_shape_override"]["precontact_backoff_m"] != 0.035
    ):
        raise CanonicalWristPathStrokeStaticError(
            "stroke successor V4 base changed"
        )
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
    image_width, image_height = base["camera_gate"]["image_size_px"]
    target_rates = np.asarray(
        base["action"]["target_rates_per_joint"], dtype=np.float64
    )
    grid_results: list[dict[str, Any]] = []
    frozen: list[tuple[dict[str, Any], np.ndarray]] = []
    for case in cases:
        family = families.get(case["case_id"])
        if (
            family is None
            or case["case_id"] in set(base["quarantine"]["case_ids"])
            or case["contact_height_index"] != 0
            or case["wrist_orientation_index"] not in {0, 1, 2}
        ):
            raise CanonicalWristPathStrokeStaticError(
                "stroke successor case changed"
            )
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
        wrist_index = int(case["wrist_orientation_index"])
        height_index = int(case["contact_height_index"])
        wrist_roll = float(
            base["grid"]["wrist_roll_targets_rad"][wrist_index]
        )
        contact_height = float(
            base["grid"]["contact_heights_m"][height_index]
        )
        row: dict[str, Any] = {
            **family,
            **case,
            "wrist_roll_target_rad": wrist_roll,
            "contact_height_m": contact_height,
            "contact_offset_m": float(base["grid"]["contact_offset_m"]),
            "stroke_m": float(override["to_m"]),
        }
        try:
            action, compile_metrics = _wrist._compile(
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
                stroke_m=float(override["to_m"]),
                closed_jaw_rad=float(base["action"]["closed_jaw_rad"]),
                sample_hz=float(base["action"]["sample_hz"]),
                target_rates=target_rates,
                maximum_ik_residual_m=float(
                    base["gates"]["maximum_ik_residual_m"]
                ),
                precontact_backoff_m=0.035,
            )
        except (RuntimeError, ValueError) as error:
            grid_results.append(
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
        terminal = source_xyz + direction * float(override["to_m"])
        pixels = _static.project(
            camera, np.asarray([source_xyz, terminal])
        )
        camera_margin = float(
            np.min(
                np.column_stack(
                    (
                        pixels[:, 0],
                        image_width - pixels[:, 0],
                        pixels[:, 1],
                        image_height - pixels[:, 1],
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
        grid_results.append(result)
        if result["static_eligible"]:
            frozen.append((result, action))
    output_directory.mkdir(parents=True)
    action_directory = output_directory / "actions"
    action_directory.mkdir()
    selected = []
    for index, (row, action) in enumerate(frozen):
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
            "sim2claw.canonical_wrist_path_stroke_static_receipt.v1"
        ),
        "status": (
            "canonical_wrist_path_stroke_static_pass"
            if passed
            else "canonical_wrist_path_stroke_static_reject"
        ),
        "proof_class": (
            "cpu_fp64_four_family_66mm_stroke_static_action_freeze"
        ),
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "family_count": 4,
        "grid_result_count": len(grid_results),
        "statically_eligible_family_count": len(selected),
        "selected": selected,
        "direction_counts": counts,
        "minimum_per_direction": 2,
        "passed": passed,
        "grid_results": grid_results,
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
    "CanonicalWristPathStrokeStaticError",
    "enumerate_and_freeze",
]
