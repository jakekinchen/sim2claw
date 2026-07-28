"""Frozen V05-TJ direct-target and 0.11 second ZOH consequence replay."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from . import bidirectional_pawn_push_v2_sim_rehearsal as _rehearsal
from . import bidirectional_pawn_push_v2_temporal_static as _static
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .scene import board_square_center


class TemporalReplayError(RuntimeError):
    """The frozen temporal replay failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    resolved = path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise TemporalReplayError(
            "V05-TJ temporal path escapes repository"
        ) from error
    return resolved


def _bound(entry: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = _resolve(Path(str(entry["path"])))
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise TemporalReplayError(f"bound V05-TJ input changed: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def _write_tensor(
    directory: Path,
    name: str,
    values: np.ndarray,
) -> dict[str, Any]:
    path = directory / f"{name}.f64le"
    array = np.asarray(values, dtype="<f8", order="C")
    path.write_bytes(array.tobytes(order="C"))
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": _sha(path),
        "shape": list(array.shape),
        "dtype": "little_endian_float64",
    }


def _zoh_delay(
    requested: np.ndarray,
    *,
    sample_hz: float,
    delay_seconds: float,
) -> tuple[np.ndarray, np.ndarray]:
    timestamps = np.arange(len(requested), dtype="<f8") / sample_hz
    source_times = np.maximum(0.0, timestamps - delay_seconds)
    indices = np.floor(source_times * sample_hz + 1e-12).astype(np.int64)
    indices = np.clip(indices, 0, len(requested) - 1)
    return np.asarray(requested[indices], dtype="<f8", order="C"), indices


def _load_action(case: Mapping[str, Any]) -> np.ndarray:
    path = _resolve(Path(str(case["action_path"])))
    if not path.is_file() or _sha(path) != case["action_sha256"]:
        raise TemporalReplayError(f"frozen successor action changed: {path}")
    shape = tuple(int(value) for value in case["action_shape"])
    action = np.fromfile(path, dtype="<f8").reshape(shape)
    if action.shape[1] != 6 or not np.all(np.isfinite(action)):
        raise TemporalReplayError("frozen successor action is invalid")
    return np.asarray(action, dtype="<f8", order="C")


