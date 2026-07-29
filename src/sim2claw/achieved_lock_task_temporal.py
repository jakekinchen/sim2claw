"""Narrow temporal replay adapter for the exact RP02D achieved-lock actions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_seeded_action_temporal as _temporal
from .observable_episode import (
    build_simulator_episode,
    first_divergence,
    write_episode,
)
from .paths import REPO_ROOT


class AchievedLockTaskTemporalError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(binding: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(binding["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise AchievedLockTaskTemporalError(
            "achieved-lock temporal input escaped repository"
        ) from error
    if not path.is_file() or _sha(path) != binding["sha256"]:
        raise AchievedLockTaskTemporalError(
            f"achieved-lock temporal input changed: {path}"
        )
    return path


def _json(binding: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(binding).read_text(encoding="utf-8"))


def _display(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT.resolve()))


def _write_tensor(
    directory: Path, name: str, values: np.ndarray
) -> dict[str, Any]:
    path = directory / f"{name}.f64le"
    array = np.asarray(values, dtype="<f8", order="C")
    path.write_bytes(array.tobytes(order="C"))
    return {
        "path": _display(path),
        "sha256": _sha(path),
        "shape": list(array.shape),
        "dtype": "little_endian_float64",
    }


def replay(contract_path: Path, output_directory: Path) -> dict[str, Any]:
    if output_directory.exists():
        raise AchievedLockTaskTemporalError(
            "immutable achieved-lock temporal output already exists"
        )
    compact = json.loads(contract_path.read_text(encoding="utf-8"))
    expected_fields = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "base_temporal_contract",
        "static_receipt",
        "static_closeout",
        "temporal_implementation",
        "cases",
        "live_seed",
        "output_directory",
        "unchanged_from_base",
        "claim_boundary",
    }
    if (
        set(compact) != expected_fields
        or compact.get("schema_version")
        != "sim2claw.achieved_lock_task_temporal.v1"
        or compact.get("status")
        != "frozen_after_exact_achieved_lock_static_pass_before_dynamic_replay"
        or len(compact.get("cases", [])) != 2
        or {case["direction"] for case in compact["cases"]}
        != {"REAL_TO_SIM", "SIM_TO_REAL"}
        or not all(compact["unchanged_from_base"].values())
    ):
        raise AchievedLockTaskTemporalError(
            "achieved-lock temporal contract changed or widened"
        )
    base = _json(compact["base_temporal_contract"])
    static = _json(compact["static_receipt"])
    _bound(compact["static_closeout"])
    _bound(compact["temporal_implementation"])
    if (
        static.get("status") != "achieved_lock_task_freeze_pass"
        or static.get("passed") is not True
        or static.get("direction_counts")
        != {"REAL_TO_SIM": 1, "SIM_TO_REAL": 1}
        or static.get("statically_eligible_family_count") != 2
        or static.get("dynamic_replay_executed") is not False
        or static.get("physical_motion") is not False
        or static.get("physical_task_attempts") != 0
    ):
        raise AchievedLockTaskTemporalError(
            "achieved-lock static admission changed"
        )
    for name in (
        "candidate_manifest",
        "registration_candidate",
        "observable_episode_contract",
        "observable_episode_closeout",
        "observable_episode_implementation",
    ):
        _bound(base["inputs"][name])
    if (
        base["plant_paths"][1]["delay_seconds"] != 0.11
        or base["gates"]["minimum_signed_progress_mm"] != 36.025
        or base["action_identity"]["sample_hz"] != 40.0
        or base["authority"]["dynamic_simulation"] is not True
        or any(
            value
            for name, value in base["authority"].items()
            if name != "dynamic_simulation"
        )
    ):
        raise AchievedLockTaskTemporalError(
            "base temporal proof gates changed"
        )
    static_by_id = {row["case_id"]: row for row in static["selected"]}
    if set(static_by_id) != {case["case_id"] for case in compact["cases"]}:
        raise AchievedLockTaskTemporalError(
            "achieved-lock temporal cases differ from static freeze"
        )

    manifest = _json(base["inputs"]["candidate_manifest"])
    rigid = _json(base["inputs"]["registration_candidate"])
    model_builder = _temporal._static_v2._calibrated_registered_model(
        _temporal._static._registered_current_model,
        manifest["candidate_config"],
    )
    timestep = float(base["simulation"]["timestep_s"])
    model, addresses, _, jaw_bodies = model_builder(rigid, timestep)
    actuators = [
        _temporal._static._named_id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, name
        )
        for name in _temporal._static.ALL_JOINTS
    ]
    sample_hz = float(base["action_identity"]["sample_hz"])
    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_size = tuple(base["camera_gate"]["image_size_px"])
    output_directory.mkdir(parents=True)
    results: list[dict[str, Any]] = []

    for case in compact["cases"]:
        frozen = static_by_id[case["case_id"]]
        if (
            frozen["action_sha256"] != case["action_sha256"]
            or frozen["direction"] != case["direction"]
        ):
            raise AchievedLockTaskTemporalError(
                "achieved-lock action identity changed"
            )
        requested = _temporal._load_action(case)
        mapped = requested.copy(order="C")
        sent = requested.copy(order="C")
        timestamps = np.arange(len(requested), dtype="<f8") / sample_hz
        source = np.asarray(
            _temporal.current_square_center(case["source_square"]),
            dtype=np.float64,
        )
        destination = np.asarray(
            _temporal.current_square_center(case["destination_square"]),
            dtype=np.float64,
        )
        direction = destination - source
        direction /= np.linalg.norm(direction)
        path_results: list[dict[str, Any]] = []
        episodes: dict[tuple[str, str], dict[str, Any]] = {}

        for plant in base["plant_paths"]:
            if plant["kind"] == "direct_target_mujoco":
                applied = requested.copy(order="C")
                source_indices = np.arange(len(requested), dtype=np.int64)
            elif plant["kind"] == "zero_order_hold_command_delay":
                applied, source_indices = _temporal._zoh_delay(
                    requested,
                    sample_hz=sample_hz,
                    delay_seconds=float(plant["delay_seconds"]),
                )
            else:
                raise AchievedLockTaskTemporalError(
                    "unexpected achieved-lock plant"
                )
            trace_directory = (
                output_directory
                / "traces"
                / case["case_id"]
                / plant["path_id"]
            )
            trace_directory.mkdir(parents=True)
            traces = {
                "requested": _write_tensor(
                    trace_directory, "requested", requested
                ),
                "mapped": _write_tensor(trace_directory, "mapped", mapped),
                "sent": _write_tensor(trace_directory, "sent", sent),
                "applied": _write_tensor(
                    trace_directory, "applied", applied
                ),
                "requested_timestamps": _write_tensor(
                    trace_directory, "requested_timestamps", timestamps
                ),
                "sent_timestamps": _write_tensor(
                    trace_directory, "sent_timestamps", timestamps
                ),
                "applied_timestamps": _write_tensor(
                    trace_directory, "applied_timestamps", timestamps
                ),
            }
            index_path = trace_directory / "applied_source_indices.i64le"
            index_path.write_bytes(
                np.asarray(source_indices, dtype="<i8").tobytes(order="C")
            )
            traces["applied_source_indices"] = {
                "path": _display(index_path),
                "sha256": _sha(index_path),
                "shape": list(source_indices.shape),
                "dtype": "little_endian_int64",
            }
            robustness: list[dict[str, Any]] = []
            for variant in base["robustness_variants"]:
                longitudinal, lateral = variant["delta_m"]
                delta = (
                    direction[:2] * longitudinal
                    + np.asarray([-direction[1], direction[0]]) * lateral
                )
                consequence = _temporal._replay(
                    model=model,
                    addresses=addresses,
                    actuators=actuators,
                    jaw_bodies=jaw_bodies,
                    action=applied,
                    selected_name=case["selected_piece_id"],
                    source_delta_m=delta,
                    direction=direction,
                    substeps=int(base["simulation"]["substeps_per_row"]),
                    sample_hz=sample_hz,
                    first_object_motion_threshold_m=float(
                        base["observable_episode"][
                            "first_object_motion_threshold_m"
                        ]
                    ),
                    camera=camera,
                    image_size=image_size,
                )
                observable = consequence.pop("observable_inputs")
                checks = {
                    "progress": consequence["signed_progress_mm"]
                    >= base["gates"]["minimum_signed_progress_mm"],
                    "selected_contact": consequence[
                        "selected_contact_steps"
                    ]
                    > 0,
                    "excluded_contact": consequence[
                        "excluded_contact_steps"
                    ]
                    == 0,
                    "excluded_displacement": consequence[
                        "maximum_excluded_displacement_mm"
                    ]
                    <= base["gates"][
                        "maximum_excluded_displacement_mm"
                    ],
                    "no_lift": consequence[
                        "maximum_selected_vertical_rise_mm"
                    ]
                    <= base["gates"][
                        "maximum_selected_vertical_rise_mm"
                    ],
                    "collision": not consequence[
                        "new_nonselected_jaw_collision_pairs"
                    ],
                    "camera_margin": consequence["camera_margin_px"]
                    >= base["camera_gate"]["minimum_margin_px"],
                }
                outcome = (
                    "pass"
                    if all(checks.values())
                    else "fail:"
                    + ",".join(
                        sorted(
                            name
                            for name, passed in checks.items()
                            if not passed
                        )
                    )
                )
                episode = build_simulator_episode(
                    episode_id=(
                        f"{case['case_id']}__{plant['path_id']}"
                        f"__{variant['variant_id']}"
                    ),
                    requested=requested,
                    applied=applied,
                    sample_hz=sample_hz,
                    joint_states=observable["joint_states"],
                    link_poses=observable["link_poses"],
                    object_states_board_se2=observable[
                        "object_states_board_se2"
                    ],
                    object_covariances=observable["object_covariances"],
                    contact_states=observable["contact_states"],
                    task_outcome=outcome,
                    first_object_motion_sample=observable[
                        "first_object_motion_sample"
                    ],
                    provenance={
                        "contract_path": _display(contract_path),
                        "contract_sha256": _sha(contract_path),
                        "static_receipt_sha256": compact[
                            "static_receipt"
                        ]["sha256"],
                        "case_id": case["case_id"],
                        "direction": case["direction"],
                        "plant_path_id": plant["path_id"],
                        "diagnostic_only": bool(
                            plant.get("diagnostic_only", False)
                        ),
                        "variant_id": variant["variant_id"],
                        "source_delta_m": delta.tolist(),
                    },
                )
                episode_path = (
                    output_directory
                    / "episodes"
                    / case["case_id"]
                    / plant["path_id"]
                    / f"{variant['variant_id']}.json"
                )
                episode_receipt = write_episode(episode, episode_path)
                episode_receipt["path"] = _display(episode_path)
                episodes[(plant["path_id"], variant["variant_id"])] = (
                    episode
                )
                robustness.append(
                    {
                        "variant_id": variant["variant_id"],
                        **consequence,
                        "checks": checks,
                        "passed": all(checks.values()),
                        "observable_episode": episode_receipt,
                    }
                )
            physical_applied = _temporal._static._physical_actions(
                applied, manifest["candidate_config"]
            )
            maximum_rates = np.max(
                np.abs(np.diff(physical_applied, axis=0)) * sample_hz,
                axis=0,
            )
            rate_limits = np.asarray(
                base["action_identity"]["gateway_rate_limits_per_joint"],
                dtype=np.float64,
            )
            identity_checks = {
                "requested_mapped_sent_byte_identical": (
                    requested.tobytes(order="C")
                    == mapped.tobytes(order="C")
                    == sent.tobytes(order="C")
                ),
                "requested_hash_matches_freeze": hashlib.sha256(
                    requested.tobytes(order="C")
                ).hexdigest()
                == case["action_sha256"],
                "timestamps_strictly_monotonic": bool(
                    np.all(np.diff(timestamps) > 0.0)
                ),
                "row_zero_exact_live_seed": np.array_equal(
                    _temporal._static._physical_actions(
                        requested[:1], manifest["candidate_config"]
                    )[0],
                    np.asarray(
                        compact["live_seed"][
                            "follower_position_degrees"
                        ],
                        dtype=np.float64,
                    ),
                ),
                "applied_gateway_rate_compatible_without_modification": bool(
                    np.all(maximum_rates <= rate_limits)
                ),
            }
            path_results.append(
                {
                    "path_id": plant["path_id"],
                    "kind": plant["kind"],
                    "delay_seconds": plant["delay_seconds"],
                    "diagnostic_only": plant["diagnostic_only"],
                    "traces": traces,
                    "maximum_applied_physical_rate_per_second": (
                        maximum_rates.tolist()
                    ),
                    "identity_checks": identity_checks,
                    "robustness": robustness,
                    "passed": all(identity_checks.values())
                    and all(row["passed"] for row in robustness),
                }
            )
        divergence = []
        direct_id = base["plant_paths"][0]["path_id"]
        zoh_id = base["plant_paths"][1]["path_id"]
        for variant in base["robustness_variants"]:
            variant_id = variant["variant_id"]
            divergence.append(
                {
                    "variant_id": variant_id,
                    **first_divergence(
                        episodes[(direct_id, variant_id)],
                        episodes[(zoh_id, variant_id)],
                        joint_threshold=float(
                            base["first_divergence"][
                                "joint_threshold_rad"
                            ]
                        ),
                        link_position_threshold_m=float(
                            base["first_divergence"][
                                "link_position_threshold_m"
                            ]
                        ),
                        object_position_threshold_m=float(
                            base["first_divergence"][
                                "object_position_threshold_m"
                            ]
                        ),
                        object_yaw_threshold_rad=float(
                            base["first_divergence"][
                                "object_yaw_threshold_rad"
                            ]
                        ),
                    ),
                }
            )
        results.append(
            {
                "case_id": case["case_id"],
                "direction": case["direction"],
                "source_square": case["source_square"],
                "destination_square": case["destination_square"],
                "selected_piece_id": case["selected_piece_id"],
                "action_sha256": case["action_sha256"],
                "plant_paths": path_results,
                "direct_vs_zoh_first_divergence": divergence,
                "passed_both_paths": all(
                    path["passed"] for path in path_results
                ),
            }
        )

    passing = [result for result in results if result["passed_both_paths"]]
    counts = {
        direction: sum(
            result["direction"] == direction for result in passing
        )
        for direction in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    passed = counts == {"REAL_TO_SIM": 1, "SIM_TO_REAL": 1}
    receipt = {
        "schema_version": "sim2claw.achieved_lock_task_temporal_receipt.v1",
        "status": (
            "achieved_lock_task_temporal_pass"
            if passed
            else "achieved_lock_task_temporal_reject"
        ),
        "proof_class": compact["proof_class"],
        "contract_path": _display(contract_path),
        "contract_sha256": _sha(contract_path),
        "static_receipt_sha256": compact["static_receipt"]["sha256"],
        "results": results,
        "passing_case_ids": [
            result["case_id"] for result in passing
        ],
        "direction_counts": counts,
        "minimum_cases_per_direction": 1,
        "task_outcomes_used_for_action_selection": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "passed": passed,
        "authority": base["authority"],
        "claim_boundary": compact["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = ["AchievedLockTaskTemporalError", "replay"]
