"""Exact-action contact witness extraction for the canonical CC02 negative."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_seeded_action_static_v2 as _static_v2
from .canonical_seeded_action_temporal import (
    _body_name,
    _load_action,
    _zoh_delay,
)
from .paths import REPO_ROOT


class CanonicalContactWitnessError(RuntimeError):
    """A contact-witness input or immutable output invariant changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CanonicalContactWitnessError(
            "contact-witness input escapes repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise CanonicalContactWitnessError(
            f"bound contact-witness input changed: {path}"
        )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def _geom_name(model: mujoco.MjModel, geom_id: int) -> str:
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
        or f"geom-{geom_id}"
    )


def _new_pair_row(
    *,
    jaw_geom: str,
    pawn_geom: str,
    jaw_body: str,
    pawn_body: str,
) -> dict[str, Any]:
    return {
        "jaw_geom": jaw_geom,
        "pawn_geom": pawn_geom,
        "jaw_body": jaw_body,
        "pawn_body": pawn_body,
        "contact_count": 0,
        "contact_height_relative_initial_pawn_root_m": {
            "minimum": None,
            "maximum": None,
        },
        "absolute_vertical_normal_component": {
            "minimum": None,
            "maximum": None,
            "sum": 0.0,
        },
        "maximum_normal_force": 0.0,
    }


def _accumulate_pair(
    row: dict[str, Any],
    *,
    height: float,
    vertical_normal: float,
    normal_force: float,
) -> None:
    row["contact_count"] += 1
    height_range = row["contact_height_relative_initial_pawn_root_m"]
    normal_range = row["absolute_vertical_normal_component"]
    for summary, value in (
        (height_range, height),
        (normal_range, vertical_normal),
    ):
        summary["minimum"] = (
            value
            if summary["minimum"] is None
            else min(summary["minimum"], value)
        )
        summary["maximum"] = (
            value
            if summary["maximum"] is None
            else max(summary["maximum"], value)
        )
    normal_range["sum"] += vertical_normal
    row["maximum_normal_force"] = max(
        row["maximum_normal_force"], normal_force
    )


def _replay_witness(
    *,
    model: mujoco.MjModel,
    addresses: list[int],
    actuators: list[int],
    jaw_bodies: set[int],
    action: np.ndarray,
    selected_name: str,
    substeps: int,
    rise_threshold_m: float,
    motion_threshold_m: float,
) -> dict[str, Any]:
    data = mujoco.MjData(model)
    selected_id = _static._named_id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    data.qpos[addresses] = action[0]
    data.ctrl[actuators] = action[0]
    mujoco.mj_forward(model, data)
    initial = data.xpos[selected_id].copy()
    first_jaw_contact_row = None
    first_planar_motion_row = None
    first_rise_row = None
    peak_rise_m = 0.0
    peak_rise_row = 0
    support_contact_steps = 0
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    first_witness: dict[str, Any] | None = None

    for row_index, row in enumerate(action):
        data.ctrl[actuators] = row
        for substep_index in range(substeps):
            mujoco.mj_step(model, data)
            planar_motion = float(
                np.linalg.norm((data.xpos[selected_id] - initial)[:2])
            )
            rise = float(data.xpos[selected_id][2] - initial[2])
            if (
                first_planar_motion_row is None
                and planar_motion >= motion_threshold_m
            ):
                first_planar_motion_row = row_index
            if first_rise_row is None and rise >= rise_threshold_m:
                first_rise_row = row_index
            if rise > peak_rise_m:
                peak_rise_m = rise
                peak_rise_row = row_index

            for contact_index in range(data.ncon):
                contact = data.contact[contact_index]
                geom1 = int(contact.geom1)
                geom2 = int(contact.geom2)
                body1 = int(model.geom_bodyid[geom1])
                body2 = int(model.geom_bodyid[geom2])
                bodies = {body1, body2}
                if selected_id in bodies and (
                    _geom_name(model, geom1) == "board_collision"
                    or _geom_name(model, geom2) == "board_collision"
                ):
                    support_contact_steps += 1
                if selected_id not in bodies or not (bodies & jaw_bodies):
                    continue
                jaw_body = body1 if body1 in jaw_bodies else body2
                jaw_geom = geom1 if body1 in jaw_bodies else geom2
                pawn_geom = geom2 if jaw_geom == geom1 else geom1
                pair_key = (
                    _geom_name(model, jaw_geom),
                    _geom_name(model, pawn_geom),
                )
                pair = pairs.setdefault(
                    pair_key,
                    _new_pair_row(
                        jaw_geom=pair_key[0],
                        pawn_geom=pair_key[1],
                        jaw_body=_body_name(model, jaw_body),
                        pawn_body=selected_name,
                    ),
                )
                normal = np.asarray(contact.frame[:3], dtype=np.float64)
                if jaw_geom == geom2:
                    normal = -normal
                address = int(contact.efc_address)
                normal_force = (
                    float(abs(data.efc_force[address]))
                    if 0 <= address < data.nefc
                    else 0.0
                )
                height = float(contact.pos[2] - initial[2])
                vertical_normal = float(abs(normal[2]))
                _accumulate_pair(
                    pair,
                    height=height,
                    vertical_normal=vertical_normal,
                    normal_force=normal_force,
                )
                if first_jaw_contact_row is None:
                    first_jaw_contact_row = row_index
                    first_witness = {
                        "row_index": row_index,
                        "substep_index": substep_index,
                        "jaw_geom": pair_key[0],
                        "pawn_geom": pair_key[1],
                        "contact_position_xyz_m": np.asarray(
                            contact.pos, dtype=np.float64
                        ).tolist(),
                        "contact_height_relative_initial_pawn_root_m": height,
                        "jaw_to_pawn_normal_xyz": normal.tolist(),
                        "normal_force": normal_force,
                    }

    normalized_pairs = []
    for pair in pairs.values():
        pair["absolute_vertical_normal_component"]["mean"] = (
            pair["absolute_vertical_normal_component"].pop("sum")
            / pair["contact_count"]
        )
        normalized_pairs.append(pair)
    normalized_pairs.sort(
        key=lambda item: (-item["contact_count"], item["jaw_geom"])
    )
    return {
        "selected_piece_id": selected_name,
        "action_rows": len(action),
        "first_jaw_contact_row": first_jaw_contact_row,
        "first_planar_motion_row": first_planar_motion_row,
        "first_rise_above_threshold_row": first_rise_row,
        "rise_after_first_jaw_contact_rows": (
            None
            if first_jaw_contact_row is None or first_rise_row is None
            else first_rise_row - first_jaw_contact_row
        ),
        "peak_vertical_rise_mm": peak_rise_m * 1000.0,
        "peak_vertical_rise_row": peak_rise_row,
        "support_contact_steps": support_contact_steps,
        "first_jaw_contact_witness": first_witness,
        "jaw_pawn_contact_pairs": normalized_pairs,
    }


