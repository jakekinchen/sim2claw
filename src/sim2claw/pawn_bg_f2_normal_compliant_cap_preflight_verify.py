"""Independent verifier for OR137's paired zero-action initial-settle gate."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_f2_normal_compliant_cap import (
    CONTRACT_PATH,
    OUTPUT_ROOT,
    PREFLIGHT_SCHEMA,
    load_contract,
)


VERDICT_SCHEMA = "sim2claw.pawn_bg_f2_normal_compliant_cap_preflight_verdict.v1"


class NormalCompliantPreflightVerifierError(RuntimeError):
    """The OR137 preflight trace is malformed or identity-drifted."""


def _load(trace_path: Path, metadata_path: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != PREFLIGHT_SCHEMA:
        raise NormalCompliantPreflightVerifierError("preflight metadata schema drifted")
    if metadata.get("trace_sha256") != sha256_file(trace_path):
        raise NormalCompliantPreflightVerifierError("preflight trace hash drifted")
    with np.load(trace_path, allow_pickle=False) as archive:
        arrays = {name: np.asarray(archive[name]) for name in archive.files}
    required = {
        "time", "qpos", "qvel", "qacc", "ctrl", "robot_qpos", "robot_qvel",
        "cap_qpos", "cap_qvel", "cap_qacc", "pawn_positions",
        "pawn_quaternions_wxyz", "static_positions", "static_quaternions_wxyz",
        "warning_counts", "contact_offsets", "contact_geom", "contact_dist", "contact_pos",
    }
    if set(arrays) != required:
        raise NormalCompliantPreflightVerifierError("preflight array inventory drifted")
    return arrays, metadata


def _quat_angle_degrees(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    dot = np.abs(np.sum(left * right, axis=-1))
    dot = np.clip(dot, -1.0, 1.0)
    return np.degrees(2.0 * np.arccos(dot))


def _contact_pairs(
    arrays: Mapping[str, np.ndarray], metadata: Mapping[str, Any]
) -> set[tuple[str, str]]:
    geom_names = list(metadata["geom_names"])
    cap_names = set(metadata["cap_geom_names"])
    pairs: set[tuple[str, str]] = set()
    for pair in arrays["contact_geom"]:
        names = tuple(sorted((geom_names[int(pair[0])], geom_names[int(pair[1])])))
        if cap_names.intersection(names):
            pairs.add(names)
    return pairs


def _paired_metrics(
    *,
    arrays: Mapping[str, np.ndarray],
    metadata: Mapping[str, Any],
    rigid_trace_path: Path,
    rigid_metadata_path: Path,
) -> dict[str, Any]:
    rigid, rigid_metadata = _load(rigid_trace_path, rigid_metadata_path)
    if metadata["robot_joint_names"] != rigid_metadata["robot_joint_names"]:
        raise NormalCompliantPreflightVerifierError("robot joint name alignment drifted")
    if metadata["pawn_names"] != rigid_metadata["pawn_names"]:
        raise NormalCompliantPreflightVerifierError("pawn name alignment drifted")
    if metadata["static_body_names"] != rigid_metadata["static_body_names"]:
        raise NormalCompliantPreflightVerifierError("static body alignment drifted")
    robot_qpos = float(np.max(np.abs(arrays["robot_qpos"] - rigid["robot_qpos"])))
    robot_qvel = float(np.max(np.abs(arrays["robot_qvel"] - rigid["robot_qvel"])))
    robot_one_step = float(
        np.max(
            np.abs(arrays["robot_qpos"] - rigid["robot_qpos"])
            + float(metadata["timestep_seconds"])
            * np.abs(arrays["robot_qvel"] - rigid["robot_qvel"])
        )
    )
    pawn_translation = float(
        np.max(np.linalg.norm(arrays["pawn_positions"] - rigid["pawn_positions"], axis=-1))
    )
    pawn_orientation = float(
        np.max(
            _quat_angle_degrees(
                arrays["pawn_quaternions_wxyz"], rigid["pawn_quaternions_wxyz"]
            )
        )
    )
    static_position = float(
        np.max(np.abs(arrays["static_positions"] - rigid["static_positions"]), initial=0.0)
    )
    static_orientation = float(
        np.max(
            np.abs(
                arrays["static_quaternions_wxyz"]
                - rigid["static_quaternions_wxyz"]
            ),
            initial=0.0,
        )
    )
    candidate_pairs = _contact_pairs(arrays, metadata)
    rigid_pairs = _contact_pairs(rigid, rigid_metadata)
    return {
        "maximum_robot_joint_position_difference_rad": robot_qpos,
        "maximum_robot_joint_velocity_difference_rad_s": robot_qvel,
        "maximum_robot_one_step_predicted_divergence_rad": robot_one_step,
        "maximum_pawn_center_difference_m": pawn_translation,
        "maximum_pawn_orientation_difference_degrees": pawn_orientation,
        "maximum_static_position_difference_m": static_position,
        "maximum_static_quaternion_component_difference": static_orientation,
        "candidate_cap_contact_pairs": [list(row) for row in sorted(candidate_pairs)],
        "rigid_cap_contact_pairs": [list(row) for row in sorted(rigid_pairs)],
        "new_cap_contact_pairs": [list(row) for row in sorted(candidate_pairs - rigid_pairs)],
    }


def verify_preflight(
    *,
    trace_path: Path,
    metadata_path: Path,
    contract_path: Path = CONTRACT_PATH,
    rigid_trace_path: Path | None = None,
    rigid_metadata_path: Path | None = None,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    arrays, metadata = _load(trace_path, metadata_path)
    if metadata.get("contract_sha256") != sha256_file(contract_path):
        raise NormalCompliantPreflightVerifierError("contract identity drifted")
    candidate_id = str(metadata["candidate_id"])
    dt = float(metadata["timestep_seconds"])
    time = arrays["time"]
    all_numeric = [
        value
        for name, value in arrays.items()
        if name not in {"contact_offsets", "contact_geom", "warning_counts"}
    ]
    finite = all(np.isfinite(value).all() for value in all_numeric)
    time_step_error = float(np.max(np.abs(np.diff(time) - dt), initial=0.0))
    ctrl_constant = bool(
        np.ascontiguousarray(arrays["ctrl"]).tobytes()
        == np.ascontiguousarray(np.broadcast_to(arrays["ctrl"][0], arrays["ctrl"].shape)).tobytes()
    )
    metrics: dict[str, Any] = {
        "row_count": int(len(time)),
        "final_time_seconds": float(time[-1]),
        "maximum_timestep_error_seconds": time_step_error,
        "warning_count_sum": int(np.sum(arrays["warning_counts"])),
        "all_recorded_values_finite": finite,
        "ctrl_bit_identical_during_hold": ctrl_constant,
        "source_action_rows_consumed": int(metadata["source_action_rows_consumed"]),
        "contact_value_count": int(len(arrays["contact_dist"])),
    }
    gates = {
        "canonical_row_count": len(time) == 101,
        "canonical_final_time": math.isclose(float(time[-1]), 0.225, abs_tol=1e-12),
        "monotonic_exact_timestep": bool(np.all(np.diff(time) > 0.0))
        and time_step_error <= 1e-12,
        "zero_warnings": int(np.sum(arrays["warning_counts"])) == 0,
        "finite_state_control_pose_and_contacts": finite,
        "constant_initial_hold_control": ctrl_constant,
        "zero_source_action_rows": int(metadata["source_action_rows_consumed"]) == 0,
        "state_discarded": metadata.get("state_discarded_after_preflight") is True,
    }
    if candidate_id == "normal_compliant_prior_k1000":
        if rigid_trace_path is None or rigid_metadata_path is None:
            raise NormalCompliantPreflightVerifierError("candidate preflight requires rigid reference")
        names = list(metadata["cap_joint_names"])
        if len(names) != 2:
            raise NormalCompliantPreflightVerifierError("candidate must expose two cap joints")
        ranges = np.asarray(metadata["cap_joint_ranges_m"], dtype=float)
        expected_ranges = np.asarray(
            [
                [-0.002, 0.0] if "_fixed_" in name else [0.0, 0.002]
                for name in names
            ],
            dtype=float,
        )
        qpos = arrays["cap_qpos"]
        qvel = arrays["cap_qvel"]
        qacc = arrays["cap_qacc"]
        lower = ranges[:, 0]
        upper = ranges[:, 1]
        far_limit_remaining = np.minimum(qpos - lower, upper - qpos)
        travel_side_remaining = np.asarray(
            [qpos[:, index] - lower[index] if "_fixed_" in name else upper[index] - qpos[:, index] for index, name in enumerate(names)]
        ).T
        neutral_side_overshoot = np.asarray(
            [
                np.maximum(-qpos[:, index], 0.0)
                if "_moving_" in name
                else np.maximum(qpos[:, index], 0.0)
                for index, name in enumerate(names)
            ]
        ).T
        final = slice(-20, None)
        paired = _paired_metrics(
            arrays=arrays,
            metadata=metadata,
            rigid_trace_path=rigid_trace_path,
            rigid_metadata_path=rigid_metadata_path,
        )
        metrics.update(
            {
                "cap_joint_names": names,
                "cap_joint_ranges_m": ranges.tolist(),
                "maximum_absolute_cap_displacement_m": float(np.max(np.abs(qpos))),
                "peak_absolute_cap_acceleration_m_s2": float(np.max(np.abs(qacc))),
                "final_window_maximum_absolute_cap_velocity_m_s": float(np.max(np.abs(qvel[final]))),
                "final_window_maximum_absolute_cap_acceleration_m_s2": float(np.max(np.abs(qacc[final]))),
                "final_window_maximum_cap_position_range_m": float(np.max(np.ptp(qpos[final], axis=0))),
                "minimum_travel_side_remaining_m": float(np.min(travel_side_remaining)),
                "minimum_distance_to_either_joint_limit_m": float(np.min(far_limit_remaining)),
                "maximum_neutral_side_soft_limit_overshoot_m": float(
                    np.max(neutral_side_overshoot)
                ),
                **paired,
            }
        )
        gates.update(
            {
                "exact_signed_joint_ranges": bool(np.array_equal(ranges, expected_ranges)),
                "cap_neutral_side_soft_limit_slack": metrics[
                    "maximum_neutral_side_soft_limit_overshoot_m"
                ]
                <= 19.62e-6,
                "cap_displacement_guard": metrics["maximum_absolute_cap_displacement_m"] <= 25e-6,
                "cap_peak_acceleration_guard": metrics["peak_absolute_cap_acceleration_m_s2"] <= 100.0,
                "cap_final_velocity_guard": metrics["final_window_maximum_absolute_cap_velocity_m_s"] <= 0.001,
                "cap_final_acceleration_guard": metrics["final_window_maximum_absolute_cap_acceleration_m_s2"] <= 1.0,
                "cap_final_position_range_guard": metrics["final_window_maximum_cap_position_range_m"] <= 19.62e-6,
                "cap_far_travel_limit_margin": metrics["minimum_travel_side_remaining_m"] >= 0.0001,
                "robot_position_nonperturbation": paired["maximum_robot_joint_position_difference_rad"] <= 2.0 * math.pi / 4096.0,
                "robot_one_step_nonperturbation": paired[
                    "maximum_robot_one_step_predicted_divergence_rad"
                ]
                <= 2.0 * math.pi / 4096.0,
                "pawn_translation_nonperturbation": paired["maximum_pawn_center_difference_m"] <= 10e-6,
                "pawn_orientation_nonperturbation": paired["maximum_pawn_orientation_difference_degrees"] <= 0.01,
                "static_positions_exact": paired["maximum_static_position_difference_m"] <= 1e-12,
                "static_orientations_exact": paired["maximum_static_quaternion_component_difference"] <= 1e-12,
                "zero_candidate_cap_contact_pairs": not paired[
                    "candidate_cap_contact_pairs"
                ],
            }
        )
    elif candidate_id == "rigid_legacy_shoulder_control":
        gates["no_compliance_joints_in_rigid"] = arrays["cap_qpos"].shape == (101, 0)
    else:
        raise NormalCompliantPreflightVerifierError("unexpected preflight candidate")
    passed = all(gates.values())
    decision = {"candidate_id": candidate_id, "passed": passed, "gates": gates, "metrics": metrics}
    return {
        "schema_version": VERDICT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_id": candidate_id,
        "passed": passed,
        "gate_results": gates,
        "metrics": metrics,
        "decision_digest": canonical_digest(decision),
        "verifier": {
            "path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
            "sha256": sha256_file(Path(__file__).resolve()),
            "producer_booleans_read": False,
        },
        "inputs": {
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": sha256_file(contract_path),
            "trace_path": str(trace_path.relative_to(REPO_ROOT)),
            "trace_sha256": sha256_file(trace_path),
            "metadata_path": str(metadata_path.relative_to(REPO_ROOT)),
            "metadata_sha256": sha256_file(metadata_path),
        },
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--rigid-trace", type=Path)
    parser.add_argument("--rigid-metadata", type=Path)
    args = parser.parse_args(argv)
    verdict = verify_preflight(
        trace_path=args.trace.resolve(),
        metadata_path=args.metadata.resolve(),
        contract_path=args.contract.resolve(),
        rigid_trace_path=None if args.rigid_trace is None else args.rigid_trace.resolve(),
        rigid_metadata_path=None if args.rigid_metadata is None else args.rigid_metadata.resolve(),
    )
    atomic_write_json(args.output.resolve(), verdict)
    print(json.dumps({"candidate_id": verdict["candidate_id"], "passed": verdict["passed"], "decision_digest": verdict["decision_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["NormalCompliantPreflightVerifierError", "verify_preflight"]
