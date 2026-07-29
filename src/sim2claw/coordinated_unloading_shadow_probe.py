"""Compile the bounded V5 coordinated-unloading shadow probe.

This module is deliberately static-only.  It binds one already frozen V5
action, truncates it before any contact in either admitted scene hypothesis,
maps the unchanged prefix into physical units, and proves that two gateway
segments fit the existing per-origin excursion envelope.  It cannot open a
camera, serial device, gateway, or count a physical task attempt.
"""

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
from .paths import REPO_ROOT


class CoordinatedUnloadingShadowProbeError(RuntimeError):
    """The prospective coordinated-unloading probe failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoordinatedUnloadingShadowProbeError(message)


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CoordinatedUnloadingShadowProbeError(
            "shadow-probe input escapes repository"
        ) from error
    _require(path.is_file(), f"shadow-probe input is missing: {path}")
    _require(_sha(path) == binding["sha256"], f"shadow-probe input changed: {path}")
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _scene_audit(
    *,
    model_builder: Any,
    rigid: Mapping[str, Any],
    actions: np.ndarray,
    selected_piece_id: str,
) -> dict[str, Any]:
    model, addresses, robot_bodies, jaw_bodies = model_builder(dict(rigid), 0.0025)
    data = mujoco.MjData(model)
    data.qpos[addresses] = actions[0]
    mujoco.mj_forward(model, data)
    baseline = _static._contact_pairs(model, data, robot_bodies)
    new_pairs: set[tuple[str, str]] = set()
    first_new_contact_row: int | None = None
    for row_index, row in enumerate(actions):
        data.qpos[addresses] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        row_new = _static._contact_pairs(model, data, robot_bodies) - baseline
        if row_new and first_new_contact_row is None:
            first_new_contact_row = row_index
        new_pairs.update(row_new)
    selected_witness = _wrist._first_contact_witness(
        model=model,
        addresses=addresses,
        seed=actions[0],
        action=actions,
        selected_name=selected_piece_id,
        jaw_bodies=jaw_bodies,
    )
    return {
        "baseline_robot_contact_pairs": [list(pair) for pair in sorted(baseline)],
        "new_robot_contact_pairs": [list(pair) for pair in sorted(new_pairs)],
        "first_new_robot_contact_row_or_missing": first_new_contact_row,
        "selected_pawn_contact_observed": selected_witness["observed"],
        "selected_pawn_contact_witness": selected_witness,
        "passed": not new_pairs and not selected_witness["observed"],
    }


def _segment_audit(
    physical: np.ndarray,
    boundaries: list[int],
    *,
    excursion_limit: float,
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for segment_index, (start, stop) in enumerate(
        zip(boundaries[:-1], boundaries[1:], strict=True)
    ):
        _require(0 <= start < stop < len(physical), "invalid segment boundary")
        segment = physical[start : stop + 1]
        delta = segment - segment[0]
        delta[:, 4] = (
            (segment[:, 4] - segment[0, 4] + 180.0) % 360.0
        ) - 180.0
        maximum = np.max(np.abs(delta), axis=0)
        reports.append(
            {
                "segment_index": segment_index,
                "start_row_inclusive": start,
                "stop_row_inclusive": stop,
                "source_row_count": stop - start + 1,
                "maximum_absolute_excursion": maximum.tolist(),
                "all_six_channels_within_frozen_limit": bool(
                    np.all(maximum <= excursion_limit)
                ),
            }
        )
    return reports


def compile_probe(contract_path: Path, output_directory: Path) -> dict[str, Any]:
    """Compile one immutable, contact-impossible V5 physical prefix."""

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _require(
        contract.get("schema_version")
        == "sim2claw.coordinated_unloading_shadow_probe.v1",
        "unexpected coordinated-unloading contract schema",
    )
    _bound(contract["inputs"]["implementation"])
    _bound(contract["inputs"]["v5_temporal_closeout"])
    _bound(contract["inputs"]["locked_elbow_terminal_closeout"])
    selector = _json(contract["inputs"]["v5_static_selector_receipt"])
    manifest = _json(contract["inputs"]["candidate_manifest"])
    registered_rigid = _json(contract["inputs"]["registered_rigid_candidate"])
    action_binding = contract["action"]
    action_path = _bound(action_binding)
    shape = tuple(int(value) for value in action_binding["shape"])
    actions = np.fromfile(action_path, dtype="<f8")
    _require(actions.size == int(np.prod(shape)), "V5 action shape changed")
    actions = np.ascontiguousarray(actions.reshape(shape), dtype="<f8")
    _require(
        selector["selected"][int(action_binding["selector_index"])]["case_id"]
        == action_binding["case_id"],
        "V5 selector index no longer names the frozen case",
    )
    _require(
        selector["selected"][int(action_binding["selector_index"])]["action_sha256"]
        == action_binding["sha256"],
        "V5 selector action identity changed",
    )

    stop_row = int(contract["prefix"]["stop_row_inclusive"])
    first_registered_contact = int(
        contract["prefix"]["registered_first_contact_row"]
    )
    first_uncorrected_contact = int(
        contract["prefix"]["uncorrected_first_contact_row"]
    )
    margin_rows = int(contract["prefix"]["minimum_contact_margin_rows"])
    _require(
        stop_row + margin_rows <= first_registered_contact
        and stop_row + margin_rows <= first_uncorrected_contact,
        "frozen prefix lacks the dual-scene contact margin",
    )
    prefix = np.ascontiguousarray(actions[: stop_row + 1], dtype="<f8")

    model_builder = _static_v2._calibrated_registered_model(
        _static._registered_current_model,
        manifest["candidate_config"],
    )
    registered = _scene_audit(
        model_builder=model_builder,
        rigid=registered_rigid,
        actions=prefix,
        selected_piece_id=str(action_binding["selected_piece_id"]),
    )
    uncorrected = _scene_audit(
        model_builder=model_builder,
        rigid={
            "robot_board_translation_xyz_m": [0.0, 0.0, 0.0],
            "robot_board_yaw_radians": 0.0,
        },
        actions=prefix,
        selected_piece_id=str(action_binding["selected_piece_id"]),
    )
    registered_full = _scene_audit(
        model_builder=model_builder,
        rigid=registered_rigid,
        actions=actions,
        selected_piece_id=str(action_binding["selected_piece_id"]),
    )
    uncorrected_full = _scene_audit(
        model_builder=model_builder,
        rigid={
            "robot_board_translation_xyz_m": [0.0, 0.0, 0.0],
            "robot_board_yaw_radians": 0.0,
        },
        actions=actions,
        selected_piece_id=str(action_binding["selected_piece_id"]),
    )
    _require(
        registered_full["first_new_robot_contact_row_or_missing"]
        == first_registered_contact,
        "registered-scene first contact row changed",
    )
    _require(
        uncorrected_full["first_new_robot_contact_row_or_missing"]
        == first_uncorrected_contact,
        "uncorrected-scene first contact row changed",
    )

    physical = _static._physical_actions(prefix, manifest["candidate_config"])
    physical = np.ascontiguousarray(physical, dtype="<f8")
    minimum = np.asarray(
        contract["gateway"]["follower_calibrated_minimum"], dtype=np.float64
    )
    maximum = np.asarray(
        contract["gateway"]["follower_calibrated_maximum"], dtype=np.float64
    )
    rates = np.asarray(
        contract["gateway"]["maximum_rates_per_second"], dtype=np.float64
    )
    sample_hz = float(contract["action"]["sample_hz"])
    maximum_rate = np.max(np.abs(np.diff(physical, axis=0)) * sample_hz, axis=0)
    segment_reports = _segment_audit(
        physical,
        [int(value) for value in contract["gateway"]["segment_boundaries"]],
        excursion_limit=float(contract["gateway"]["segment_excursion_limit"]),
    )
    row_zero = np.asarray(contract["gateway"]["expected_row_zero"], dtype=np.float64)
    checks = {
        "registered_scene_contact_impossible": registered["passed"],
        "uncorrected_scene_contact_impossible": uncorrected["passed"],
        "row_zero_exact": bool(np.array_equal(physical[0], row_zero)),
        "all_rows_inside_calibrated_limits": bool(
            np.all(physical >= minimum) and np.all(physical <= maximum)
        ),
        "all_rates_within_gateway_limits": bool(np.all(maximum_rate <= rates)),
        "all_segments_within_excursion_limit": all(
            row["all_six_channels_within_frozen_limit"]
            for row in segment_reports
        ),
        "reverse_return_reuses_identical_rows": bool(
            np.array_equal(physical[::-1][::-1], physical)
        ),
    }
    passed = all(checks.values())
    _require(not output_directory.exists(), "refusing to overwrite shadow-probe output")
    output_directory.mkdir(parents=True)
    physical_path = output_directory / "physical_prefix.f64le"
    physical_path.write_bytes(physical.tobytes(order="C"))
    receipt = {
        "schema_version": "sim2claw.coordinated_unloading_shadow_probe_receipt.v1",
        "status": (
            "coordinated_unloading_shadow_probe_static_pass"
            if passed
            else "coordinated_unloading_shadow_probe_static_reject"
        ),
        "proof_class": (
            "prospective_dual_scene_contact_impossible_segmented_physical_prefix"
        ),
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": _sha(contract_path),
        },
        "case_id": action_binding["case_id"],
        "source_action_sha256": action_binding["sha256"],
        "source_action_shape": list(shape),
        "prefix_stop_row_inclusive": stop_row,
        "prefix_shape": list(prefix.shape),
        "prefix_model_sha256": hashlib.sha256(prefix.tobytes(order="C")).hexdigest(),
        "physical_prefix": {
            "path": _display_path(physical_path),
            "sha256": _sha(physical_path),
            "shape": list(physical.shape),
            "dtype": "little_endian_float64",
        },
        "row_zero_physical": physical[0].tolist(),
        "terminal_physical": physical[-1].tolist(),
        "maximum_physical_rate_per_second": maximum_rate.tolist(),
        "segments": segment_reports,
        "registered_scene": registered,
        "uncorrected_scene": uncorrected,
        "future_contact_rows": {
            "registered_scene": first_registered_contact,
            "uncorrected_scene": first_uncorrected_contact,
        },
        "checks": checks,
        "passed": passed,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "mapping_approval": False,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt
