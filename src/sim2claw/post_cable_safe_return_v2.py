"""Pan-away static successor for the RP04H post-cable safe return."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_seeded_action_static_v2 as _static_v2
from . import post_cable_safe_return as _base
from .coordinated_unloading_shadow_probe import _scene_audit
from .full_range_no_contact_identification import _clearance_audit
from .physical_canary import _physical_to_model_position


def compile_return_v2(
    contract_path: Path, output_directory: Path
) -> dict[str, Any]:
    _base._require(
        not output_directory.exists(), "immutable RP04H V2 output exists"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _base._require(
        contract.get("schema_version")
        == "sim2claw.post_cable_safe_return_static.v2"
        and contract["authority"]
        == {
            "model_loading": True,
            "static_simulation": True,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "mapping_approval": False,
            "transfer_claim": False,
        },
        "RP04H V2 static authority changed",
    )
    for entry in contract["inputs"].values():
        _base._bound(entry)
    manifest = json.loads(
        _base._bound(contract["inputs"]["candidate_manifest"]).read_text(
            encoding="utf-8"
        )
    )
    rigid = json.loads(
        _base._bound(
            contract["inputs"]["registered_rigid_candidate"]
        ).read_text(encoding="utf-8")
    )
    waypoints = [
        np.asarray(row, dtype="<f8") for row in contract["route"]["waypoints"]
    ]
    _base._require(len(waypoints) == 4, "RP04H V2 waypoint count changed")
    maximum_step = float(contract["route"]["maximum_step_degrees"])
    parts = [
        _base._interpolate(start, target, maximum_step)
        for start, target in zip(waypoints[:-1], waypoints[1:], strict=True)
    ]
    physical = np.asarray(
        np.vstack((parts[0], parts[1][1:], parts[2][1:])),
        dtype="<f8",
        order="C",
    )
    physical[0] = waypoints[0]
    physical[-1] = waypoints[-1]
    boundaries = [
        len(parts[0]) - 1,
        len(parts[0]) + len(parts[1]) - 2,
        len(physical) - 1,
    ]
    _base._require(
        list(physical.shape) == contract["route"]["expected_shape"]
        and boundaries == contract["route"]["stage_boundary_rows"]
        and np.array_equal(physical[0], waypoints[0])
        and np.array_equal(physical[-1], waypoints[-1]),
        "RP04H V2 route denominator changed",
    )
    candidate = manifest["candidate_config"]
    model_actions = np.asarray(
        _physical_to_model_position(physical, candidate),
        dtype="<f8",
        order="C",
    )
    builder = _static_v2._calibrated_registered_model(
        _static._registered_current_model, candidate
    )
    selected_piece = str(contract["geometry"]["selected_piece_id"])
    uncorrected = {
        "robot_board_translation_xyz_m": [0.0, 0.0, 0.0],
        "robot_board_yaw_radians": 0.0,
    }
    registered_scene = _scene_audit(
        model_builder=builder,
        rigid=rigid,
        actions=model_actions,
        selected_piece_id=selected_piece,
    )
    uncorrected_scene = _scene_audit(
        model_builder=builder,
        rigid=uncorrected,
        actions=model_actions,
        selected_piece_id=selected_piece,
    )
    registered_clearance = _clearance_audit(
        model_builder=builder, rigid=rigid, actions=model_actions
    )
    uncorrected_clearance = _clearance_audit(
        model_builder=builder,
        rigid=uncorrected,
        actions=model_actions,
    )
    lower = np.asarray(contract["gateway"]["calibrated_minimum"], dtype=float)
    upper = np.asarray(contract["gateway"]["calibrated_maximum"], dtype=float)
    rates = np.max(
        np.abs(np.diff(physical, axis=0))
        * float(contract["route"]["sample_hz"]),
        axis=0,
    )
    limits = np.asarray(
        contract["gateway"]["maximum_rates_per_second"], dtype=float
    )
    registered_gate = float(
        contract["geometry"]["registered_minimum_clearance_m"]
    )
    baseline = float(
        contract["geometry"]["uncorrected_row_zero_clearance_m"]
    )
    worsening = float(
        contract["geometry"]["maximum_uncorrected_worsening_m"]
    )
    checks = {
        "registered_scene_contact_free": registered_scene["passed"],
        "uncorrected_scene_contact_free": uncorrected_scene["passed"],
        "registered_scene_clearance": registered_clearance[
            "minimum_overall_clearance_m"
        ]
        >= registered_gate,
        "uncorrected_scene_no_more_than_baseline_worsening": (
            uncorrected_clearance["minimum_overall_clearance_m"]
            >= baseline - worsening
        ),
        "inside_calibrated_limits": bool(
            np.all(physical >= lower) and np.all(physical <= upper)
        ),
        "inside_gateway_rates": bool(np.all(rates <= limits)),
        "pan_away_first": bool(
            np.allclose(physical[: boundaries[0] + 1, 1:], physical[0, 1:])
            and physical[boundaries[0], 0] == -60.0
        ),
        "terminal_exact_natural_anchor": np.array_equal(
            physical[-1], waypoints[-1]
        ),
    }
    passed = all(checks.values())
    output_directory.mkdir(parents=True)
    physical_path = output_directory / "physical_route.f64le"
    model_path = output_directory / "model_route.f64le"
    physical_path.write_bytes(physical.tobytes(order="C"))
    model_path.write_bytes(model_actions.tobytes(order="C"))
    receipt = {
        "schema_version": "sim2claw.post_cable_safe_return_static_receipt.v2",
        "status": (
            "post_cable_safe_return_static_pass"
            if passed
            else "post_cable_safe_return_static_reject"
        ),
        "passed": passed,
        "contract_path": _base._display(contract_path),
        "contract_sha256": _base._sha(contract_path),
        "physical_route": {
            "path": _base._display(physical_path),
            "sha256": _base._sha(physical_path),
            "shape": list(physical.shape),
            "dtype": "little_endian_float64",
        },
        "model_route": {
            "path": _base._display(model_path),
            "sha256": _base._sha(model_path),
            "shape": list(model_actions.shape),
            "dtype": "little_endian_float64",
        },
        "stage_boundary_rows": boundaries,
        "maximum_rates_per_second": rates.tolist(),
        "registered_scene": registered_scene,
        "uncorrected_scene": uncorrected_scene,
        "registered_clearance": registered_clearance,
        "uncorrected_clearance": uncorrected_clearance,
        "checks": checks,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "mapping_approved": False,
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


execute_return = _base.execute_return

__all__ = ["compile_return_v2", "execute_return"]
