"""Fail-closed readiness audit for a canonical bidirectional transfer packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .current_workcell import CURRENT_WORKCELL_ID
from .paths import REPO_ROOT


class CanonicalTransferReadinessError(RuntimeError):
    """A frozen readiness input or invariant changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(entry: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(entry["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalTransferReadinessError(
            "readiness input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise CanonicalTransferReadinessError(
            f"bound readiness input changed: {path}"
        )
    return path


def _json(entry: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(entry).read_text(encoding="utf-8"))


def _model_to_physical(
    model_actions: np.ndarray,
    candidate_config: Mapping[str, Any],
) -> np.ndarray:
    joints = candidate_config["physical_adapter"]["joint_transform"]["joints"]
    if len(joints) != model_actions.shape[1]:
        raise CanonicalTransferReadinessError(
            "physical transform width does not match action width"
        )
    result = np.empty_like(model_actions, dtype=np.float64)
    for index, joint in enumerate(joints):
        scale = float(joint["scale"])
        sign = float(joint["sign"])
        offset = float(joint["zero_offset"])
        if scale <= 0.0 or sign not in (-1.0, 1.0):
            raise CanonicalTransferReadinessError(
                "physical transform contains an invalid scalar"
            )
        result[:, index] = (
            model_actions[:, index] - offset
        ) / (scale * sign)
    return result


def _maximum_row_delta(
    rows: np.ndarray,
    anchor: np.ndarray,
) -> tuple[float, int]:
    row_maxima = np.max(np.abs(rows - anchor), axis=1)
    index = int(np.argmin(row_maxima))
    return float(row_maxima[index]), index


def evaluate(contract_path: Path, output_path: Path) -> dict[str, Any]:
    """Evaluate frozen legacy candidates against the current live anchor."""

    if output_path.exists():
        raise CanonicalTransferReadinessError(
            "immutable output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.canonical_transfer_readiness.v1"
    ):
        raise CanonicalTransferReadinessError(
            "unexpected canonical readiness contract"
        )

    hard_cutover = _json(contract["inputs"]["hard_cutover"])
    registration = _json(contract["inputs"]["registration_receipt"])
    registration_closeout = _json(
        contract["inputs"]["registration_closeout"]
    )
    manifest = _json(contract["inputs"]["candidate_manifest"])
    d1_derivation = _json(contract["inputs"]["d1_derivation"])
    action_path = _bound(contract["inputs"]["sim_to_real_action"])
    c922_path = _bound(contract["inputs"]["live_c922_frame"])
    d405_path = _bound(contract["inputs"]["live_d405_frame"])

    shape = tuple(contract["inputs"]["sim_to_real_action"]["shape"])
    action = np.fromfile(action_path, dtype="<f8")
    if action.size != int(np.prod(shape)):
        raise CanonicalTransferReadinessError(
            "SIM_TO_REAL action shape changed"
        )
    action = action.reshape(shape)
    physical_action = _model_to_physical(
        action, manifest["candidate_config"]
    )

    live = np.asarray(
        contract["live_snapshot"]["follower_position_degrees"],
        dtype=np.float64,
    )
    physical_minimum = np.asarray(
        contract["live_snapshot"]["follower_calibrated_minimum"],
        dtype=np.float64,
    )
    physical_maximum = np.asarray(
        contract["live_snapshot"]["follower_calibrated_maximum"],
        dtype=np.float64,
    )
    start_delta = physical_action[0] - live
    closest_delta, closest_index = _maximum_row_delta(physical_action, live)
    rates = np.max(
        np.abs(np.diff(physical_action, axis=0))
        * float(contract["gates"]["sample_hz"]),
        axis=0,
    )
    rate_limits = np.asarray(
        contract["gates"]["gateway_rate_limits_per_joint"],
        dtype=np.float64,
    )
    action_in_bounds = bool(
        np.all(physical_action >= physical_minimum)
        and np.all(physical_action <= physical_maximum)
    )

    source_samples_path = _bound(
        contract["inputs"]["real_to_sim_source_samples"]
    )
    source_rows = [
        json.loads(line)
        for line in source_samples_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    source_index = int(d1_derivation["source"]["source_start_index"])
    source_start = np.asarray(
        source_rows[source_index]["follower_actual_position_degrees"],
        dtype=np.float64,
    )
    source_start_delta = source_start - live

    transform = manifest["candidate_config"]["physical_adapter"][
        "joint_transform"
    ]
    maximum_start_delta = float(
        contract["gates"]["maximum_unplanned_start_delta_degrees"]
    )
    maximum_gripper_delta = float(
        contract["gates"]["maximum_unplanned_gripper_delta_percent"]
    )
    sim_start_pass = bool(
        np.max(np.abs(start_delta[:5])) <= maximum_start_delta
        and abs(float(start_delta[5])) <= maximum_gripper_delta
    )
    real_start_pass = bool(
        np.max(np.abs(source_start_delta[:5])) <= maximum_start_delta
        and abs(float(source_start_delta[5])) <= maximum_gripper_delta
    )
    mapping_approved = bool(transform.get("calibration_approved"))

    checks = {
        "canonical_runtime_active": (
            CURRENT_WORKCELL_ID
            == contract["canonical_runtime"]["current_workcell_id"]
        ),
        "hard_cutover_complete": (
            hard_cutover.get("status") == "verified_complete"
        ),
        "canonical_registration_passed": (
            registration.get("passed") is True
            and registration.get("status")
            == "canonical_task_plane_registration_pass"
            and registration_closeout.get("status")
            == "accepted_registration_prerequisite_satisfied"
            and registration_closeout["result"][
                "registration_prerequisite_satisfied"
            ]
            is True
        ),
        "live_preflight_passed": (
            contract["live_snapshot"]["preflight_passed"] is True
        ),
        "live_torque_disabled": (
            contract["live_snapshot"]["physical_follower_torque_enabled"]
            is False
        ),
        "live_cameras_available": (
            c922_path.is_file() and d405_path.is_file()
        ),
        "sim_to_real_action_float64le_40hz": (
            action.dtype == np.dtype("<f8")
            and contract["gates"]["sample_hz"] == 40.0
        ),
        "sim_to_real_action_within_calibrated_bounds": action_in_bounds,
        "sim_to_real_action_within_gateway_rate_limits": bool(
            np.all(rates <= rate_limits)
        ),
        "physical_model_mapping_approved": mapping_approved,
        "sim_to_real_start_matches_live_anchor": sim_start_pass,
        "real_to_sim_source_start_matches_live_anchor": real_start_pass,
    }
    passed = all(checks.values())
    blockers = [name for name, value in checks.items() if not value]
    result = {
        "schema_version": "sim2claw.canonical_transfer_readiness_receipt.v1",
        "contract_id": contract["contract_id"],
        "proof_class": (
            "read_only_live_anchor_and_frozen_candidate_readiness_audit"
        ),
        "status": (
            "canonical_transfer_readiness_pass"
            if passed
            else "canonical_transfer_readiness_reject"
        ),
        "passed": passed,
        "checks": checks,
        "blockers": blockers,
        "live_snapshot": contract["live_snapshot"],
        "sim_to_real_candidate": {
            "action_raw_float64le_sha256": _sha(action_path),
            "shape": list(action.shape),
            "first_physical_command": physical_action[0].tolist(),
            "last_physical_command": physical_action[-1].tolist(),
            "first_minus_live": start_delta.tolist(),
            "maximum_first_arm_delta_degrees": float(
                np.max(np.abs(start_delta[:5]))
            ),
            "closest_row_to_live_index": closest_index,
            "closest_row_maximum_delta": closest_delta,
            "maximum_rates_per_joint": rates.tolist(),
            "physical_minimum_per_joint": np.min(
                physical_action, axis=0
            ).tolist(),
            "physical_maximum_per_joint": np.max(
                physical_action, axis=0
            ).tolist(),
        },
        "real_to_sim_candidate": {
            "source_samples_sha256": _sha(source_samples_path),
            "source_start_index": source_index,
            "source_start_physical": source_start.tolist(),
            "source_start_minus_live": source_start_delta.tolist(),
            "maximum_source_start_arm_delta_degrees": float(
                np.max(np.abs(source_start_delta[:5]))
            ),
        },
        "mapping": {
            "transform_id": transform["transform_id"],
            "review_status": transform["review_status"],
            "calibration_approved": mapping_approved,
        },
        "decision": {
            "legacy_sim_to_real_candidate_executable": (
                mapping_approved and sim_start_pass
            ),
            "legacy_real_to_sim_candidate_executable": real_start_pass,
            "physical_packet_authorized": passed,
            "next_action": (
                "freeze_physical_packet"
                if passed
                else "compile_fresh_actions_from_live_anchor_in_canonical_runtime"
            ),
        },
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


__all__ = [
    "CanonicalTransferReadinessError",
    "evaluate",
]
