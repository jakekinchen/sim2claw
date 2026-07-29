"""Freeze the two unopened V4 wrist/path family actions without dynamics."""

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


class CanonicalWristPathActionCompletionError(RuntimeError):
    """A frozen completion input or action changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalWristPathActionCompletionError(
            "completion input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CanonicalWristPathActionCompletionError(
            f"completion input changed: {path}"
        )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def freeze_actions(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    if output_directory.exists():
        raise CanonicalWristPathActionCompletionError(
            "immutable action completion output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "static_contract",
        "static_receipt",
        "temporal_closeout",
        "implementation",
        "cases",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    if (
        set(contract) != expected
        or contract["schema_version"]
        != "sim2claw.canonical_wrist_path_action_completion.v1"
        or len(contract["cases"]) != 2
        or contract["authority"] != {
            "model_loading": True,
            "static_simulation": True,
            "dynamic_simulation": False,
            "mapping_approval": False,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "simulator_promotion": False,
            "transfer_claim": False,
        }
    ):
        raise CanonicalWristPathActionCompletionError(
            "action completion contract widened"
        )
    static_successor = _json(contract["static_contract"])
    static_receipt = _json(contract["static_receipt"])
    _bound(contract["temporal_closeout"])
    _bound(contract["implementation"])
    if (
        static_successor["schema_version"]
        != "sim2claw.canonical_wrist_path_static_successor.v4"
        or static_receipt["status"] != "canonical_wrist_path_static_pass"
        or static_receipt["statically_eligible_family_count"] != 6
    ):
        raise CanonicalWristPathActionCompletionError(
            "V4 static admission changed"
        )
    base = _json(static_successor["base_contract"])
    manifest = _json(base["inputs"]["candidate_manifest"])
    rigid = _json(base["inputs"]["registration_candidate"])
    model, addresses, _, _ = _static_v2._calibrated_registered_model(
        _static._registered_current_model,
        manifest["candidate_config"],
    )(rigid, float(base["simulation"]["timestep_s"]))
    live_seed = np.asarray(
        base["live_seed"]["model_radians"], dtype=np.float64
    )
    initial = mujoco.MjData(model)
    initial.qpos[addresses] = live_seed
    mujoco.mj_forward(model, initial)
    families = {
        row["case_id"]: row for row in _static._families(model)
    }
    eligible_rows = {
        (
            row["case_id"],
            row["wrist_orientation_index"],
            row["contact_height_index"],
        ): row
        for row in static_receipt["grid_results"]
        if row["static_eligible"]
    }
    target_rates = np.asarray(
        base["action"]["target_rates_per_joint"], dtype=np.float64
    )
    output_directory.mkdir(parents=True)
    action_directory = output_directory / "actions"
    action_directory.mkdir()
    frozen = []
    for index, case in enumerate(contract["cases"]):
        family = families.get(case["case_id"])
        evidence = eligible_rows.get(
            (
                case["case_id"],
                case["wrist_orientation_index"],
                case["contact_height_index"],
            )
        )
        if family is None or evidence is None:
            raise CanonicalWristPathActionCompletionError(
                "completion case is not a frozen eligible V4 cell"
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
        action, metrics = _wrist._compile(
            model=model,
            addresses=addresses,
            live_seed=live_seed,
            candidate_config=manifest["candidate_config"],
            source_xyz=source_xyz,
            direction=direction,
            wrist_roll_rad=float(case["wrist_roll_target_rad"]),
            contact_offset_m=float(base["grid"]["contact_offset_m"]),
            contact_height_m=float(case["contact_height_m"]),
            clearance_height_m=float(base["grid"]["clearance_height_m"]),
            stroke_m=float(base["grid"]["stroke_m"]),
            closed_jaw_rad=float(base["action"]["closed_jaw_rad"]),
            sample_hz=float(base["action"]["sample_hz"]),
            target_rates=target_rates,
            maximum_ik_residual_m=float(
                base["gates"]["maximum_ik_residual_m"]
            ),
            precontact_backoff_m=float(
                static_successor["path_shape_override"][
                    "precontact_backoff_m"
                ]
            ),
        )
        raw = action.tobytes(order="C")
        if (
            hashlib.sha256(raw).hexdigest() != case["action_sha256"]
            or list(action.shape) != case["action_shape"]
            or metrics["action_raw_float64le_sha256"]
            != evidence["compile"]["action_raw_float64le_sha256"]
        ):
            raise CanonicalWristPathActionCompletionError(
                "completed action differs from frozen V4 cell"
            )
        path = action_directory / f"{index:02d}.f64le"
        path.write_bytes(raw)
        frozen.append(
            {
                **case,
                "action_path": str(path.relative_to(REPO_ROOT)),
            }
        )
    receipt = {
        "schema_version": (
            "sim2claw.canonical_wrist_path_action_completion_receipt.v1"
        ),
        "status": "two_unopened_v4_family_actions_frozen",
        "proof_class": (
            "cpu_fp64_static_action_completion_without_dynamic_outcomes"
        ),
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "frozen_actions": frozen,
        "dynamic_simulation": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CanonicalWristPathActionCompletionError",
    "freeze_actions",
]