def diagnose(
    contract_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Run the frozen exact-action nominal contact witness once."""

    if output_path.exists():
        raise CanonicalContactWitnessError(
            "immutable contact-witness output already exists"
        )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != (
        "sim2claw.canonical_contact_witness.v1"
    ):
        raise CanonicalContactWitnessError(
            "unexpected contact-witness contract"
        )
    for binding in contract["inputs"].values():
        _bound(binding)
    temporal_receipt = _json(contract["inputs"]["temporal_receipt"])
    static_receipt = _json(contract["inputs"]["static_receipt"])
    manifest = _json(contract["inputs"]["candidate_manifest"])
    rigid = _json(contract["inputs"]["registration_candidate"])
    if (
        temporal_receipt["status"]
        != "canonical_seeded_action_temporal_reject"
        or temporal_receipt["direction_counts"]
        != {"REAL_TO_SIM": 0, "SIM_TO_REAL": 0}
        or len(contract["cases"]) != 4
        or contract["plant_paths"]
        != ["canonical_direct_target", "diagnostic_zoh_0p11s"]
    ):
        raise CanonicalContactWitnessError(
            "contact-witness admission changed"
        )
    static_by_id = {
        row["case_id"]: row for row in static_receipt["selected"]
    }
    if set(static_by_id) != {row["case_id"] for row in contract["cases"]}:
        raise CanonicalContactWitnessError(
            "contact-witness cases changed"
        )

    model_builder = _static_v2._calibrated_registered_model(
        _static._registered_current_model,
        manifest["candidate_config"],
    )
    model, addresses, _, jaw_bodies = model_builder(
        rigid, float(contract["simulation"]["timestep_s"])
    )
    actuators = [
        _static._named_id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        for name in _static.ALL_JOINTS
    ]
    sample_hz = float(contract["action_identity"]["sample_hz"])
    results = []
    for case in contract["cases"]:
        static = static_by_id[case["case_id"]]
        action = _load_action(case)
        if (
            static["action_sha256"] != case["action_sha256"]
            or hashlib.sha256(action.tobytes(order="C")).hexdigest()
            != case["action_sha256"]
        ):
            raise CanonicalContactWitnessError(
                "contact-witness action changed"
            )
        for path_id in contract["plant_paths"]:
            applied = (
                action
                if path_id == "canonical_direct_target"
                else _zoh_delay(
                    action,
                    sample_hz=sample_hz,
                    delay_seconds=0.11,
                )[0]
            )
            witness = _replay_witness(
                model=model,
                addresses=addresses,
                actuators=actuators,
                jaw_bodies=jaw_bodies,
                action=applied,
                selected_name=case["selected_piece_id"],
                substeps=int(
                    contract["simulation"]["substeps_per_row"]
                ),
                rise_threshold_m=float(
                    contract["thresholds"]["rise_threshold_m"]
                ),
                motion_threshold_m=float(
                    contract["thresholds"]["planar_motion_threshold_m"]
                ),
            )
            results.append(
                {
                    "case_id": case["case_id"],
                    "direction": case["direction"],
                    "path_id": path_id,
                    "requested_action_sha256": case["action_sha256"],
                    "applied_action_sha256": hashlib.sha256(
                        np.asarray(applied, dtype="<f8").tobytes(order="C")
                    ).hexdigest(),
                    **witness,
                }
            )
    all_rise_follows_contact = all(
        row["rise_after_first_jaw_contact_rows"] is not None
        and row["rise_after_first_jaw_contact_rows"] >= 0
        for row in results
    )
    receipt = {
        "schema_version": "sim2claw.canonical_contact_witness_receipt.v1",
        "status": "canonical_contact_witness_completed",
        "proof_class": (
            "cpu_fp64_exact_action_nominal_contact_witness_diagnostic"
        ),
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "source_temporal_receipt_sha256": contract["inputs"][
            "temporal_receipt"
        ]["sha256"],
        "results": results,
        "all_rise_events_follow_jaw_contact": all_rise_follows_contact,
        "dynamics_or_action_changed": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CanonicalContactWitnessError",
    "diagnose",
]