def replay(contract_path: Path, output_directory: Path) -> dict[str, Any]:
    contract_path = _resolve(contract_path)
    output_directory = _resolve(output_directory)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_temporal_replay.v1"
    ):
        raise TemporalReplayError("unexpected V05-TJ temporal contract")
    _, static_receipt = _bound(contract["static_receipt"])
    _, rehearsal_contract = _bound(contract["rehearsal_contract"])
    _, wrapper = _bound(rehearsal_contract["candidate_manifest"])
    _, rigid = _bound(rehearsal_contract["registration_candidate"])

    model, qpos, actuators, jaw_bodies = _rehearsal._registered_model(
        wrapper,
        rigid,
        float(rehearsal_contract["simulation"]["timestep_s"]),
    )
    seed_physical = np.asarray(
        [rehearsal_contract["action_synthesis"]["seed_physical"]]
    )
    seed_model = _physical_to_model_position(
        seed_physical, wrapper["candidate_config"]
    )[0]
    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_size = tuple(rehearsal_contract["camera_gate"]["image_size_px"])
    sample_hz = float(contract["action_identity"]["sample_hz"])
    variants = rehearsal_contract["robustness_variants"]
    output_directory.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for case in contract["cases"]:
        matching = [
            row
            for row in static_receipt["eligible_cases"]
            if row["case_id"] == case["case_id"]
        ]
        if len(matching) != 1:
            raise TemporalReplayError(
                f"frozen case is not uniquely static-admitted: {case['case_id']}"
            )
        if matching[0]["action_sha256"] != case["action_sha256"]:
            raise TemporalReplayError("case action hash differs from static freeze")
        requested = _load_action(case)
        sent = requested.copy(order="C")
        if requested.tobytes(order="C") != sent.tobytes(order="C"):
            raise TemporalReplayError("requested and sent action bytes differ")
        timestamps = np.arange(len(requested), dtype="<f8") / sample_hz
        source = np.asarray(board_square_center(case["source_square"]))
        destination = np.asarray(
            board_square_center(case["destination_square"])
        )
        direction = destination - source
        direction /= np.linalg.norm(direction)

        path_results: list[dict[str, Any]] = []
        for path_spec in contract["plant_paths"]:
            if path_spec["kind"] == "direct_target_mujoco":
                applied = requested.copy(order="C")
                source_indices = np.arange(len(requested), dtype=np.int64)
            elif path_spec["kind"] == "zero_order_hold_command_delay":
                applied, source_indices = _zoh_delay(
                    requested,
                    sample_hz=sample_hz,
                    delay_seconds=float(path_spec["delay_seconds"]),
                )
            else:
                raise TemporalReplayError("unknown frozen plant path")
            trace_directory = (
                output_directory
                / "traces"
                / case["case_id"]
                / path_spec["path_id"]
            )
            trace_directory.mkdir(parents=True, exist_ok=True)
            traces = {
                "requested": _write_tensor(
                    trace_directory, "requested", requested
                ),
                "sent": _write_tensor(trace_directory, "sent", sent),
                "applied": _write_tensor(
                    trace_directory, "applied", applied
                ),
                "requested_timestamps": _write_tensor(
                    trace_directory,
                    "requested_timestamps",
                    timestamps,
                ),
                "sent_timestamps": _write_tensor(
                    trace_directory, "sent_timestamps", timestamps
                ),
                "applied_timestamps": _write_tensor(
                    trace_directory, "applied_timestamps", timestamps
                ),
            }
            index_path = trace_directory / "applied_source_indices.i64le"
            np.asarray(source_indices, dtype="<i8").tofile(index_path)
            traces["applied_source_indices"] = {
                "path": str(index_path.relative_to(REPO_ROOT)),
                "sha256": _sha(index_path),
                "shape": list(source_indices.shape),
                "dtype": "little_endian_int64",
            }
            gateway = _static._gateway_audit(
                applied,
                wrapper,
                sample_hz=sample_hz,
            )
            replays: list[dict[str, Any]] = []
            for variant in variants:
                longitudinal, lateral = variant["delta_m"]
                delta = (
                    direction[:2] * longitudinal
                    + np.asarray([-direction[1], direction[0]]) * lateral
                )
                consequence = _rehearsal._replay(
                    model=model,
                    qpos_addresses=qpos,
                    actuator_ids=actuators,
                    jaw_bodies=jaw_bodies,
                    action=applied,
                    selected_name=case["selected_piece_id"],
                    source_delta_m=delta,
                    direction=direction,
                    substeps=int(
                        rehearsal_contract["simulation"][
                            "substeps_per_row"
                        ]
                    ),
                    camera=camera,
                    image_size=image_size,
                )
                checks = {
                    "fully_off_source": consequence["signed_progress_mm"]
                    >= rehearsal_contract["gates"][
                        "minimum_signed_progress_mm"
                    ],
                    "selected_contact": consequence[
                        "selected_contact_steps"
                    ]
                    > 0,
                    "excluded_contact": consequence[
                        "excluded_contact_steps"
                    ]
                    == rehearsal_contract["gates"][
                        "excluded_contact_count"
                    ],
                    "excluded_displacement": consequence[
                        "maximum_excluded_displacement_mm"
                    ]
                    <= rehearsal_contract["gates"][
                        "maximum_excluded_displacement_mm"
                    ],
                    "collision": not consequence[
                        "new_nonselected_jaw_collision_pairs"
                    ],
                    "camera_margin": consequence["camera_margin_px"]
                    >= rehearsal_contract["camera_gate"][
                        "minimum_margin_px"
                    ],
                }
                replays.append(
                    {
                        "variant_id": variant["variant_id"],
                        **consequence,
                        "checks": checks,
                        "passed": all(checks.values()),
                    }
                )
            identity_checks = {
                "requested_sent_byte_identical": (
                    requested.tobytes(order="C")
                    == sent.tobytes(order="C")
                ),
                "requested_hash_matches_freeze": hashlib.sha256(
                    requested.tobytes(order="C")
                ).hexdigest()
                == case["action_sha256"],
                "timestamps_strictly_monotonic": bool(
                    np.all(np.diff(timestamps) > 0.0)
                ),
                "gateway_bounds": gateway[
                    "all_rows_inside_calibrated_limits"
                ],
                "gateway_rates": gateway[
                    "all_rates_within_reviewed_gateway_limits"
                ],
                "no_gateway_transform": not gateway[
                    "would_require_gateway_transform"
                ],
            }
            passed = all(identity_checks.values()) and all(
                row["passed"] for row in replays
            )
            path_results.append(
                {
                    "path_id": path_spec["path_id"],
                    "kind": path_spec["kind"],
                    "delay_seconds": path_spec.get("delay_seconds", 0.0),
                    "diagnostic_only": bool(
                        path_spec.get("diagnostic_only", False)
                    ),
                    "traces": traces,
                    "identity_checks": identity_checks,
                    "gateway": gateway,
                    "robustness": replays,
                    "passed": passed,
                }
            )
        case_passed = all(row["passed"] for row in path_results)
        results.append(
            {
                "case_id": case["case_id"],
                "direction_lane": case["direction_lane"],
                "source_square": case["source_square"],
                "destination_square": case["destination_square"],
                "selected_piece_id": case["selected_piece_id"],
                "action_sha256": case["action_sha256"],
                "plant_paths": path_results,
                "passed_both_paths": case_passed,
            }
        )

    passing = [row for row in results if row["passed_both_paths"]]
    lane_counts = {
        lane: sum(row["direction_lane"] == lane for row in passing)
        for lane in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    minimum = int(contract["acceptance"]["minimum_cases_per_direction"])
    direction_checks = {
        lane: count >= minimum for lane, count in lane_counts.items()
    }
    receipt = {
        "schema_version": (
            "sim2claw.bidirectional_pawn_push_v2_temporal_replay_receipt.v1"
        ),
        "status": (
            "temporal_replay_pass"
            if all(direction_checks.values())
            else "temporal_replay_reject"
        ),
        "proof_class": (
            "cpu_fp64_action_frozen_direct_target_and_diagnostic_"
            "zoh_consequence_replay"
        ),
        "contract_path": str(contract_path.relative_to(REPO_ROOT.resolve())),
        "contract_sha256": _sha(contract_path),
        "static_receipt_sha256": contract["static_receipt"]["sha256"],
        "candidate_refit": False,
        "task_outcomes_used_for_action_selection": False,
        "results": results,
        "passing_case_ids": [row["case_id"] for row in passing],
        "lane_counts": lane_counts,
        "direction_checks": direction_checks,
        "minimum_cases_per_direction": minimum,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": (
            "Simulation-only direct-target baseline and diagnostic 0.11 "
            "second ZOH challenger over pre-frozen byte-identical actions. "
            "No calibrated plant, physical task, promotion, or transfer claim."
        ),
    }
    receipt_path = output_directory / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["TemporalReplayError", "replay"]
